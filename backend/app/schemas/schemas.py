import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class CandleSchema(BaseModel):
    timestamp: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0

    class Config:
        from_attributes = True


class MarketStatusSchema(BaseModel):
    data_mode: str
    data_source: str
    status: str
    latency_ms: float
    last_successful_sync: Optional[datetime.datetime]
    is_healthy: bool
    is_demo: bool
    is_market_open: Optional[bool] = True
    market_hours_info: Optional[Dict[str, Any]] = None
    disclaimer: str
    supported_symbols: List[str]
    timeframes: List[str]


class FilterResultSchema(BaseModel):
    filter_number: int
    filter_name: str
    status: str
    detected_direction: Optional[str] = None
    indicator_values: Optional[Dict[str, Any]] = None
    explanation: str

    class Config:
        from_attributes = True


class ManualOutcomeSchema(BaseModel):
    id: Optional[int] = None
    signal_id: str
    observed_entry_price: float
    observed_expiry_price: float
    observed_time: datetime.datetime
    user_reported_outcome: str  # WIN, LOSS, TIE
    price_source_description: str = "Quotex Manual Observation"
    notes: Optional[str] = None
    recorded_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class ManualOutcomeCreate(BaseModel):
    observed_entry_price: float
    observed_expiry_price: float
    observed_time: datetime.datetime
    user_reported_outcome: str = Field(..., pattern="^(WIN|LOSS|TIE)$")
    price_source_description: Optional[str] = "Quotex Manual Observation"
    notes: Optional[str] = None


class SignalSchema(BaseModel):
    id: str
    symbol: str
    direction: str  # CALL, PUT, NO TRADE
    created_at: datetime.datetime
    entry_price: float
    expiry_time: datetime.datetime
    data_source: str
    timeframe: str
    rule_agreement_score: float
    strategy_version: str
    data_quality_status: str
    decision_reason: str
    is_evaluated: bool = False
    evaluation_price: Optional[float] = None
    algorithmic_outcome: Optional[str] = None
    evaluated_at: Optional[datetime.datetime] = None
    filters: List[FilterResultSchema] = []
    manual_outcome: Optional[ManualOutcomeSchema] = None
    fear_and_greed: Optional[Dict[str, Any]] = None
    currency_strength: Optional[Dict[str, Any]] = None
    micro_timing_tip: Optional[str] = None
    is_pre_signal: Optional[bool] = False
    pre_signal_direction: Optional[str] = "NONE"
    readiness_score: Optional[float] = 0.0
    pre_signal_message: Optional[str] = None
    recommended_timeframe: Optional[str] = "M1 / M5"
    recommended_expiry_minutes: Optional[int] = 5
    recommended_expiry_description: Optional[str] = None
    timing_guide: Optional[str] = None

    class Config:
        from_attributes = True


class AnalyzeRequest(BaseModel):
    symbol: str
    timeframe: str = "M1"
    force_refresh: bool = False


class BacktestRequest(BaseModel):
    symbol: str = "EUR/USD"
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None
    period_type: str = "DEVELOPMENT"  # DEVELOPMENT, VALIDATION, OUT_OF_SAMPLE, FULL
    payout_ratio: float = 0.85
    min_rule_agreement: int = 4
    strategy_version: str = "1.0.0"


class BacktestTradeSchema(BaseModel):
    symbol: str
    direction: str
    entry_time: datetime.datetime
    entry_price: float
    expiry_time: datetime.datetime
    expiry_price: float
    outcome: str
    rule_score: float
    return_unit: float

    class Config:
        from_attributes = True


class BacktestResponse(BaseModel):
    run_id: str
    symbol: str
    period_type: str
    payout_ratio: float
    total_candles: int
    total_signals: int
    call_signals: int
    put_signals: int
    win_count: int
    loss_count: int
    tie_count: int
    win_rate: float
    wilson_ci_lower: float
    wilson_ci_upper: float
    max_consecutive_losses: int
    net_simulated_return: float
    break_even_rate: float
    rejected_signals_count: int
    missing_data_count: int
    session_breakdown: Dict[str, Any] = {}
    hourly_breakdown: Dict[int, Any] = {}
    volatility_breakdown: Dict[str, Any] = {}
    trades: List[BacktestTradeSchema] = []


class SettingsSchema(BaseModel):
    data_mode: str
    ema_fast_period: int
    ema_slow_period: int
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    macd_fast: int
    macd_slow: int
    macd_signal: int
    atr_period: int
    min_rule_agreement_count: int
    default_payout_ratio: float
    alpha_vantage_api_key: Optional[str] = ""
    twelve_data_api_key: Optional[str] = ""


class SettingsUpdate(BaseModel):
    data_mode: Optional[str] = None
    ema_fast_period: Optional[int] = None
    ema_slow_period: Optional[int] = None
    rsi_period: Optional[int] = None
    rsi_overbought: Optional[float] = None
    rsi_oversold: Optional[float] = None
    macd_fast: Optional[int] = None
    macd_slow: Optional[int] = None
    macd_signal: Optional[int] = None
    atr_period: Optional[int] = None
    min_rule_agreement_count: Optional[int] = None
    default_payout_ratio: Optional[float] = None
    alpha_vantage_api_key: Optional[str] = None
    twelve_data_api_key: Optional[str] = None


class AnalyticsSummary(BaseModel):
    total_signals: int
    evaluated_signals: int
    algorithmic_win_rate: float
    algorithmic_wilson_lower: float
    algorithmic_wilson_upper: float
    algorithmic_net_return: float
    manual_logged_trades: int
    manual_win_rate: float
    manual_wins: int
    manual_losses: int
    manual_ties: int
    recent_signals: List[SignalSchema] = []
    symbol_stats: Dict[str, Any] = {}
