import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd

class BaseDataProvider(ABC):
    """
    Abstract base interface for all market data providers (Demo, Delayed, Live).
    Ensures that any new data source can be plugged in without changing the core strategy engine.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for the data source."""
        pass

    @property
    @abstractmethod
    def is_demo(self) -> bool:
        """Whether this provider produces synthetic or simulated demo data."""
        pass

    @abstractmethod
    def fetch_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 120,
        end_time: Optional[datetime.datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetches historical OHLCV candles sorted strictly ascending by timestamp.
        DataFrame must contain columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume'].
        All timestamps MUST be UTC.
        """
        pass

    @abstractmethod
    def fetch_latest_candle(
        self,
        symbol: str,
        timeframe: str,
    ) -> Dict[str, Any]:
        """
        Fetches the latest completed/closed candle for the symbol.
        """
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """
        Checks connectivity, returns latency_ms, status (OK, DEGRADED, DOWN), and details.
        """
        pass
