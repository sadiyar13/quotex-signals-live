import json
import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.data.manager import market_data_manager
from app.services.signal_service import signal_service
from app.backtesting.engine import backtest_engine
from app.models.models import BacktestRunRecord, BacktestTradeRecord, AppSettingRecord
from app.schemas.schemas import (
    CandleSchema,
    MarketStatusSchema,
    SignalSchema,
    AnalyzeRequest,
    ManualOutcomeCreate,
    AnalyticsSummary,
    BacktestRequest,
    BacktestResponse,
    SettingsSchema,
    SettingsUpdate,
)
from app.core.config import settings

api_router = APIRouter()

@api_router.get("/health")
def get_health():
    """System health check and diagnostic status."""
    return {
        "status": "OK",
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "utc_time": datetime.datetime.utcnow().isoformat(),
        "data_mode": settings.DATA_MODE,
    }


@api_router.get("/assets")
def get_assets():
    """List of supported Forex currency pairs and default timeframes."""
    return {
        "symbols": settings.SUPPORTED_SYMBOLS,
        "timeframes": settings.DEFAULT_TIMEFRAMES,
        "horizon_minutes": settings.SIGNAL_HORIZON_MINUTES,
        "default_payout_ratio": settings.DEFAULT_PAYOUT_RATIO,
    }


@api_router.get("/market/status", response_model=MarketStatusSchema)
def get_market_status():
    """Active data source, latency, freshness, and operational health."""
    return market_data_manager.get_status()


@api_router.get("/market/candles", response_model=List[CandleSchema])
def get_market_candles(
    symbol: str = Query("EUR/USD"),
    timeframe: str = Query("M1"),
    count: int = Query(100, ge=10, le=500),
):
    """Fetches verified historical OHLCV candles with UTC timestamps."""
    if symbol not in settings.SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"نماد {symbol} پشتیبانی نمی‌شود.")
    if timeframe not in settings.DEFAULT_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"تایم‌فریم {timeframe} نامعتبر است.")

    df, report = market_data_manager.get_candles(symbol, timeframe, count=count)
    return df.to_dict(orient="records")


@api_router.post("/signals/analyze", response_model=SignalSchema)
def analyze_signal(
    req: AnalyzeRequest,
    db: Session = Depends(get_db),
):
    """
    Evaluates current market conditions across M1, M5, M15.
    Applies the 5 independent filters and produces CALL / PUT / NO TRADE.
    Prevents duplicate entries and saves result to SQLite.
    """
    if req.symbol not in settings.SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"نماد {req.symbol} پشتیبانی نمی‌شود.")

    try:
        sig = signal_service.analyze_and_record(db, req.symbol, req.timeframe)
        return sig
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در پردازش سیگنال: {str(e)}")


