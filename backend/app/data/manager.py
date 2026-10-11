import datetime
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from app.data.base import BaseDataProvider
from app.data.synthetic import SyntheticDemoDataProvider
from app.data.external import ExternalMarketDataProvider
from app.data.market_hours import get_forex_market_status, is_otc_symbol
from app.core.config import settings

class DataQualityReport:
    def __init__(self, is_valid: bool, status: str, details: Dict[str, Any]):
        self.is_valid = is_valid
        self.status = status  # VALID, STALE, GAP_DETECTED, PRICE_ANOMALY, INSUFFICIENT, DISCONNECTED, MARKET_CLOSED
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "status": self.status,
            "details": self.details,
        }

class MarketDataManager:
    """
    Central manager for market data.
    Provides live real Forex market data to indicators and strategy,
    enforcing zero synthetic data leakage into live trading analysis,
    strict data hygiene, anomaly detection, and Quotex price discrepancy disclosure.
    """

    def __init__(self):
        self.demo_provider = SyntheticDemoDataProvider()
        self.external_provider = ExternalMarketDataProvider(
            twelve_data_api_key=settings.TWELVE_DATA_API_KEY
        )

    def get_active_provider(self) -> BaseDataProvider:
        mode = settings.DATA_MODE.upper()
        # Synthetic provider is permitted ONLY in explicit offline test mode
        if mode == "DEMO_OFFLINE":
            return self.demo_provider
        return self.external_provider

    def get_status(self) -> Dict[str, Any]:
        provider = self.get_active_provider()
        health = provider.check_health()
        market_hours = get_forex_market_status()

        quotex_disclaimer = (
            "⚠️ تفاوت مظنه Quotex با بازار بین‌بانکی: "
            "مظنه‌های ارائه‌دهنده بازار بر مبنای نرخ‌های بین‌بانکی رسمی است. پلتفرم Quotex "
            "ممکن است به دلیل اسپرد داخلی یا تأمین‌کننده نقدینگی خود، اختلاف جزئی (۱ تا ۳ پیپ) با بازار داشته باشد. "
            "توصیه می‌شود تنها در سیگنال‌های با توافق بیش از ۸۰٪ و شکست‌های پرقدرت معامله دستی انجام دهید."
        )

        return {
            "data_mode": "REAL" if not provider.is_demo else "DEMO_OFFLINE",
            "data_source": provider.source_name,
            "status": health["status"],
            "latency_ms": health["latency_ms"],
            "last_successful_sync": health.get("last_successful_sync"),
            "is_healthy": health["status"] in ["LIVE", "REAL_DELAYED", "OK"],
            "is_demo": provider.is_demo,
            "is_market_open": market_hours["is_open"],
            "market_hours_info": market_hours,
            "disclaimer": quotex_disclaimer,
            "supported_symbols": settings.SUPPORTED_SYMBOLS,
            "timeframes": settings.DEFAULT_TIMEFRAMES,
        }

    def validate_candles(self, df: pd.DataFrame, timeframe: str) -> DataQualityReport:
        """
        Rigorous multi-layer data quality audit:
          1. Insufficient count check
          2. Duplicate timestamp check
          3. Price sanity & integrity check
          4. Abnormal gap detection
          5. Market staleness check (aware of weekend market closure)
        """
        if df.empty or len(df) < 30:
            return DataQualityReport(
                is_valid=False,
                status="INSUFFICIENT",
                details={"reason": "تعداد کندل‌های دریافتی برای محاسبه معتبر استراتژی کافی نیست (حداقل ۳۰ کندل نیاز است)."},
            )

        # 1. Duplicate timestamp check
        if df["timestamp"].duplicated().any():
            return DataQualityReport(
                is_valid=False,
                status="DUPLICATE_CANDLES",
                details={"reason": "کندل‌های تکراری در سری زمانی جریان داده مشاهده شد."},
            )

        # 2. Price sanity check (High/Low and positive values)
        invalid_bounds = (
            (df["high"] < df["low"])
            | (df["open"] > df["high"])
            | (df["open"] < df["low"])
            | (df["close"] > df["high"])
            | (df["close"] < df["low"])
            | (df["close"] <= 0)
        )
        if invalid_bounds.any():
            return DataQualityReport(
                is_valid=False,
                status="PRICE_ANOMALY",
                details={"reason": "قیمت‌های غیرعادی یا ناهماهنگ در کندل‌ها کشف شد (نقص در High/Low یا قیمت منفی)."},
            )

        # 3. Abnormal gap check (time difference between consecutive candles)
        tf_map = {"M1": 1, "M5": 5, "M15": 15}
        expected_mins = tf_map.get(timeframe.upper(), 1)
        time_diffs = df["timestamp"].diff().dropna()
        max_allowed_delta = datetime.timedelta(minutes=expected_mins * 6)

        # Allow gaps across weekend boundary
        abnormal_gaps = [td for td in time_diffs if td > max_allowed_delta and td < datetime.timedelta(days=2)]
        if len(abnormal_gaps) > 3:
            return DataQualityReport(
                is_valid=False,
                status="GAP_DETECTED",
                details={"reason": f"شکاف زمانی غیرعادی در جریان داده تشخیص داده شد (بیش از ۳ گپ بالای {expected_mins * 6} دقیقه)."},
            )

        # 4. Freshness and staleness check
        market_status = get_forex_market_status()
        latest_ts = df["timestamp"].iloc[-1]
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        if market_status["is_open"]:
            # When market is actively open, data shouldn't lag significantly
            if now_utc - latest_ts > datetime.timedelta(minutes=expected_mins * 12):
                return DataQualityReport(
                    is_valid=False,
                    status="STALE",
                    details={
                        "reason": f"داده‌های دریافتی قدیمی هستند (آخرین کندل: {latest_ts} UTC). ارتباط زنده بازار نیازمند تازه‌سازی است.",
                        "latest_candle_time": str(latest_ts),
                    },
                )
        else:
            # During weekend closure, inform the user that market is closed
            return DataQualityReport(
                is_valid=True,
                status="MARKET_CLOSED_WEEKEND",
                details={
                    "reason": "بازار رسمی فارکس به دلیل تعطیلات آخر هفته بسته است. تحلیل بر مبنای آخرین کندل‌های پایانی رسمی انجام می‌شود.",
                    "candle_count": len(df),
                    "latest_candle_time": str(latest_ts),
                },
            )

        return DataQualityReport(
            is_valid=True,
            status="VALID",
            details={"candle_count": len(df), "latest_candle_time": str(latest_ts)},
        )

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 120,
        end_time: Optional[datetime.datetime] = None,
    ) -> Tuple[pd.DataFrame, DataQualityReport]:
        """
        Fetches authentic market candles.
        CRITICAL RULE: Never fall back to synthetic data in live operational mode!
        If network fails, returns empty DataFrame and an explicit error report.
        """
        if is_otc_symbol(symbol):
            empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
            report = DataQualityReport(
                is_valid=False,
                status="OTC_REJECTED",
                details={"reason": f"نماد {symbol} نماد غیررسمی OTC است و برای معاملات واقعی پشتیبانی نمی‌شود."},
            )
            return empty_df, report

        provider = self.get_active_provider()
        try:
            df = provider.fetch_historical_candles(
                symbol=symbol,
                timeframe=timeframe,
                count=count,
                end_time=end_time,
            )
            report = self.validate_candles(df, timeframe)
            return df, report
        except Exception as e:
            # If in explicit offline demo mode, fall back to synthetic
            if provider.is_demo:
                df = self.demo_provider.fetch_historical_candles(symbol, timeframe, count, end_time)
                report = self.validate_candles(df, timeframe)
                return df, report

            # In REAL mode: DO NOT INJECT FAKE DATA!
            empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
            report = DataQualityReport(
                is_valid=False,
                status="DISCONNECTED",
                details={
                    "reason": f"عدم امکان دریافت داده واقعی از بازار ({str(e)}). به منظور حفظ سرمایه، سیگنالی صادر نمی‌شود.",
                    "error": str(e),
                },
            )
            return empty_df, report

market_data_manager = MarketDataManager()
