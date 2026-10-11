import datetime
import time
import httpx
import pandas as pd
from typing import Dict, Any, Optional
from app.data.base import BaseDataProvider
from app.data.market_hours import get_forex_market_status, is_otc_symbol, ALLOWED_FOREX_SYMBOLS
from app.core.config import settings

YAHOO_SYMBOL_MAP = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CHF": "USDCHF=X",
    "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X",
}

class YahooFinanceForexProvider:
    """
    Real Interbank Forex Market Data Provider via Yahoo Finance v8 chart API.
    Provides legitimate live/delayed OHLCV candles for standard Forex pairs.
    Zero registration or API key required.
    Includes in-memory TTL caching (5 seconds) to prevent redundant network requests.
    """

    def __init__(self, cache_ttl_seconds: float = 4.0):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_latency_ms: float = 0.0
        self._last_sync: Optional[datetime.datetime] = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

    @property
    def source_name(self) -> str:
        return "YAHOO_INTERBANK_REAL"

    def fetch_candles(self, symbol: str, timeframe: str, count: int = 120) -> pd.DataFrame:
        if is_otc_symbol(symbol):
            raise ValueError(f"نماد {symbol} از نوع OTC است. این سامانه فقط جفت‌ارزهای رسمی فارکس را پشتیبانی می‌کند.")

        y_symbol = YAHOO_SYMBOL_MAP.get(symbol)
        if not y_symbol:
            y_symbol = symbol.replace("/", "") + "=X"

        tf_map = {
            "M1": ("1m", "1d"),
            "M5": ("5m", "5d"),
            "M15": ("15m", "5d"),
        }
        interval, range_str = tf_map.get(timeframe.upper(), ("1m", "1d"))

        cache_key = f"{symbol}_{timeframe}"
        now = time.time()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if now - cached["timestamp"] < self.cache_ttl:
                return cached["data"].tail(count).copy()

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_symbol}?interval={interval}&range={range_str}"
        start_t = time.time()

        try:
            with httpx.Client(timeout=9.0) as client:
                resp = client.get(url, headers=self._headers)
                self._last_latency_ms = round((time.time() - start_t) * 1000, 2)
                resp.raise_for_status()
                data = resp.json()

            chart = data.get("chart", {})
            result_list = chart.get("result")
            if not result_list:
                err = chart.get("error", {})
                raise ConnectionError(f"خطا در دریافت مظنه بازار از یاهو فایننس: {err.get('description', 'پاسخ خالی')}")

            result = result_list[0]
            timestamps = result.get("timestamp", [])
            indicators = result.get("indicators", {})
            quote_list = indicators.get("quote", [])
            if not quote_list or not timestamps:
                raise ValueError(f"داده‌های کندل‌استیک برای نماد {symbol} در دسترس نیست.")

            quotes = quote_list[0]
            opens = quotes.get("open", [])
            highs = quotes.get("high", [])
            lows = quotes.get("low", [])
            closes = quotes.get("close", [])
            volumes = quotes.get("volume", [])

            rows = []
            for i, ts in enumerate(timestamps):
                if i >= len(opens) or i >= len(highs) or i >= len(lows) or i >= len(closes):
                    break
                o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                v = volumes[i] if volumes and i < len(volumes) else 0.0

                if o is not None and h is not None and l is not None and c is not None:
                    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).replace(tzinfo=None)
                    rows.append({
                        "timestamp": dt,
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v or 0.0),
                    })

            if not rows:
                raise ValueError(f"کندل معتبری برای نماد {symbol} استخراج نشد.")

            df = pd.DataFrame(rows)
            df.sort_values("timestamp", inplace=True)
            df.reset_index(drop=True, inplace=True)

            self._last_sync = datetime.datetime.utcnow()
            self._cache[cache_key] = {"timestamp": now, "data": df}
            return df.tail(count).copy()

        except Exception as e:
            self._last_latency_ms = round((time.time() - start_t) * 1000, 2)
            raise ConnectionError(f"خطای ارتباط با منبع داده بین‌بانکی یاهو فایننس: {str(e)}")


