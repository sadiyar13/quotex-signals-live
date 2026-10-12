import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from app.indicators.technical import compute_all_indicators
from app.indicators.support_resistance import find_swing_levels
from app.indicators.candlestick import analyze_candlestick_patterns

class FilterResult:
    def __init__(
        self,
        filter_number: int,
        filter_name: str,
        status: str,  # PASS, FAIL, CONFLICT, INSUFFICIENT_DATA
        detected_direction: Optional[str] = None,  # CALL, PUT, NEUTRAL
        indicator_values: Optional[Dict[str, Any]] = None,
        explanation: str = "",
    ):
        self.filter_number = filter_number
        self.filter_name = filter_name
        self.status = status
        self.detected_direction = detected_direction
        self.indicator_values = indicator_values or {}
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filter_number": self.filter_number,
            "filter_name": self.filter_name,
            "status": self.status,
            "detected_direction": self.detected_direction,
            "indicator_values": self.indicator_values,
            "explanation": self.explanation,
        }


def evaluate_filter_1_mtf_trend(
    df_m1: pd.DataFrame,
    df_m5: pd.DataFrame,
    df_m15: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
) -> FilterResult:
    """
    فیلتر اول: تشخیص روند چندتایم‌فریمی (Multi-Timeframe Trend)
    ارزیابی موقعیت EMA 20 و EMA 50 در تایم‌فریم‌های M5 و M15.
    هر دو تایم‌فریم کلان باید هم‌جهت باشند.
    """
    name = "تشخیص روند چندتایم‌فریمی (MTF Trend)"
    if len(df_m5) < 35 or len(df_m15) < 20:
        return FilterResult(
            1, name, "INSUFFICIENT_DATA", "NEUTRAL",
            {}, "داده کافی در تایم‌فریم‌های M5 یا M15 برای محاسبه روند کلان وجود ندارد."
        )

    m5_ind = compute_all_indicators(df_m5, ema_fast=ema_fast, ema_slow=ema_slow)
    m15_ind = compute_all_indicators(df_m15, ema_fast=ema_fast, ema_slow=ema_slow)

    m5_fast = float(m5_ind[f"ema_{ema_fast}"].iloc[-1])
    m5_slow = float(m5_ind[f"ema_{ema_slow}"].iloc[-1])
    m5_close = float(m5_ind["close"].iloc[-1])

    m15_fast = float(m15_ind[f"ema_{ema_fast}"].iloc[-1])
    m15_slow = float(m15_ind[f"ema_{ema_slow}"].iloc[-1])
    m15_close = float(m15_ind["close"].iloc[-1])

    m5_trend = "CALL" if (m5_fast > m5_slow and m5_close >= m5_fast) else (
        "PUT" if (m5_fast < m5_slow and m5_close <= m5_fast) else "NEUTRAL"
    )

    m15_trend = "CALL" if (m15_fast > m15_slow) else (
        "PUT" if (m15_fast < m15_slow) else "NEUTRAL"
    )

    values = {
        "m5_ema20": round(m5_fast, 5),
        "m5_ema50": round(m5_slow, 5),
        "m15_ema20": round(m15_fast, 5),
        "m15_ema50": round(m15_slow, 5),
        "m5_direction": m5_trend,
        "m15_direction": m15_trend,
    }

    if m5_trend == "CALL" and m15_trend == "CALL":
        return FilterResult(
            1, name, "PASS", "CALL", values,
            f"همگرایی صعودی قوی: EMA20 بالاتر از EMA50 در تایم‌فریم‌های M5 و M15 قرار دارد."
        )
    elif m5_trend == "PUT" and m15_trend == "PUT":
        return FilterResult(
            1, name, "PASS", "PUT", values,
            f"همگرایی نزولی قوی: EMA20 پایین‌تر از EMA50 در تایم‌فریم‌های M5 و M15 قرار دارد."
        )
    elif m5_trend != m15_trend:
        return FilterResult(
            1, name, "CONFLICT", "NEUTRAL", values,
            f"تعارض روند تایم‌فریم‌ها: M5={m5_trend} اما M15={m15_trend}. فیلتر ناموفق."
        )
    else:
        return FilterResult(
            1, name, "FAIL", "NEUTRAL", values,
            "بازار رِنج یا بدون جهت‌گیری واضح در تایم‌فریم‌های میان‌مدت و کلان."
        )


