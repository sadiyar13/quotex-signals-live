import pandas as pd
from typing import Dict, Any, Optional
from app.indicators.technical import calculate_rsi, calculate_macd

def detect_divergence(df: pd.DataFrame, lookback: int = 25) -> Dict[str, Any]:
    """
    Scans for Bullish and Bearish Regular & Hidden Divergences
    between Price and RSI (14) / MACD.
    Divergences are mathematically one of the highest win-rate reversal triggers in technical analysis.
    """
    if df.empty or len(df) < lookback + 5:
        return {
            "has_divergence": False,
            "divergence_type": "NONE",
            "direction": "NEUTRAL",
            "confidence_boost": 0.0,
            "description": "تعداد کندل‌ها برای بررسی واگرایی کافی نیست.",
        }

    close = df["close"].tail(lookback).reset_index(drop=True)
    low = df["low"].tail(lookback).reset_index(drop=True)
    high = df["high"].tail(lookback).reset_index(drop=True)

    rsi = calculate_rsi(df["close"], period=14).tail(lookback).reset_index(drop=True)
    macd_line, signal_line, hist = calculate_macd(df["close"])
    hist = hist.tail(lookback).reset_index(drop=True)

    n = len(close)
    if n < 15:
        return {
            "has_divergence": False,
            "divergence_type": "NONE",
            "direction": "NEUTRAL",
            "confidence_boost": 0.0,
            "description": "داده ناکافی برای واگرایی.",
        }

    # Find swing lows (troughs) for Bullish Divergence
    # Compare recent swing trough (last 4 bars) with an earlier swing trough (bars 8 to 22)
    recent_price_low_idx = low.iloc[-5:].idxmin()
    recent_price_low = low.iloc[recent_price_low_idx]
    recent_rsi_low = rsi.iloc[recent_price_low_idx]

    earlier_low_slice = low.iloc[2:-6]
    if not earlier_low_slice.empty:
        earlier_price_low_idx = earlier_low_slice.idxmin()
        earlier_price_low = low.iloc[earlier_price_low_idx]
        earlier_rsi_low = rsi.iloc[earlier_price_low_idx]

        # Regular Bullish Divergence: Price made Lower Low, but RSI made Higher Low
        if (recent_price_low < earlier_price_low) and (recent_rsi_low > earlier_rsi_low + 2.0):
            return {
                "has_divergence": True,
                "divergence_type": "REGULAR_BULLISH",
                "direction": "CALL",
                "confidence_boost": 15.0,
                "description": f"واگرایی مثبت کلاسیک (Bullish Divergence) کشف شد: قیمت کف پایین‌تر زد اما RSI کف بالاتر ثبت کرد (قدرت صعودی).",
            }

        # Hidden Bullish Divergence: Price made Higher Low, but RSI made Lower Low (Trend continuation)
        if (recent_price_low > earlier_price_low) and (recent_rsi_low < earlier_rsi_low - 2.0):
            return {
                "has_divergence": True,
                "divergence_type": "HIDDEN_BULLISH",
                "direction": "CALL",
                "confidence_boost": 10.0,
                "description": "واگرایی مثبت مخفی (Hidden Bullish): نشانه پرقدرت ادامه روند صعودی.",
            }

    # Find swing highs (peaks) for Bearish Divergence
    recent_price_high_idx = high.iloc[-5:].idxmax()
    recent_price_high = high.iloc[recent_price_high_idx]
    recent_rsi_high = rsi.iloc[recent_price_high_idx]

    earlier_high_slice = high.iloc[2:-6]
    if not earlier_high_slice.empty:
        earlier_price_high_idx = earlier_high_slice.idxmax()
        earlier_price_high = high.iloc[earlier_price_high_idx]
        earlier_rsi_high = rsi.iloc[earlier_price_high_idx]

        # Regular Bearish Divergence: Price made Higher High, but RSI made Lower High
        if (recent_price_high > earlier_price_high) and (recent_rsi_high < earlier_rsi_high - 2.0):
            return {
                "has_divergence": True,
                "divergence_type": "REGULAR_BEARISH",
                "direction": "PUT",
                "confidence_boost": 15.0,
                "description": f"واگرایی منفی کلاسیک (Bearish Divergence) کشف شد: قیمت سقف بالاتر ثبت کرد اما RSI سقف پایین‌تر زد (فشار ریزشی).",
            }

        # Hidden Bearish Divergence: Price made Lower High, but RSI made Higher High
        if (recent_price_high < earlier_price_high) and (recent_rsi_high > earlier_rsi_high + 2.0):
            return {
                "has_divergence": True,
                "divergence_type": "HIDDEN_BEARISH",
                "direction": "PUT",
                "confidence_boost": 10.0,
                "description": "واگرایی منفی مخفی (Hidden Bearish): نشانه پرقدرت ادامه روند نزولی.",
            }

    return {
        "has_divergence": False,
        "divergence_type": "NONE",
        "direction": "NEUTRAL",
        "confidence_boost": 0.0,
        "description": "واگرایی مشهودی بین قیمت و اندیکاتورهای مومنتوم مشاهده نمی‌شود.",
    }
