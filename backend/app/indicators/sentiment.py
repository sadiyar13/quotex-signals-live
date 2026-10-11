import numpy as np
import pandas as pd
from typing import Dict, Any
from app.indicators.technical import calculate_rsi, calculate_atr, calculate_ema

def calculate_fear_and_greed_index(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Forex Fear & Greed Index (0 - 100).
    A quantitative multi-factor sentiment model specifically calibrated for Forex:
      1. RSI Momentum Extreme (25% weight)
      2. Distance from EMA50 Mean (25% weight)
      3. Bollinger %B Location (25% weight)
      4. Volatility Expansion / ATR Relative Percentile (25% weight)
    
    Output interpretation:
      0  - 25  : Extreme Fear (ترس شدید - اشباع فروش عمیق)
      26 - 45  : Fear (ترس - فشار نزولی غالب)
      46 - 54  : Neutral (خنثی - تعادل احساسی)
      55 - 75  : Greed (طمع - تمایل صعودی)
      76 - 100 : Extreme Greed (طمع شدید - اشباع خرید افراطی)
    """
    if df.empty or len(df) < 30:
        return {
            "score": 50.0,
            "state": "NEUTRAL",
            "state_fa": "خنثی",
            "color": "#94A3B8",
            "description": "داده‌ها برای محاسبه شاخص احساسات کافی نیست.",
            "components": {},
        }

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # 1. RSI (14)
    rsi_series = calculate_rsi(close, period=14)
    last_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
    rsi_score = np.clip(last_rsi, 0.0, 100.0)

    # 2. Distance from EMA50
    ema50 = calculate_ema(close, period=min(50, len(df)))
    last_close = float(close.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    pct_diff = ((last_close - last_ema50) / last_ema50) * 100.0
    # Map +/- 0.5% forex deviation to 0-100 scale (50 is neutral)
    ema_score = float(np.clip(50.0 + (pct_diff / 0.4) * 50.0, 0.0, 100.0))

    # 3. Bollinger %B (20, 2)
    period_bb = min(20, len(df))
    sma20 = close.rolling(period_bb).mean()
    std20 = close.rolling(period_bb).std(ddof=0).fillna(0.0001)
    upper_b = sma20 + (2.0 * std20)
    lower_b = sma20 - (2.0 * std20)
    bb_width = float(upper_b.iloc[-1] - lower_b.iloc[-1])
    if bb_width > 0:
        pct_b = float((last_close - lower_b.iloc[-1]) / bb_width) * 100.0
    else:
        pct_b = 50.0
    bb_score = float(np.clip(pct_b, 0.0, 100.0))

    # 4. Volatility Sentiment (ATR relative to 50-bar median)
    atr_series = calculate_atr(high, low, close, period=14)
    last_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0005
    median_atr = float(atr_series.rolling(min(30, len(atr_series))).median().iloc[-1]) if not atr_series.empty else last_atr
    vol_ratio = (last_atr / median_atr) if median_atr > 0 else 1.0
    # In up-momentum, high vol = Greed surge; in down-momentum, high vol = Panic/Fear
    if last_close >= last_ema50:
        vol_score = float(np.clip(50.0 + (vol_ratio - 1.0) * 40.0, 0.0, 100.0))
    else:
        vol_score = float(np.clip(50.0 - (vol_ratio - 1.0) * 40.0, 0.0, 100.0))

    # Composite Fear & Greed Score
    composite_score = round(
        (0.30 * rsi_score) + (0.25 * ema_score) + (0.25 * bb_score) + (0.20 * vol_score),
        1
    )

    if composite_score <= 25.0:
        state = "EXTREME_FEAR"
        state_fa = "ترس شدید (Extreme Fear)"
        color = "#EF4444"  # Red
        desc = "فشار فروش افراطی و هیجان منفی شدید. بازار در محدوده اشباع فروش سنگین قرار دارد و پتانسیل جهش بازگشتی صعودی بسیار بالاست."
    elif composite_score <= 45.0:
        state = "FEAR"
        state_fa = "ترس (Fear)"
        color = "#F97316"  # Orange
        desc = "احساسات غالب معامله‌گران متمایل به احتیاط و فروش است."
    elif composite_score <= 55.0:
        state = "NEUTRAL"
        state_fa = "خنثی و متعادل (Neutral)"
        color = "#94A3B8"  # Slate
        desc = "تعادل میان خریداران و فروشندگان؛ بازار در فاز تصمیم‌گیری یا تثبیت قیمت قرار دارد."
    elif composite_score <= 75.0:
        state = "GREED"
        state_fa = "طمع (Greed)"
        color = "#10B981"  # Emerald
        desc = "خوش‌بینی و تقاضای خریداران بر بازار حاکم است."
    else:
        state = "EXTREME_GREED"
        state_fa = "طمع شدید (Extreme Greed)"
        color = "#06B6D4"  # Cyan
        desc = "هیجان خرید افراطی و طمع شدید. قیمت به شدت منبسط شده و احتمال تخلیه هیجان و اصلاح بازگشتی نزولی وجود دارد."

    return {
        "score": composite_score,
        "state": state,
        "state_fa": state_fa,
        "color": color,
        "description": desc,
        "components": {
            "rsi_score": round(rsi_score, 1),
            "trend_distance_score": round(ema_score, 1),
            "bollinger_position_score": round(bb_score, 1),
            "volatility_score": round(vol_score, 1),
        },
    }
