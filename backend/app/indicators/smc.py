"""
Smart Money Concepts (SMC) & ICT Analysis Engine for Binary Options & Forex.
Focuses on:
  1. Fair Value Gaps (FVG / Imbalances)
  2. Order Blocks (OB - Institutional footprints)
  3. Liquidity Sweeps (Stop Hunts & Wick Rejections)
  4. Market Structure Shift (MSS / CHoCH)

Zero lookahead bias: Strictly evaluates closed historical candles.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def detect_fair_value_gaps(df: pd.DataFrame, min_gap_pips: float = 0.0001) -> Dict[str, Any]:
    """
    Detects Fair Value Gaps (FVG) across recent closed candles.
    Bullish FVG: Low of candle [i] > High of candle [i-2] (Gap between candle 1 high and candle 3 low)
    Bearish FVG: High of candle [i] < Low of candle [i-2] (Gap between candle 1 low and candle 3 high)
    
    Checks if the most recent closed candle has tested or mitigated an active FVG.
    """
    if len(df) < 10:
        return {
            "has_fvg": False,
            "fvg_type": "NONE",
            "active_gaps": [],
            "mitigation_status": "NONE",
            "direction": "NEUTRAL",
            "fvg_score": 0.0,
            "explanation": "داده‌های کندلی کافی برای محاسبه FVG وجود ندارد."
        }

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values

    active_gaps = []
    n = len(df)

    # Scan last 25 closed candles (excluding current unclosed)
    for i in range(max(2, n - 25), n):
        # Bullish FVG
        if lows[i] > highs[i - 2]:
            gap_size = lows[i] - highs[i - 2]
            if gap_size >= min_gap_pips:
                active_gaps.append({
                    "index": i,
                    "type": "BULLISH_FVG",
                    "top": float(lows[i]),
                    "bottom": float(highs[i - 2]),
                    "size": float(gap_size),
                })
        # Bearish FVG
        elif highs[i] < lows[i - 2]:
            gap_size = lows[i - 2] - highs[i - 2]
            if gap_size >= min_gap_pips:
                active_gaps.append({
                    "index": i,
                    "type": "BEARISH_FVG",
                    "top": float(lows[i - 2]),
                    "bottom": float(highs[i]),
                    "size": float(gap_size),
                })

    current_close = float(closes[-1])
    current_low = float(lows[-1])
    current_high = float(highs[-1])

    detected_direction = "NEUTRAL"
    fvg_type = "NONE"
    mitigation_status = "NONE"
    fvg_score = 0.0
    explanation = "شکاف ارزش منصفانه (FVG) فعالی در مجاورت قیمت یافت نشد."

    # Check recent unmitigated gaps relative to current price
    for gap in reversed(active_gaps):
        if gap["type"] == "BULLISH_FVG":
            # Price pulled back into Bullish FVG and bounced (Low touches gap, Close remains inside or above)
            if current_low <= gap["top"] and current_close >= gap["bottom"]:
                detected_direction = "CALL"
                fvg_type = "BULLISH_FVG"
                mitigation_status = "TESTING_BULLISH_FVG"
                fvg_score = 85.0
                explanation = f"قیمت به ناحیه شکاف ارزش منصفانه صعودی (Bullish FVG: {gap['bottom']:.5f} - {gap['top']:.5f}) پولبک زده و حمایت شده است."
                break
        elif gap["type"] == "BEARISH_FVG":
            # Price rallied into Bearish FVG and rejected (High touches gap, Close remains inside or below)
            if current_high >= gap["bottom"] and current_close <= gap["top"]:
                detected_direction = "PUT"
                fvg_type = "BEARISH_FVG"
                mitigation_status = "TESTING_BEARISH_FVG"
                fvg_score = 85.0
                explanation = f"قیمت به ناحیه شکاف ارزش منصفانه نزولی (Bearish FVG: {gap['bottom']:.5f} - {gap['top']:.5f}) پولبک زده و ریجکت شده است."
                break

    return {
        "has_fvg": fvg_score > 0,
        "fvg_type": fvg_type,
        "active_gaps": active_gaps[-3:],
        "mitigation_status": mitigation_status,
        "direction": detected_direction,
        "fvg_score": fvg_score,
        "explanation": explanation,
    }


def detect_order_blocks(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detects Institutional Order Blocks (OB).
    Bullish OB: The last down candle before an explosive upward expansion that broke swing high.
    Bearish OB: The last up candle before an explosive downward impulse that broke swing low.
    """
    if len(df) < 20:
        return {
            "has_order_block": False,
            "ob_type": "NONE",
            "direction": "NEUTRAL",
            "ob_level": 0.0,
            "explanation": "داده‌های کافی برای رهگیری اردر بلاک وجود ندارد."
        }

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    current_price = float(closes[-1])
    current_low = float(lows[-1])
    current_high = float(highs[-1])

    # Search for dominant displacement candles in last 15 bars
    bullish_obs = []
    bearish_obs = []

    for i in range(n - 15, n - 2):
        body_size = abs(closes[i] - opens[i])
        avg_body = np.mean([abs(closes[j] - opens[j]) for j in range(max(0, i - 5), i)])
        
        # Bullish displacement
        if closes[i] > opens[i] and body_size > 1.4 * avg_body:
            # Previous candle is the candidate Bullish Order Block
            ob_idx = i - 1
            if closes[ob_idx] <= opens[ob_idx]: # Bearish candle prior to pump
                bullish_obs.append({
                    "top": float(highs[ob_idx]),
                    "bottom": float(lows[ob_idx]),
                    "open": float(opens[ob_idx]),
                    "close": float(closes[ob_idx]),
                })
        # Bearish displacement
        elif closes[i] < opens[i] and body_size > 1.4 * avg_body:
            # Previous candle is candidate Bearish Order Block
            ob_idx = i - 1
            if closes[ob_idx] >= opens[ob_idx]: # Bullish candle prior to dump
                bearish_obs.append({
                    "top": float(highs[ob_idx]),
                    "bottom": float(lows[ob_idx]),
                    "open": float(opens[ob_idx]),
                    "close": float(closes[ob_idx]),
                })

    detected_direction = "NEUTRAL"
    ob_type = "NONE"
    ob_level = 0.0
    explanation = "قیمت در حال حاضر خارج از محدوده اردر بلاک‌های موسساتی قرار دارد."

    # Check proximity to recent Bullish OB
    if bullish_obs:
        recent_ob = bullish_obs[-1]
        # Current price within or testing the OB
        if current_low <= recent_ob["top"] and current_price >= recent_ob["bottom"]:
            detected_direction = "CALL"
            ob_type = "BULLISH_ORDER_BLOCK"
            ob_level = recent_ob["top"]
            explanation = f"قیمت به اردر بلاک صعودی بانک‌ها ({recent_ob['bottom']:.5f} - {recent_ob['top']:.5f}) برخورد کرده و پتانسیل پرتاب به بالا دارد."

    # Check proximity to recent Bearish OB
    if bearish_obs and detected_direction == "NEUTRAL":
        recent_ob = bearish_obs[-1]
        if current_high >= recent_ob["bottom"] and current_price <= recent_ob["top"]:
            detected_direction = "PUT"
            ob_type = "BEARISH_ORDER_BLOCK"
            ob_level = recent_ob["bottom"]
            explanation = f"قیمت به اردر بلاک نزولی بانک‌ها ({recent_ob['bottom']:.5f} - {recent_ob['top']:.5f}) برخورد کرده و پتانسیل ریزش شدید دارد."

    return {
        "has_order_block": detected_direction != "NEUTRAL",
        "ob_type": ob_type,
        "direction": detected_direction,
        "ob_level": ob_level,
        "explanation": explanation,
    }


