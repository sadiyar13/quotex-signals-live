"""
Advanced High-Precision Oscillators:
  1. Stochastic Momentum Oscillator (%K, %D - Fast & Slow)
  2. Commodity Channel Index (CCI-14 & CCI-50)
  3. Triple Oscillator Confluence (Stochastic + CCI + RSI)
"""

from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd


def calculate_stochastic(
    df: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> Dict[str, Any]:
    """
    Computes Slow Stochastic Oscillator (%K and %D).
    %K = SMA( (Close - Lowest Low) / (Highest High - Lowest Low) * 100, smooth_k )
    %D = SMA(%K, d_period)
    """
    if len(df) < k_period + smooth_k + d_period:
        return {
            "k": 50.0,
            "d": 50.0,
            "is_overbought": False,
            "is_oversold": False,
            "cross_direction": "NEUTRAL",
            "explanation": "داده‌های کافی برای محاسبه استوکاستیک موجود نیست."
        }

    highs = df["high"].rolling(window=k_period).max()
    lows = df["low"].rolling(window=k_period).min()
    denominator = highs - lows
    # Avoid zero division
    denominator = denominator.replace(0, np.nan).fillna(0.00001)

    raw_k = ((df["close"] - lows) / denominator) * 100.0
    slow_k = raw_k.rolling(window=smooth_k).mean().fillna(50.0)
    slow_d = slow_k.rolling(window=d_period).mean().fillna(50.0)

    curr_k = float(slow_k.iloc[-1])
    curr_d = float(slow_d.iloc[-1])
    prev_k = float(slow_k.iloc[-2]) if len(slow_k) > 1 else curr_k
    prev_d = float(slow_d.iloc[-2]) if len(slow_d) > 1 else curr_d

    is_overbought = curr_k >= 80.0
    is_oversold = curr_k <= 20.0

    # Cross detection
    cross_direction = "NEUTRAL"
    if prev_k <= prev_d and curr_k > curr_d and (curr_k <= 35.0 or prev_k <= 25.0):
        cross_direction = "CALL"  # Bullish crossover from oversold
    elif prev_k >= prev_d and curr_k < curr_d and (curr_k >= 65.0 or prev_k >= 75.0):
        cross_direction = "PUT"  # Bearish crossover from overbought

    return {
        "k": round(curr_k, 2),
        "d": round(curr_d, 2),
        "prev_k": round(prev_k, 2),
        "prev_d": round(prev_d, 2),
        "is_overbought": is_overbought,
        "is_oversold": is_oversold,
        "cross_direction": cross_direction,
        "explanation": f"استوکاستیک %K={curr_k:.1f} و %D={curr_d:.1f}" + (
            " (تقاطع صعودی در اشباع فروش)" if cross_direction == "CALL" else
            " (تقاطع نزولی در اشباع خرید)" if cross_direction == "PUT" else ""
        )
    }


def calculate_cci(df: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
    """
    Computes Commodity Channel Index (CCI).
    Typical Price (TP) = (High + Low + Close) / 3
    CCI = (TP - SMA(TP)) / (0.015 * Mean Deviation)
    """
    if len(df) < period + 5:
        return {
            "cci": 0.0,
            "is_overbought": False,
            "is_oversold": False,
            "direction": "NEUTRAL",
            "explanation": "داده‌های کافی برای محاسبه CCI موجود نیست."
        }

    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    sma_tp = tp.rolling(window=period).mean()
    
    # Calculate Mean Absolute Deviation (MAD)
    mad = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    mad = mad.replace(0, np.nan).fillna(0.00001)

    cci_series = (tp - sma_tp) / (0.015 * mad)
    cci_series = cci_series.fillna(0.0)

    curr_cci = float(cci_series.iloc[-1])
    prev_cci = float(cci_series.iloc[-2]) if len(cci_series) > 1 else curr_cci

    is_overbought = curr_cci >= 100.0
    is_oversold = curr_cci <= -100.0

    direction = "NEUTRAL"
    if prev_cci <= -100.0 and curr_cci > -100.0:
        direction = "CALL"  # Hook reversal exiting oversold
    elif prev_cci >= 100.0 and curr_cci < 100.0:
        direction = "PUT"  # Hook reversal exiting overbought
    elif curr_cci <= -150.0:
        direction = "CALL"  # Extreme panic sell climax
    elif curr_cci >= 150.0:
        direction = "PUT"  # Extreme greed blow-off top

    return {
        "cci": round(curr_cci, 2),
        "prev_cci": round(prev_cci, 2),
        "is_overbought": is_overbought,
        "is_oversold": is_oversold,
        "direction": direction,
        "explanation": f"شاخص CCI={curr_cci:.1f}" + (
            " (سیگنال برگشت از محدوده اشباع فروش)" if direction == "CALL" else
            " (سیگنال برگشت از محدوده اشباع خرید)" if direction == "PUT" else ""
        )
    }


def analyze_confluence_oscillators(df: pd.DataFrame, rsi_val: float = 50.0) -> Dict[str, Any]:
    """
    Evaluates multi-oscillator alignment across Stochastic, CCI, and RSI.
    High-win-rate trigger when at least 2 oscillators agree on extreme exhaustion/reversal.
    """
    stoch = calculate_stochastic(df)
    cci = calculate_cci(df)

    call_points = 0
    put_points = 0

    if stoch["cross_direction"] == "CALL":
        call_points += 2
    elif stoch["is_oversold"]:
        call_points += 1

    if stoch["cross_direction"] == "PUT":
        put_points += 2
    elif stoch["is_overbought"]:
        put_points += 1

    if cci["direction"] == "CALL":
        call_points += 2
    elif cci["is_oversold"]:
        call_points += 1

    if cci["direction"] == "PUT":
        put_points += 2
    elif cci["is_overbought"]:
        put_points += 1

    # RSI support
    if rsi_val <= 35.0:
        call_points += 1
    elif rsi_val >= 65.0:
        put_points += 1

    direction = "NEUTRAL"
    if call_points >= 3 and call_points > put_points:
        direction = "CALL"
    elif put_points >= 3 and put_points > call_points:
        direction = "PUT"

    return {
        "direction": direction,
        "call_points": call_points,
        "put_points": put_points,
        "stochastic": stoch,
        "cci": cci,
        "rsi": round(rsi_val, 2),
        "explanation": f"همگرایی اسیلاتورها: استوکاستیک ({stoch['k']:.1f}/{stoch['d']:.1f})، شاخص CCI ({cci['cci']:.1f})، و RSI ({rsi_val:.1f})"
    }
