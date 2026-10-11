import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

def analyze_candlestick_patterns(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Evaluates Japanese Candlestick patterns strictly on the LAST CLOSED CANDLE (index -1)
    and its preceding closed candle (index -2).
    
    Supported Patterns:
      - Bullish Engulfing (پوشای صعودی)
      - Bearish Engulfing (پوشای نزولی)
      - Bullish Pinbar / Hammer (پین‌بار صعودی)
      - Bearish Pinbar / Shooting Star (پین‌بار نزولی)
      - Strong Momentum Candle (کندل پرقدرت جهت‌دار)
    """
    if len(df) < 2:
        return {
            "pattern": "NONE",
            "direction": "NEUTRAL",
            "strength": 0.0,
            "description": "داده ناکافی برای تحلیل الگوهای کندلی",
        }

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    curr_o, curr_h, curr_l, curr_c = float(curr["open"]), float(curr["high"]), float(curr["low"]), float(curr["close"])
    prev_o, prev_h, prev_l, prev_c = float(prev["open"]), float(prev["high"]), float(prev["low"]), float(prev["close"])

    curr_body = abs(curr_c - curr_o)
    curr_range = curr_h - curr_l
    prev_body = abs(prev_c - prev_o)

    curr_upper_shadow = curr_h - max(curr_o, curr_c)
    curr_lower_shadow = min(curr_o, curr_c) - curr_l

    is_curr_bullish = curr_c > curr_o
    is_curr_bearish = curr_c < curr_o
    is_prev_bullish = prev_c > prev_o
    is_prev_bearish = prev_c < prev_o

    # Avoid zero division
    if curr_range <= 1e-6:
        return {
            "pattern": "DOJI",
            "direction": "NEUTRAL",
            "strength": 0.0,
            "description": "کندل بدون نوسان (دوجی متوقف)",
        }

    # 1. Bullish Engulfing
    if is_prev_bearish and is_curr_bullish:
        if curr_o <= prev_c and curr_c >= prev_o and curr_body > prev_body:
            return {
                "pattern": "BULLISH_ENGULFING",
                "direction": "CALL",
                "strength": 0.9,
                "description": "الگوی پوشای صعودی (Bullish Engulfing) با پوشش کامل کندل نزولی قبل",
            }

    # 2. Bearish Engulfing
    if is_prev_bullish and is_curr_bearish:
        if curr_o >= prev_c and curr_c <= prev_o and curr_body > prev_body:
            return {
                "pattern": "BEARISH_ENGULFING",
                "direction": "PUT",
                "strength": 0.9,
                "description": "الگوی پوشای نزولی (Bearish Engulfing) با پوشش کامل کندل صعودی قبل",
            }

    # 3. Bullish Pinbar (Hammer)
    # Lower shadow is at least 2x the body, upper shadow is small, close is in top 40% of range
    if curr_lower_shadow >= 2.0 * max(curr_body, 1e-5) and curr_upper_shadow <= 0.8 * curr_body:
        close_pos = (curr_c - curr_l) / curr_range
        if close_pos >= 0.60:
            return {
                "pattern": "BULLISH_PINBAR",
                "direction": "CALL",
                "strength": 0.85,
                "description": "الگوی پین‌بار صعودی (سایه پایینی بلند بیش از ۲ برابر بدنه با ریجکت کف)",
            }

    # 4. Bearish Pinbar (Shooting Star)
    # Upper shadow is at least 2x the body, lower shadow is small, close is in bottom 40% of range
    if curr_upper_shadow >= 2.0 * max(curr_body, 1e-5) and curr_lower_shadow <= 0.8 * curr_body:
        close_pos = (curr_c - curr_l) / curr_range
        if close_pos <= 0.40:
            return {
                "pattern": "BEARISH_PINBAR",
                "direction": "PUT",
                "strength": 0.85,
                "description": "الگوی پین‌بار نزولی (سایه بالایی بلند بیش از ۲ برابر بدنه با ریجکت سقف)",
            }

    # 5. Strong Momentum Candle
    body_ratio = curr_body / curr_range
    if body_ratio >= 0.70:
        if is_curr_bullish:
            return {
                "pattern": "BULLISH_MARUBOZU",
                "direction": "CALL",
                "strength": 0.75,
                "description": "کندل پرقدرت صعودی ممنتومی با بدنه بزرگ بیش از ۷۰ درصد دامنه",
            }
        elif is_curr_bearish:
            return {
                "pattern": "BEARISH_MARUBOZU",
                "direction": "PUT",
                "strength": 0.75,
                "description": "کندل پرقدرت نزولی ممنتومی با بدنه بزرگ بیش از ۷۰ درصد دامنه",
            }

    # Default: Neutral
    return {
        "pattern": "NEUTRAL_CANDLE",
        "direction": "NEUTRAL",
        "strength": 0.3,
        "description": "کندل عادی بدون الگوی تأیید شاخص",
    }