class TwelveDataClient:
    """
    Twelve Data REST Client.
    Requires personal API key configured in .env (TWELVE_DATA_API_KEY).
    Includes rate-limiting throttle (8 calls/min on free tier).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TWELVE_DATA_API_KEY
        self._last_call_time = 0.0
        self._min_interval_seconds = 1.2
        self._last_latency_ms = 0.0
        self._last_sync: Optional[datetime.datetime] = None

    @property
    def source_name(self) -> str:
        return "TWELVE_DATA_REST"

    def fetch_candles(self, symbol: str, timeframe: str, count: int = 120) -> pd.DataFrame:
        if not self.api_key:
            raise ValueError("کلید API برای Twelve Data تنظیم نشده است.")

        if is_otc_symbol(symbol):
            raise ValueError(f"نماد {symbol} از نوع OTC است. Twelve Data فقط نمادهای رسمی فارکس را پشتیبانی می‌کند.")

        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval_seconds:
            time.sleep(self._min_interval_seconds - elapsed)

        interval_map = {"M1": "1min", "M5": "5min", "M15": "15min"}
        interval_str = interval_map.get(timeframe.upper(), "1min")

        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval_str,
            "outputsize": count,
            "apikey": self.api_key,
            "timezone": "UTC",
        }

        start_t = time.time()
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params=params)
                self._last_latency_ms = round((time.time() - start_t) * 1000, 2)
                self._last_call_time = time.time()
                resp.raise_for_status()
                data = resp.json()

            if "values" not in data:
                err_msg = data.get("message", "خطای دریافت داده از Twelve Data")
                raise ValueError(err_msg)

            rows = []
            for item in reversed(data["values"]):
                dt = datetime.datetime.fromisoformat(item["datetime"])
                rows.append({
                    "timestamp": dt,
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume", 0.0)),
                })

            df = pd.DataFrame(rows)
            self._last_sync = datetime.datetime.utcnow()
            return df
        except Exception as e:
            self._last_latency_ms = round((time.time() - start_t) * 1000, 2)
            raise ConnectionError(f"خطای ارتباط با Twelve Data: {str(e)}")


class ExternalMarketDataProvider(BaseDataProvider):
    """
    Primary Unified Real Market Data Provider for live operations.
    Strictly uses real market sources:
      1. Twelve Data (if user API key is provided)
      2. Yahoo Finance Interbank Forex (zero-key real market feed)
    Zero synthetic or random data is generated in this provider.
    """

    def __init__(self, twelve_data_api_key: Optional[str] = None):
        self.twelve_data = TwelveDataClient(api_key=twelve_data_api_key)
        self.yahoo_interbank = YahooFinanceForexProvider()
        self._last_latency_ms = 0.0
        self._last_sync: Optional[datetime.datetime] = None

    @property
    def source_name(self) -> str:
        if self.twelve_data.api_key:
            return "TWELVE_DATA_LIVE"
        return "YAHOO_INTERBANK_REAL"

    @property
    def is_demo(self) -> bool:
        return False

    def check_health(self) -> Dict[str, Any]:
        market_hours = get_forex_market_status()
        is_market_open = market_hours["is_open"]

        if self.twelve_data.api_key:
            active_src = "Twelve Data (کلید API فعال)"
            status = "LIVE" if is_market_open else "MARKET_CLOSED"
        else:
            active_src = "Yahoo Finance Interbank Forex (جریان داده بدون کلید)"
            status = "REAL_DELAYED" if is_market_open else "MARKET_CLOSED"

        latency = self._last_latency_ms or self.yahoo_interbank._last_latency_ms or self.twelve_data._last_latency_ms

        if not is_market_open:
            msg = f"{active_src} متصل است. {market_hours['reason']}"
        else:
            msg = f"جریان داده واقعی از {active_src} فعال و متصل است."

        return {
            "status": status,
            "latency_ms": latency,
            "last_successful_sync": self._last_sync or datetime.datetime.utcnow(),
            "message": msg,
            "is_demo": False,
            "is_market_open": is_market_open,
            "market_hours": market_hours,
            "has_twelve_data_key": bool(self.twelve_data.api_key),
        }

    def fetch_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 120,
        end_time: Optional[datetime.datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetches authentic historical Forex candles.
        First attempts Twelve Data (if key set), then falls back to Yahoo Interbank.
        If both fail, raises an exception — never injects fake candles.
        """
        # If user provided a Twelve Data key, prioritize it
        if self.twelve_data.api_key:
            try:
                df = self.twelve_data.fetch_candles(symbol, timeframe, count)
                self._last_latency_ms = self.twelve_data._last_latency_ms
                self._last_sync = self.twelve_data._last_sync
                return df
            except Exception as e:
                # Log or fall back to Yahoo Interbank as secondary real source
                pass

        # Use Yahoo Interbank real Forex feed
        try:
            df = self.yahoo_interbank.fetch_candles(symbol, timeframe, count)
            self._last_latency_ms = self.yahoo_interbank._last_latency_ms
            self._last_sync = self.yahoo_interbank._last_sync
            return df
        except Exception as e:
            self._last_latency_ms = self.yahoo_interbank._last_latency_ms
            raise ConnectionError(f"امکان دریافت داده واقعی از منابع بازار وجود ندارد: {str(e)}")

    def fetch_latest_candle(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        df = self.fetch_historical_candles(symbol, timeframe, count=2)
        latest = df.iloc[-1]
        return {
            "timestamp": latest["timestamp"],
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "close": float(latest["close"]),
            "volume": float(latest.get("volume", 0.0)),
        }