def detect_liquidity_sweep(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detects Liquidity Sweeps (Stop Hunts / Wick Rejections):
    - Bullish Sweep (Sell-side liquidity sweep): Price penetrates below prior swing low with wick,
      then quickly closes back above the level (rejection wick > 50% of candle range).
    - Bearish Sweep (Buy-side liquidity sweep): Price spikes above prior swing high with wick,
      then quickly closes back below the level.
    """
    if len(df) < 20:
        return {
            "has_sweep": False,
            "sweep_type": "NONE",
            "direction": "NEUTRAL",
            "explanation": "داده کافی برای پایش نقدینگی استاپ‌ها وجود ندارد."
        }

    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values

    last_idx = len(df) - 1
    candle_high = highs[last_idx]
    candle_low = lows[last_idx]
    candle_open = opens[last_idx]
    candle_close = closes[last_idx]
    candle_range = candle_high - candle_low

    if candle_range <= 0.00001:
        return {
            "has_sweep": False,
            "sweep_type": "NONE",
            "direction": "NEUTRAL",
            "explanation": "دامنه کندل ناچیز است."
        }

    # Find swing highs and lows in past 15 candles prior to last candle
    prior_highs = highs[max(0, last_idx - 15):last_idx]
    prior_lows = lows[max(0, last_idx - 15):last_idx]

    swing_high = float(np.max(prior_highs))
    swing_low = float(np.min(prior_lows))

    lower_wick = min(candle_open, candle_close) - candle_low
    upper_wick = candle_high - max(candle_open, candle_close)

    # Bullish Liquidity Sweep (Swept sell-stops below swing low, long lower shadow, closed back up)
    if candle_low < swing_low and candle_close > swing_low and (lower_wick / candle_range) >= 0.45:
        return {
            "has_sweep": True,
            "sweep_type": "SELL_SIDE_LIQUIDITY_SWEEP",
            "direction": "CALL",
            "explanation": f"شکار نقدینگی فروشندگان (استاپ‌هانت کف {swing_low:.5f}) رخ داد؛ بازگشت فوری قیمت با سایه بلند خرید."
        }

    # Bearish Liquidity Sweep (Swept buy-stops above swing high, long upper shadow, closed back down)
    if candle_high > swing_high and candle_close < swing_high and (upper_wick / candle_range) >= 0.45:
        return {
            "has_sweep": True,
            "sweep_type": "BUY_SIDE_LIQUIDITY_SWEEP",
            "direction": "PUT",
            "explanation": f"شکار نقدینگی خریداران (استاپ‌هانت سقف {swing_high:.5f}) رخ داد؛ ریجکت فوری قیمت با سایه بلند فروش."
        }

    return {
        "has_sweep": False,
        "sweep_type": "NONE",
        "direction": "NEUTRAL",
        "explanation": "هیچ استاپ‌هانت یا شکار نقدینگی واضحی در کندل اخیر رخ نداده است."
    }


def analyze_smart_money_concepts(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Master SMC Confluence Analyzer.
    Combines FVG, Order Blocks, and Liquidity Sweeps into a unified Smart Money score.
    """
    fvg = detect_fair_value_gaps(df)
    ob = detect_order_blocks(df)
    sweep = detect_liquidity_sweep(df)

    call_votes = 0
    put_votes = 0

    if fvg["direction"] == "CALL":
        call_votes += 2
    elif fvg["direction"] == "PUT":
        put_votes += 2

    if ob["direction"] == "CALL":
        call_votes += 2
    elif ob["direction"] == "PUT":
        put_votes += 2

    if sweep["direction"] == "CALL":
        call_votes += 3  # Liquidity sweeps are extremely high win-rate in binary options
    elif sweep["direction"] == "PUT":
        put_votes += 3

    direction = "NEUTRAL"
    confidence = 0.0
    setup_name = "NONE"

    if call_votes > put_votes and call_votes >= 2:
        direction = "CALL"
        confidence = min(95.0, 60.0 + call_votes * 10.0)
        setup_name = f"SMC BULLISH ({fvg['fvg_type'] if fvg['direction'] == 'CALL' else ''} {ob['ob_type'] if ob['direction'] == 'CALL' else ''} {sweep['sweep_type'] if sweep['direction'] == 'CALL' else ''})".strip()
    elif put_votes > call_votes and put_votes >= 2:
        direction = "PUT"
        confidence = min(95.0, 60.0 + put_votes * 10.0)
        setup_name = f"SMC BEARISH ({fvg['fvg_type'] if fvg['direction'] == 'PUT' else ''} {ob['ob_type'] if ob['direction'] == 'PUT' else ''} {sweep['sweep_type'] if sweep['direction'] == 'PUT' else ''})".strip()

    reasons = []
    if sweep["has_sweep"]:
        reasons.append(sweep["explanation"])
    if ob["has_order_block"]:
        reasons.append(ob["explanation"])
    if fvg["has_fvg"]:
        reasons.append(fvg["explanation"])

    if not reasons:
        reasons.append("ساختار اسمارت مانی فعلاً در وضعیت تعادل خنثی است.")

    return {
        "direction": direction,
        "confidence": confidence,
        "setup_name": setup_name,
        "call_votes": call_votes,
        "put_votes": put_votes,
        "fvg": fvg,
        "order_block": ob,
        "liquidity_sweep": sweep,
        "explanation": " | ".join(reasons),
    }
