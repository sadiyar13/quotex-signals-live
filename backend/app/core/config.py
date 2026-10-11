import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "Forex Binary Options Smart Signal Dashboard"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Environment & Data Mode
    DATA_MODE: str = "REAL"  # REAL (live/interbank), DEMO_OFFLINE (isolated synthetic)
    DATA_SOURCE_NAME: str = "YAHOO_INTERBANK_REAL"
    
    # Database
    DATABASE_URL: str = f"sqlite:///{DATA_DIR.as_posix()}/signals.db"
    
    # Trading & Market Symbols
    SUPPORTED_SYMBOLS: List[str] = [
        "EUR/USD",
        "GBP/USD",
        "USD/JPY",
        "AUD/USD",
        "USD/CHF",
        "USD/CAD",
        "NZD/USD",
    ]
    
    DEFAULT_TIMEFRAMES: List[str] = ["M1", "M5", "M15"]
    SIGNAL_HORIZON_MINUTES: int = 5
    DEFAULT_PAYOUT_RATIO: float = 0.85  # 85% net payout on win
    
    # Optional External APIs
    ALPHA_VANTAGE_API_KEY: str = ""
    TWELVE_DATA_API_KEY: str = ""
    
    # Strategy Settings (Configurable defaults)
    EMA_FAST_PERIOD: int = 20
    EMA_SLOW_PERIOD: int = 50
    RSI_PERIOD: int = 14
    RSI_OVERBOUGHT: float = 70.0
    RSI_OVERSOLD: float = 30.0
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    ATR_PERIOD: int = 14
    MIN_RULE_AGREEMENT_COUNT: int = 4  # 4 out of 5 filters must agree
    
    # Security & CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
