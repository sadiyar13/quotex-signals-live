import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from app.database.session import Base

class CandleRecord(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String(20), index=True, nullable=False)
    timeframe = Column(String(10), index=True, nullable=False)  # M1, M5, M15
    timestamp = Column(DateTime, index=True, nullable=False)    # UTC timestamp of candle open
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True, default=0.0)
    data_source = Column(String(50), nullable=False, default="DEMO")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_symbol_tf_ts", "symbol", "timeframe", "timestamp", unique=True),
    )


class SignalRecord(Base):
    __tablename__ = "signals"

    id = Column(String(64), primary_key=True, index=True)  # UUID or deterministic hash
    symbol = Column(String(20), index=True, nullable=False)
    direction = Column(String(10), index=True, nullable=False)  # CALL, PUT, NO TRADE
    created_at = Column(DateTime, index=True, nullable=False)   # UTC creation time
    entry_price = Column(Float, nullable=False)
    expiry_time = Column(DateTime, index=True, nullable=False)  # UTC 5m expiry time
    data_source = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False, default="M1")
    rule_agreement_score = Column(Float, nullable=False, default=0.0)
    strategy_version = Column(String(20), nullable=False, default="1.0.0")
    data_quality_status = Column(String(20), nullable=False, default="VALID")
    decision_reason = Column(Text, nullable=False)
    
    # Paper Trading / Algorithmic Evaluation
    is_evaluated = Column(Boolean, default=False, index=True)
    evaluation_price = Column(Float, nullable=True)
    algorithmic_outcome = Column(String(10), nullable=True)  # WIN, LOSS, TIE, PENDING
    evaluated_at = Column(DateTime, nullable=True)

    # Relationships
    filters = relationship("FilterResultRecord", back_populates="signal", cascade="all, delete-orphan")
    manual_outcome = relationship("ManualOutcomeRecord", back_populates="signal", uselist=False, cascade="all, delete-orphan")


class FilterResultRecord(Base):
    __tablename__ = "filter_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(64), ForeignKey("signals.id"), index=True, nullable=False)
    filter_number = Column(Integer, nullable=False)  # 1 to 5
    filter_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)      # PASS, FAIL, CONFLICT, INSUFFICIENT_DATA
    detected_direction = Column(String(10), nullable=True)  # CALL, PUT, NEUTRAL
    indicator_values = Column(Text, nullable=True)  # JSON-encoded indicators
    explanation = Column(Text, nullable=False)

    signal = relationship("SignalRecord", back_populates="filters")


class ManualOutcomeRecord(Base):
    __tablename__ = "manual_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(64), ForeignKey("signals.id"), unique=True, index=True, nullable=False)
    observed_entry_price = Column(Float, nullable=False)
    observed_expiry_price = Column(Float, nullable=False)
    observed_time = Column(DateTime, nullable=False)
    user_reported_outcome = Column(String(10), nullable=False)  # WIN, LOSS, TIE
    price_source_description = Column(String(100), nullable=False, default="Quotex Manual Observation")
    notes = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)

    signal = relationship("SignalRecord", back_populates="manual_outcome")


class BacktestRunRecord(Base):
    __tablename__ = "backtest_runs"

    id = Column(String(64), primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    period_type = Column(String(20), nullable=False)  # DEVELOPMENT, VALIDATION, OUT_OF_SAMPLE, FULL
    payout_ratio = Column(Float, nullable=False, default=0.85)
    strategy_version = Column(String(20), nullable=False, default="1.0.0")
    parameters_json = Column(Text, nullable=True)
    
    # Summary Metrics
    total_candles = Column(Integer, default=0)
    total_signals = Column(Integer, default=0)
    call_signals = Column(Integer, default=0)
    put_signals = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    tie_count = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    wilson_ci_lower = Column(Float, default=0.0)
    wilson_ci_upper = Column(Float, default=0.0)
    max_consecutive_losses = Column(Integer, default=0)
    net_simulated_return = Column(Float, default=0.0)
    break_even_rate = Column(Float, default=0.0)
    rejected_signals_count = Column(Integer, default=0)
    missing_data_count = Column(Integer, default=0)
    summary_report_json = Column(Text, nullable=True)

    trades = relationship("BacktestTradeRecord", back_populates="run", cascade="all, delete-orphan")


class BacktestTradeRecord(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("backtest_runs.id"), index=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)  # CALL, PUT
    entry_time = Column(DateTime, nullable=False)
    entry_price = Column(Float, nullable=False)
    expiry_time = Column(DateTime, nullable=False)
    expiry_price = Column(Float, nullable=False)
    outcome = Column(String(10), nullable=False)  # WIN, LOSS, TIE
    rule_score = Column(Float, nullable=False)
    return_unit = Column(Float, nullable=False)  # +P or -1.0 or 0.0

    run = relationship("BacktestRunRecord", back_populates="trades")


class AppSettingRecord(Base):
    __tablename__ = "app_settings"

    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class DataSourceHealthRecord(Base):
    __tablename__ = "data_source_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False)  # OK, DEGRADED, DOWN, RATE_LIMITED
    latency_ms = Column(Float, nullable=False, default=0.0)
    last_successful_sync = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