@api_router.get("/signals", response_model=List[SignalSchema])
def list_signals(
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    is_evaluated: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Fetches historical signals with filters and outcomes."""
    return signal_service.get_signals(db, symbol, direction, is_evaluated, limit)


@api_router.get("/signals/{signal_id}", response_model=SignalSchema)
def get_signal_detail(
    signal_id: str,
    db: Session = Depends(get_db),
):
    """Fetches comprehensive details of a single signal."""
    sig = signal_service.get_signal_by_id(db, signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="سیگنال مورد نظر یافت نشد.")
    return sig


@api_router.post("/signals/{signal_id}/manual-outcome", response_model=SignalSchema)
def record_manual_outcome(
    signal_id: str,
    payload: ManualOutcomeCreate,
    db: Session = Depends(get_db),
):
    """
    Records manually observed outcome from Quotex (entry price, expiry price, outcome).
    Kept strictly separated from external algorithmic evaluations.
    """
    try:
        sig = signal_service.record_manual_outcome(db, signal_id, payload)
        return sig
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در ثبت نتیجه دستی: {str(e)}")


@api_router.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics(db: Session = Depends(get_db)):
    """Summary of algorithmic paper trading & manual Quotex logs with Wilson confidence intervals."""
    return signal_service.get_analytics_summary(db)


@api_router.post("/backtests", response_model=BacktestResponse)
def run_backtest(
    req: BacktestRequest,
    db: Session = Depends(get_db),
):
    """
    Runs historical replay backtest on candles without lookahead bias.
    Splits into Development, Validation, or Out-of-sample periods.
    """
    df_m1, report = market_data_manager.get_candles(req.symbol, "M1", count=1200)
    if df_m1.empty or len(df_m1) < 60:
        raise HTTPException(status_code=400, detail="داده برای اجرای بکتست ناکافی است.")

    try:
        bt_res = backtest_engine.run(
            df_m1=df_m1,
            symbol=req.symbol,
            period_type=req.period_type,
            payout_ratio=req.payout_ratio,
            min_rule_agreement=req.min_rule_agreement,
        )

        # Save to database
        run_rec = BacktestRunRecord(
            id=bt_res["run_id"],
            symbol=req.symbol,
            start_time=df_m1["timestamp"].iloc[0],
            end_time=df_m1["timestamp"].iloc[-1],
            period_type=req.period_type,
            payout_ratio=bt_res["payout_ratio"],
            strategy_version=req.strategy_version,
            total_candles=bt_res["total_candles"],
            total_signals=bt_res["total_signals"],
            call_signals=bt_res["call_signals"],
            put_signals=bt_res["put_signals"],
            win_count=bt_res["win_count"],
            loss_count=bt_res["loss_count"],
            tie_count=bt_res["tie_count"],
            win_rate=bt_res["win_rate"],
            wilson_ci_lower=bt_res["wilson_ci_lower"],
            wilson_ci_upper=bt_res["wilson_ci_upper"],
            max_consecutive_losses=bt_res["max_consecutive_losses"],
            net_simulated_return=bt_res["net_simulated_return"],
            break_even_rate=bt_res["break_even_rate"],
            rejected_signals_count=bt_res["rejected_signals_count"],
            missing_data_count=bt_res["missing_data_count"],
            summary_report_json=json.dumps(bt_res["session_breakdown"]),
        )
        db.add(run_rec)

        for t in bt_res["trades"]:
            t_rec = BacktestTradeRecord(
                run_id=bt_res["run_id"],
                symbol=t["symbol"],
                direction=t["direction"],
                entry_time=t["entry_time"],
                entry_price=t["entry_price"],
                expiry_time=t["expiry_time"],
                expiry_price=t["expiry_price"],
                outcome=t["outcome"],
                rule_score=t["rule_score"],
                return_unit=t["return_unit"],
            )
            db.add(t_rec)

        db.commit()
        return bt_res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در اجرای بکتست: {str(e)}")


@api_router.get("/backtests/{run_id}", response_model=BacktestResponse)
def get_backtest_run(run_id: str, db: Session = Depends(get_db)):
    """Fetches details of a stored backtest run."""
    run_rec = db.query(BacktestRunRecord).filter(BacktestRunRecord.id == run_id).first()
    if not run_rec:
        raise HTTPException(status_code=404, detail="نتیجه بکتست یافت نشد.")

    trades = [
        {
            "symbol": t.symbol,
            "direction": t.direction,
            "entry_time": t.entry_time,
            "entry_price": t.entry_price,
            "expiry_time": t.expiry_time,
            "expiry_price": t.expiry_price,
            "outcome": t.outcome,
            "rule_score": t.rule_score,
            "return_unit": t.return_unit,
        }
        for t in run_rec.trades
    ]

    session_breakdown = {}
    if run_rec.summary_report_json:
        try:
            session_breakdown = json.loads(run_rec.summary_report_json)
        except Exception:
            pass

    return {
        "run_id": run_rec.id,
        "symbol": run_rec.symbol,
        "period_type": run_rec.period_type,
        "payout_ratio": run_rec.payout_ratio,
        "total_candles": run_rec.total_candles,
        "total_signals": run_rec.total_signals,
        "call_signals": run_rec.call_signals,
        "put_signals": run_rec.put_signals,
        "win_count": run_rec.win_count,
        "loss_count": run_rec.loss_count,
        "tie_count": run_rec.tie_count,
        "win_rate": run_rec.win_rate,
        "wilson_ci_lower": run_rec.wilson_ci_lower,
        "wilson_ci_upper": run_rec.wilson_ci_upper,
        "max_consecutive_losses": run_rec.max_consecutive_losses,
        "net_simulated_return": run_rec.net_simulated_return,
        "break_even_rate": run_rec.break_even_rate,
        "rejected_signals_count": run_rec.rejected_signals_count,
        "missing_data_count": run_rec.missing_data_count,
        "session_breakdown": session_breakdown,
        "hourly_breakdown": {},
        "trades": trades,
    }


@api_router.get("/settings", response_model=SettingsSchema)
def get_app_settings(db: Session = Depends(get_db)):
    """Retrieves operational strategy settings."""
    return {
        "data_mode": settings.DATA_MODE,
        "ema_fast_period": settings.EMA_FAST_PERIOD,
        "ema_slow_period": settings.EMA_SLOW_PERIOD,
        "rsi_period": settings.RSI_PERIOD,
        "rsi_overbought": settings.RSI_OVERBOUGHT,
        "rsi_oversold": settings.RSI_OVERSOLD,
        "macd_fast": settings.MACD_FAST,
        "macd_slow": settings.MACD_SLOW,
        "macd_signal": settings.MACD_SIGNAL,
        "atr_period": settings.ATR_PERIOD,
        "min_rule_agreement_count": settings.MIN_RULE_AGREEMENT_COUNT,
        "default_payout_ratio": settings.DEFAULT_PAYOUT_RATIO,
        "alpha_vantage_api_key": settings.ALPHA_VANTAGE_API_KEY[:4] + "***" if settings.ALPHA_VANTAGE_API_KEY else "",
        "twelve_data_api_key": settings.TWELVE_DATA_API_KEY[:4] + "***" if settings.TWELVE_DATA_API_KEY else "",
    }


@api_router.put("/settings", response_model=SettingsSchema)
def update_app_settings(
    update: SettingsUpdate,
    db: Session = Depends(get_db),
):
    """Updates operational settings."""
    if update.data_mode:
        settings.DATA_MODE = update.data_mode
    if update.ema_fast_period:
        settings.EMA_FAST_PERIOD = update.ema_fast_period
    if update.ema_slow_period:
        settings.EMA_SLOW_PERIOD = update.ema_slow_period
    if update.rsi_period:
        settings.RSI_PERIOD = update.rsi_period
    if update.rsi_overbought:
        settings.RSI_OVERBOUGHT = update.rsi_overbought
    if update.rsi_oversold:
        settings.RSI_OVERSOLD = update.rsi_oversold
    if update.macd_fast:
        settings.MACD_FAST = update.macd_fast
    if update.macd_slow:
        settings.MACD_SLOW = update.macd_slow
    if update.macd_signal:
        settings.MACD_SIGNAL = update.macd_signal
    if update.atr_period:
        settings.ATR_PERIOD = update.atr_period
    if update.min_rule_agreement_count:
        settings.MIN_RULE_AGREEMENT_COUNT = update.min_rule_agreement_count
    if update.default_payout_ratio:
        settings.DEFAULT_PAYOUT_RATIO = update.default_payout_ratio
    if update.twelve_data_api_key is not None:
        settings.TWELVE_DATA_API_KEY = update.twelve_data_api_key

    return get_app_settings(db)