def evaluate_filter_2_momentum(
    df_m1: pd.DataFrame,
    rsi_period: int = 14,
    rsi_ob: float = 70.0,
    rsi_os: float = 30.0,
) -> FilterResult:
    """
    فیلتر دوم: مومنتوم (Momentum Filter)
    ارزیابی RSI 14، شیب حرکت RSI، خط MACD و هیستوگرام در تایم‌فریم ورود (M1).
    """
    name = "مومنتوم بازار (RSI & MACD)"
    if len(df_m1) < 35:
        return FilterResult(2, name, "INSUFFICIENT_DATA", "NEUTRAL", {}, "داده برای محاسبه مومنتوم ناکافی است.")

    ind = compute_all_indicators(df_m1, rsi_period=rsi_period)
    curr_rsi = float(ind["rsi"].iloc[-1])
    prev_rsi = float(ind["rsi"].iloc[-2])
    macd_line = float(ind["macd_line"].iloc[-1])
    macd_signal = float(ind["macd_signal"].iloc[-1])
    macd_hist = float(ind["macd_hist"].iloc[-1])
    prev_macd_hist = float(ind["macd_hist"].iloc[-2])

    values = {
        "rsi": round(curr_rsi, 2),
        "rsi_delta": round(curr_rsi - prev_rsi, 2),
        "macd_line": round(macd_line, 6),
        "macd_signal": round(macd_signal, 6),
        "macd_hist": round(macd_hist, 6),
    }

    # Bullish Momentum: RSI > 50 and rising, not overbought, MACD line > Signal, Histogram positive or expanding
    is_bullish = (
        curr_rsi > 50.0
        and curr_rsi < rsi_ob
        and curr_rsi >= prev_rsi
        and macd_line > macd_signal
        and macd_hist >= prev_macd_hist
    )

    # Bearish Momentum: RSI < 50 and falling, not oversold, MACD line < Signal, Histogram negative or expanding downwards
    is_bearish = (
        curr_rsi < 50.0
        and curr_rsi > rsi_os
        and curr_rsi <= prev_rsi
        and macd_line < macd_signal
        and macd_hist <= prev_macd_hist
    )

    if is_bullish:
        return FilterResult(
            2, name, "PASS", "CALL", values,
            f"مومنتوم صعودی تأیید شد (RSI={values['rsi']} افزایشی و MACD بالای سیگنال با هیستوگرام مثبت)."
        )
    elif is_bearish:
        return FilterResult(
            2, name, "PASS", "PUT", values,
            f"مومنتوم نزولی تأیید شد (RSI={values['rsi']} کاهشی و MACD زیر سیگنال با هیستوگرام منفی)."
        )
    else:
        # Check if overbought or oversold
        reason = "مومنتوم ضعیف یا تعارض میان جهت RSI و خطوط MACD."
        if curr_rsi >= rsi_ob:
            reason = f"هشدار اشباع خرید (RSI={values['rsi']}); ورود به معامله CALL پرخطر است."
        elif curr_rsi <= rsi_os:
            reason = f"هشدار اشباع فروش (RSI={values['rsi']}); ورود به معامله PUT پرخطر است."

        return FilterResult(2, name, "FAIL", "NEUTRAL", values, reason)


