import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA) with span=period.
    Uses adjust=False for classic recursive EMA.
    Returns NaN for early periods where data is insufficient.
    """
    if len(series) < period:
        return pd.Series(np.nan, index=series.index)
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI) using Wilder's Smoothing.
    Formula:
      RS = Smoothed Gain / Smoothed Loss
      RSI = 100 - (100 / (1 + RS))
    """
    if len(series) < period + 1:
        return pd.Series(np.nan, index=series.index)

    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing via ewm alpha=1/period
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    fill_vals = pd.Series(np.where(avg_gain == 0, 0.0, 100.0), index=rsi.index)
    rsi = rsi.fillna(fill_vals)
    return rsi


def calculate_macd(
    series: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD:
      macd_line = EMA(fast) - EMA(slow)
      signal_line = EMA(macd_line, signal_period)
      histogram = macd_line - signal_line
    """
    if len(series) < slow_period + signal_period:
        nan_s = pd.Series(np.nan, index=series.index)
        return nan_s, nan_s, nan_s

    fast_ema = calculate_ema(series, fast_period)
    slow_ema = calculate_ema(series, slow_period)
    macd_line = fast_ema - slow_ema
    signal_line = calculate_ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Calculate Average True Range (ATR) with period=14 using Wilder's smoothing.
    TR = max(High - Low, abs(High - PrevClose), abs(Low - PrevClose))
    """
    if len(high) < period + 1:
        return pd.Series(np.nan, index=high.index)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Average Directional Index (ADX) and +DI / -DI.
    ADX < 20: Chop / Range (High risk in binary options!)
    ADX >= 25: Strong Trending Market
    """
    if len(high) < period * 2:
        nan_s = pd.Series(np.nan, index=high.index)
        return nan_s, nan_s, nan_s

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    # Directional Movement
    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # True Range
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    tr_smoothed = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    plus_di = 100.0 * (pd.Series(plus_dm, index=high.index).ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / tr_smoothed)
    minus_di = 100.0 * (pd.Series(minus_dm, index=high.index).ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / tr_smoothed)

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().fillna(20.0)

    return adx, plus_di.fillna(0.0), minus_di.fillna(0.0)


def compute_all_indicators(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Computes all standard indicators on a DataFrame containing ['open', 'high', 'low', 'close'].
    Appends new columns:
      - ema_fast, ema_slow
      - rsi
      - macd_line, macd_signal, macd_hist
      - atr
      - adx, plus_di, minus_di
    """
    res = df.copy()
    close = res["close"]
    high = res["high"]
    low = res["low"]

    res[f"ema_{ema_fast}"] = calculate_ema(close, ema_fast)
    res[f"ema_{ema_slow}"] = calculate_ema(close, ema_slow)
    res["rsi"] = calculate_rsi(close, rsi_period)

    m_line, s_line, m_hist = calculate_macd(close, macd_fast, macd_slow, macd_signal)
    res["macd_line"] = m_line
    res["macd_signal"] = s_line
    res["macd_hist"] = m_hist

    res["atr"] = calculate_atr(high, low, close, atr_period)
    adx_s, plus_di, minus_di = calculate_adx(high, low, close, period=14)
    res["adx"] = adx_s
    res["plus_di"] = plus_di
    res["minus_di"] = minus_di
    return res
