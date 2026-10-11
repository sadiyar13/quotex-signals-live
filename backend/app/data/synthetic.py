import datetime
import math
import hashlib
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from app.data.base import BaseDataProvider

BASE_PRICES = {
    "EUR/USD": 1.08500,
    "GBP/USD": 1.28800,
    "USD/JPY": 153.200,
    "AUD/USD": 0.65400,
    "USD/CHF": 0.88400,
    "USD/CAD": 1.38200,
    "NZD/USD": 0.59600,
}

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
}

class SyntheticDemoDataProvider(BaseDataProvider):
    """
    Realistic Forex Microstructure Generator for Demo/Development Mode.
    Generates authentic-looking candlestick patterns, trends, mean-reversion,
    and session-dependent volatility (London/NY overlap vs Asian session).
    
    CRITICAL: Clearly flagged as is_demo=True and DEMO_SYNTHETIC.
    Never claimed as real live quotes.
    """

    def __init__(self, seed: Optional[int] = None):
        self._seed = seed or 42

    @property
    def source_name(self) -> str:
        return "DEMO_SYNTHETIC_MICROSTRUCTURE"

    @property
    def is_demo(self) -> bool:
        return True

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "OK",
            "latency_ms": 1.5,
            "last_successful_sync": datetime.datetime.utcnow(),
            "message": "Demo synthetic generator active (حالت شبیه‌سازی آموزشی)",
            "is_demo": True,
        }

    def _get_symbol_seed(self, symbol: str) -> int:
        h = int(hashlib.md5(symbol.encode("utf-8")).hexdigest()[:8], 16)
        return (self._seed + h) % 1000000

    def fetch_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 150,
        end_time: Optional[datetime.datetime] = None,
    ) -> pd.DataFrame:
        tf_mins = TIMEFRAME_MINUTES.get(timeframe.upper(), 1)
        now = end_time or datetime.datetime.utcnow()

        # Align to the most recently closed candle
        # e.g., if now is 12:04:35 and tf is M5, last closed candle is 12:00:00 (opened at 11:55:00)
        now_ts = now.timestamp()
        tf_seconds = tf_mins * 60
        last_closed_ts = math.floor(now_ts / tf_seconds) * tf_seconds

        timestamps = [
            datetime.datetime.utcfromtimestamp(last_closed_ts - (count - 1 - i) * tf_seconds)
            for i in range(count)
        ]

        base_price = BASE_PRICES.get(symbol.upper(), 1.1000)
        is_jpy = "JPY" in symbol.upper()
        pip_unit = 0.01 if is_jpy else 0.0001
        round_decimals = 3 if is_jpy else 5

        sym_seed = self._get_symbol_seed(symbol)
        rng = np.random.RandomState(sym_seed)

        # Generate a realistic Forex series using combined wave oscillations + Ornstein-Uhlenbeck drift
        t_indices = np.arange(count, dtype=float)
        # Macro waves (simulating support and resistance cycles)
        cycle1 = np.sin(t_indices / 18.0) * 15 * pip_unit
        cycle2 = np.cos(t_indices / 7.0) * 8 * pip_unit
        
        # Session volatility factor based on hour of day
        candles_data = []
        current_price = base_price + cycle1[0] + cycle2[0]

        for i, dt in enumerate(timestamps):
            hour = dt.hour
            # Higher volatility during London (08-16 UTC) & NY (13-21 UTC)
            if 8 <= hour <= 17:
                vol_mult = 1.3
            elif 0 <= hour <= 7:
                vol_mult = 0.7  # Asian session
            else:
                vol_mult = 0.9

            drift = (cycle1[i] + cycle2[i] - (current_price - base_price)) * 0.1
            noise = rng.normal(0, 3.5 * pip_unit * vol_mult * math.sqrt(tf_mins))
            
            c_open = current_price
            c_close = c_open + drift + noise
            
            wick_high = abs(rng.exponential(2.0 * pip_unit * vol_mult))
            wick_low = abs(rng.exponential(2.0 * pip_unit * vol_mult))
            
            c_high = max(c_open, c_close) + wick_high
            c_low = min(c_open, c_close) - wick_low
            
            vol = round(float(rng.uniform(100, 500) * vol_mult), 1)

            candles_data.append({
                "timestamp": dt,
                "open": round(float(c_open), round_decimals),
                "high": round(float(c_high), round_decimals),
                "low": round(float(c_low), round_decimals),
                "close": round(float(c_close), round_decimals),
                "volume": vol,
            })
            current_price = c_close

        df = pd.DataFrame(candles_data)
        return df

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