def evaluate_filter_3_volatility_quality(
    df_m1: pd.DataFrame,
    atr_period: int = 14,
) -> FilterResult:
    """
    فیلتر سوم: نوسان و کیفیت بازار (Volatility & Market Quality)
    ارزیابی ATR، تشخیص نوسان فوق‌العاده پایین (خواب بازار)، جهش‌های غیرعادی و کندل‌های عظیم الجثه.
    """
    name = "کیفیت بازار و دامنه نوسان (Volatility & ATR)"
    if len(df_m1) < atr_period + 20:
        return FilterResult(3, name, "INSUFFICIENT_DATA", "NEUTRAL", {}, "داده برای سنجش نوسان بازار کافی نیست.")

    ind = compute_all_indicators(df_m1, atr_period=atr_period)
    atr_series = ind["atr"]
    curr_atr = float(atr_series.iloc[-1])
    mean_atr = float(atr_series.iloc[-30:].mean())

    curr_candle = df_m1.iloc[-1]
    curr_range = float(curr_candle["high"] - curr_candle["low"])

    values = {
        "current_atr": round(curr_atr, 5),
        "average_atr_30": round(mean_atr, 5),
        "atr_ratio": round(curr_atr / max(mean_atr, 1e-6), 2),
        "last_candle_range": round(curr_range, 5),
    }

    # 1. Dead market: ATR < 0.3 * average OR absolute ATR < 0.5 pips
    min_absolute_atr = 0.005 if curr_candle["close"] > 50.0 else 0.00005
    if curr_atr < 0.3 * mean_atr or curr_atr < min_absolute_atr:
        return FilterResult(
            3, name, "FAIL", "NEUTRAL", values,
            "نوسان بازار به شدت پایین است (بازار مرده/راکد). احتمال خطای انقضا در باینری آپشن بالاست."
        )

    # 2. Chaos / News spike: ATR > 2.8 * average
    if curr_atr > 2.8 * mean_atr:
        return FilterResult(
            3, name, "FAIL", "NEUTRAL", values,
            "جهش نوسانی شدید و غیرعادی (احتمال خبر ناگهانی). ورود به بازار ریسک نامتعارف دارد."
        )

    # 3. Giant single candle: candle range > 3.2 * ATR
    if curr_range > 3.2 * curr_atr:
        return FilterResult(
            3, name, "FAIL", "NEUTRAL", values,
            "کندل اخیر با بدنه/سایه غیرعادی بزرگ تشکیل شده است (خطر فرسودگی حرکت)."
        )

    return FilterResult(
        3, name, "PASS", "NEUTRAL", values,
        f"نوسان بازار در محدوده استاندارد و پایدار قرار دارد (نسبت ATR={values['atr_ratio']})."
    )


def evaluate_filter_4_support_resistance(
    df_m1: pd.DataFrame,
    proposed_direction: Optional[str] = None,
) -> FilterResult:
    """
    فیلتر چهارم: حمایت و مقاومت (Support & Resistance Proximity)
    تضمین عدم ورود به سقف نزدیک در خرید، یا کف نزدیک در فروش.
    """
    name = "مجاورت سطوح حمایت و مقاومت (S/R)"
    sr = find_swing_levels(df_m1, left_bars=5, right_bars=2, lookback_total=60)
    dist_res = sr["dist_to_resistance_pips"]
    dist_sup = sr["dist_to_support_pips"]
    curr_c = sr["current_close"]

    values = {
        "nearest_resistance": sr["nearest_resistance"],
        "nearest_support": sr["nearest_support"],
        "dist_to_res_pips": dist_res,
        "dist_to_sup_pips": dist_sup,
    }

    # Minimum safe distance to opposing level for 5-minute binary expiry (at least 2.5 pips)
    min_safe_pips = 2.5

    if proposed_direction == "CALL":
        if dist_res is not None and dist_res < min_safe_pips:
            return FilterResult(
                4, name, "FAIL", "NEUTRAL", values,
                f"هشدار: قیمت دقیقاً در مجاورت مقاومت ({sr['nearest_resistance']}) با فاصله تنها {dist_res} پیپ است. احتمال ریجکت بالاست."
            )
        return FilterResult(
            4, name, "PASS", "CALL", values,
            f"فاصله آزاد تا نزدیک‌ترین مقاومت ({dist_res if dist_res else 'بدون مانع نزدیک'} پیپ) برای حرکت صعودی مساعد است."
        )
    elif proposed_direction == "PUT":
        if dist_sup is not None and dist_sup < min_safe_pips:
            return FilterResult(
                4, name, "FAIL", "NEUTRAL", values,
                f"هشدار: قیمت دقیقاً در مجاورت حمایت ({sr['nearest_support']}) با فاصله تنها {dist_sup} پیپ است. احتمال جهش صعودی بالاست."
            )
        return FilterResult(
            4, name, "PASS", "PUT", values,
            f"فاصله آزاد تا نزدیک‌ترین حمایت ({dist_sup if dist_sup else 'بدون مانع نزدیک'} پیپ) برای حرکت نزولی مساعد است."
        )
    else:
        # Evaluate without pre-set direction
        if dist_res is not None and dist_res > min_safe_pips and (dist_sup is None or dist_sup < min_safe_pips):
            # Bouncing from support!
            return FilterResult(
                4, name, "PASS", "CALL", values,
                f"قیمت در حال جهش از حمایت ({sr['nearest_support']}) به سمت مقاومت آزاد است."
            )
        elif dist_sup is not None and dist_sup > min_safe_pips and (dist_res is None or dist_res < min_safe_pips):
            # Rejecting from resistance!
            return FilterResult(
                4, name, "PASS", "PUT", values,
                f"قیمت در حال ریزش از مقاومت ({sr['nearest_resistance']}) به سمت حمایت باز است."
            )
        return FilterResult(
            4, name, "PASS", "NEUTRAL", values,
            "فاصله مناسب از هر دو سطح کلیدی بدون ممانعت مستقیم."
        )


