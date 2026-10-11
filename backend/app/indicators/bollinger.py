import pandas as pd
from typing import Dict, Any

def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict[str, Any]:
    """
    Bollinger Bands (20, 2.0) Volatility Exhaustion & Reversion Indicator.
    Statistical probability of price staying within 2 std deviations is ~95.4%.
    When price pierces the outer band and then prints a reversal wick/candle back inside,
    the 5-minute mean-reversion probability reaches its highest statistical edge.
    """
    if df.empty or len(df) < period:
        return {
            "middle": 0.0,
            "upper": 0.0,
            "lower": 0.0,
            "percent_b": 0.5,
            "bandwidth": 0.0,
            "setup": "NONE",
            "direction": "NEUTRAL",
            "explanation": "داده‌ها برای باندهای بولینگر ناکافی است.",
        }

    close = df["close"]
    high = df["high"]
    low = df["low"]

    sma = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0).fillna(0.0001)

    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)

    last_close = float(close.iloc[-1])
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_mid = float(sma.iloc[-1])
    last_up = float(upper.iloc[-1])
    last_low_b = float(lower.iloc[-1])

    bw = (last_up - last_low_b) / last_mid if last_mid > 0 else 0.0
    pct_b = (last_close - last_low_b) / (last_up - last_low_b) if (last_up - last_low_b) > 0 else 0.5

    setup = "NORMAL"
    direction = "NEUTRAL"
    explanation = "قیمت در میانه باندهای بولینگر در حال نوسان طبیعی است."

    # Check for upper band rejection (Overbought exhaustion -> PUT)
    prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close
    prev_high = float(high.iloc[-2]) if len(high) > 1 else last_high
    prev_low = float(low.iloc[-2]) if len(low) > 1 else last_low
    prev_up = float(upper.iloc[-2]) if len(upper) > 1 else last_up
    prev_low_b = float(lower.iloc[-2]) if len(lower) > 1 else last_low_b

    if prev_high >= prev_up and last_close < last_up:
        setup = "UPPER_BAND_REJECTION"
        direction = "PUT"
        explanation = "واکنش بازگشتی به باند بالای بولینگر (Exhaustion Rejection): قیمت از باند خارج شد و به درون باند پس زده شد (سیگنال PUT)."
    elif prev_low <= prev_low_b and last_close > last_low_b:
        setup = "LOWER_BAND_REJECTION"
        direction = "CALL"
        explanation = "واکنش بازگشتی به باند پایین بولینگر (Exhaustion Bounce): قیمت از کف باند خارج شد و به درون باند بازگشت (سیگنال CALL)."
    elif pct_b > 0.95:
        setup = "BAND_OVERBOUGHT"
        direction = "PUT"
        explanation = "اشباع خرید شدید در مجاورت ۹۵٪ باند بالایی بولینگر."
    elif pct_b < 0.05:
        setup = "BAND_OVERSOLD"
        direction = "CALL"
        explanation = "اشباع فروش شدید در مجاورت ۵٪ باند پایینی بولینگر."

    return {
        "middle": round(last_mid, 5),
        "upper": round(last_up, 5),
        "lower": round(last_low_b, 5),
        "percent_b": round(pct_b, 3),
        "bandwidth": round(bw, 5),
        "setup": setup,
        "direction": direction,
        "explanation": explanation,
    }