def evaluate_filter_5_candlestick(
    df_m1: pd.DataFrame,
) -> FilterResult:
    """
    فیلتر پنجم: تأیید کندلی (Candlestick Confirmation)
    بررسی الگوهای کندل بسته شده اخیر (Bullish/Bearish Engulfing, Pinbar, Momentum).
    """
    name = "تأیید الگوهای پرایس‌اکشن کندلی"
    pattern_res = analyze_candlestick_patterns(df_m1)

    pat = pattern_res["pattern"]
    dir_detected = pattern_res["direction"]
    strength = pattern_res["strength"]
    desc = pattern_res["description"]

    values = {
        "pattern": pat,
        "direction": dir_detected,
        "pattern_strength": strength,
    }

    if dir_detected in ["CALL", "PUT"] and strength >= 0.70:
        return FilterResult(
            5, name, "PASS", dir_detected, values,
            f"الگوی تأیید کندلی معتبر: {desc}"
        )
    else:
        return FilterResult(
            5, name, "FAIL", "NEUTRAL", values,
            f"فاقد الگوی بازگشتی یا ممنتومی شاخص (کندل: {desc})."
        )


def evaluate_filter_6_divergence(df_m1: pd.DataFrame) -> FilterResult:
    """
    فیلتر ششم: شکار واگرایی‌های مومنتوم (RSI & MACD Divergence)
    قوی‌ترین الگوی ریاضی برای تشخیص برگشت روند در ۵ دقیقه آینده.
    """
    from app.indicators.divergence import detect_divergence
    name = "شکار واگرایی‌های مومنتوم (Divergence)"
    div = detect_divergence(df_m1)

    values = {
        "has_divergence": div["has_divergence"],
        "divergence_type": div["divergence_type"],
        "confidence_boost": div["confidence_boost"],
    }

    if div["has_divergence"]:
        return FilterResult(
            6, name, "PASS", div["direction"], values,
            div["description"]
        )
    else:
        return FilterResult(
            6, name, "NEUTRAL", "NEUTRAL", values,
            div["description"]
        )


def evaluate_filter_7_bollinger(df_m1: pd.DataFrame) -> FilterResult:
    """
    فیلتر هفتم: بازگشت به میانگین باندهای بولینگر (Bollinger Mean Reversion)
    خروج قیمت از انحراف معیار ۲.۰ و بازگشت شتابان به درون باندها.
    """
    from app.indicators.bollinger import calculate_bollinger_bands
    name = "تخلیه هیجان باندهای بولینگر (Bollinger Reversion)"
    bb = calculate_bollinger_bands(df_m1)

    values = {
        "setup": bb["setup"],
        "percent_b": bb["percent_b"],
        "bandwidth": bb["bandwidth"],
    }

    if bb["direction"] in ["CALL", "PUT"]:
        return FilterResult(
            7, name, "PASS", bb["direction"], values,
            bb["explanation"]
        )
    else:
        return FilterResult(
            7, name, "PASS", "NEUTRAL", values,
            bb["explanation"]
        )


def evaluate_filter_8_csm(symbol: str, pair_changes: Dict[str, float] = None) -> FilterResult:
    """
    فیلتر هشتم: تاییدیه قدرت نسبی ارزها (Currency Strength Meter - CSM)
    بررسی هم‌راستایی قدرت ارز پایه نسبت به ارز مظنه.
    """
    from app.indicators.csm import calculate_currency_strength_meter, evaluate_pair_csm_alignment
    name = "موازنه قدرت نسبی ارزها (CSM)"
    pair_changes = pair_changes or {}
    csm_data = calculate_currency_strength_meter(pair_changes)
    res = evaluate_pair_csm_alignment(symbol, csm_data)

    values = {
        "base_score": res.get("base_score", 5.0),
        "quote_score": res.get("quote_score", 5.0),
        "diff": res.get("diff", 0.0),
    }

    return FilterResult(
        8, name, res["status"], res["detected_direction"], values,
        res["explanation"]
    )


def evaluate_filter_9_session_liquidity(now_utc=None) -> FilterResult:
    """
    فیلتر نهم: کیفیت نقدینگی سشن معاملاتی (Session Liquidity Quality)
    اجتناب از ساعات مرده بازار و اولویت‌دهی به همپوشانی لندن و نیویورک.
    """
    from app.indicators.sessions import evaluate_session_liquidity
    name = "کیفیت نقدینگی و سشن بازار (Session Liquidity)"
    sess = evaluate_session_liquidity(now_utc)

    values = {
        "session_name": sess["session_name"],
        "quality_tier": sess["quality_tier"],
        "multiplier": sess["win_rate_multiplier"],
    }

    if sess["is_high_liquidity"]:
        return FilterResult(
            9, name, "PASS", "NEUTRAL", values,
            f"{sess['session_name']}: {sess['explanation']}"
        )
    elif sess["quality_tier"] == "MARKET_CLOSED":
        return FilterResult(
            9, name, "NEUTRAL", "NEUTRAL", values,
            f"{sess['session_name']}: {sess['explanation']}"
        )
    else:
        return FilterResult(
            9, name, "WARN", "NEUTRAL", values,
            f"{sess['session_name']}: {sess['explanation']}"
        )


def evaluate_filter_10_smc(df_m1: pd.DataFrame) -> FilterResult:
    """
    فیلتر دهم: رویکرد پول هوشمند و شکاف ارزش (Smart Money Concepts & FVG)
    تشخیص ردپای نهادها، استاپ‌هانت نقدینگی، و شکاف‌های قیمت برای ورود اسنایپری.
    """
    from app.indicators.smc import analyze_smart_money_concepts
    name = "پول هوشمند و شکاف ارزش (SMC & FVG)"
    smc_res = analyze_smart_money_concepts(df_m1)

    values = {
        "setup_name": smc_res["setup_name"],
        "confidence": smc_res["confidence"],
        "has_fvg": smc_res["fvg"]["has_fvg"],
        "has_order_block": smc_res["order_block"]["has_order_block"],
        "has_sweep": smc_res["liquidity_sweep"]["has_sweep"],
    }

    if smc_res["direction"] in ["CALL", "PUT"]:
        return FilterResult(
            10, name, "PASS", smc_res["direction"], values,
            smc_res["explanation"]
        )
    else:
        return FilterResult(
            10, name, "NEUTRAL", "NEUTRAL", values,
            smc_res["explanation"]
        )


def evaluate_filter_11_oscillators(df_m1: pd.DataFrame, rsi_val: float = 50.0) -> FilterResult:
    """
    فیلتر یازدهم: تاییدیه همگرایی سه‌گانه اسیلاتورها (Stochastic & CCI & RSI)
    شکار کراس‌های استوکاستیک در نقاط افراطی و بازگشت‌های مومنتوم CCI.
    """
    from app.indicators.oscillators import analyze_confluence_oscillators
    name = "همگرایی اسیلاتورها (Stochastic & CCI)"
    osc_res = analyze_confluence_oscillators(df_m1, rsi_val=rsi_val)

    values = {
        "stoch_k": osc_res["stochastic"]["k"],
        "stoch_d": osc_res["stochastic"]["d"],
        "cci": osc_res["cci"]["cci"],
        "rsi": osc_res["rsi"],
        "call_points": osc_res["call_points"],
        "put_points": osc_res["put_points"],
    }

    if osc_res["direction"] in ["CALL", "PUT"]:
        return FilterResult(
            11, name, "PASS", osc_res["direction"], values,
            osc_res["explanation"]
        )
    else:
        return FilterResult(
            11, name, "NEUTRAL", "NEUTRAL", values,
            osc_res["explanation"]
        )


