import hashlib
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
from app.strategy.filters import (
    evaluate_filter_1_mtf_trend,
    evaluate_filter_2_momentum,
    evaluate_filter_3_volatility_quality,
    evaluate_filter_4_support_resistance,
    evaluate_filter_5_candlestick,
    evaluate_filter_6_divergence,
    evaluate_filter_7_bollinger,
    evaluate_filter_8_csm,
    evaluate_filter_9_session_liquidity,
    evaluate_filter_10_smc,
    evaluate_filter_11_oscillators,
    FilterResult,
)
from app.indicators.sentiment import calculate_fear_and_greed_index
from app.indicators.csm import calculate_currency_strength_meter
from app.core.config import settings

class StrategyEngine:
    """
    Advanced High-Win-Rate Multi-Factor Decision Engine for Forex Binary Options.
    Produces exclusively:
      - CALL
      - PUT
      - NO TRADE
    
    Guarantees:
      - Uses ONLY closed candles
      - Evaluates 9 comprehensive technical and macro factors:
          1. Multi-Timeframe Trend (M1, M5, M15)
          2. Momentum (RSI Wilder & MACD)
          3. Volatility & Market Quality (ATR)
          4. S/R Boundary Clearance
          5. Price Action Candlestick Confirmation
          6. RSI & MACD Regular/Hidden Divergence
          7. Bollinger Bands Exhaustion & %B Mean Reversion
          8. Currency Strength Meter (CSM) Cross-Alignment
          9. Session Liquidity Quality
      - Calculates Forex Fear & Greed Sentiment Index (0 - 100)
      - Enforces minimum agreement count across core and confirmation filters
      - Zero lookahead bias
      - Duplicate prevention via deterministic SHA-256 ID
    """

    def __init__(
        self,
        strategy_version: str = "3.0.0-PRO-SMC",
        min_agreement_count: int = 4,
        horizon_minutes: int = 5,
    ):
        self.strategy_version = strategy_version
        self.min_agreement_count = min_agreement_count
        self.horizon_minutes = horizon_minutes

    def generate_signal_id(self, symbol: str, timeframe: str, candle_timestamp: datetime.datetime) -> str:
        """Deterministic ID prevents duplicate signals on the same closed candle."""
        payload = f"{symbol}_{timeframe}_{candle_timestamp.isoformat()}_{self.strategy_version}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def analyze(
        self,
        symbol: str,
        df_m1: pd.DataFrame,
        df_m5: pd.DataFrame,
        df_m15: pd.DataFrame,
        data_source: str,
        data_quality_status: str = "VALID",
        pair_changes: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Runs full quantitative multi-factor evaluation pipeline.
        """
        if df_m1.empty or len(df_m1) < 30 or data_quality_status not in ["VALID", "MARKET_CLOSED_WEEKEND"]:
            if df_m1.empty or len(df_m1) < 30:
                reason = "عدم صدور سیگنال: داده تاریخی برای تایم‌فریم M1 کافی نیست."
                status_code = "INSUFFICIENT_DATA"
            else:
                reason = f"عدم صدور سیگنال: وضعیت جریان داده نامعتبر یا قطع است ({data_quality_status}). به منظور جلوگیری از هرگونه ریسک، معامله‌ای پیشنهاد نمی‌شود."
                status_code = data_quality_status

            return {
                "id": f"notrade_{int(datetime.datetime.utcnow().timestamp())}",
                "symbol": symbol,
                "direction": "NO TRADE",
                "created_at": datetime.datetime.utcnow(),
                "entry_price": float(df_m1.iloc[-1]["close"]) if not df_m1.empty else 0.0,
                "expiry_time": datetime.datetime.utcnow(),
                "data_source": data_source,
                "timeframe": "M1",
                "rule_agreement_score": 0.0,
                "strategy_version": self.strategy_version,
                "data_quality_status": status_code,
                "decision_reason": reason,
                "fear_and_greed": {"score": 50.0, "state": "NEUTRAL", "state_fa": "خنثی", "color": "#94A3B8"},
                "currency_strength": {},
                "is_pre_signal": False,
                "pre_signal_direction": "NONE",
                "readiness_score": 0.0,
                "pre_signal_message": "",
                "recommended_timeframe": "M1 / M5",
                "recommended_expiry_minutes": self.horizon_minutes,
                "recommended_expiry_description": f"انقضای {self.horizon_minutes} دقیقه در کوتکس (پایان کندل M5)",
                "timing_guide": "در ثانیه ۰ تا ۳ شروع کندل جدید کلیک کنید.",
                "filters": [],
            }

        last_closed_candle = df_m1.iloc[-1]
        candle_ts = last_closed_candle["timestamp"]
        entry_price = float(last_closed_candle["close"])
        expiry_ts = candle_ts + datetime.timedelta(minutes=self.horizon_minutes)
        signal_id = self.generate_signal_id(symbol, "M1", candle_ts)

        # 1. Core Filter 1: MTF Trend
        f1 = evaluate_filter_1_mtf_trend(
            df_m1, df_m5, df_m15,
            ema_fast=settings.EMA_FAST_PERIOD,
            ema_slow=settings.EMA_SLOW_PERIOD,
        )

        # 2. Core Filter 2: Momentum
        f2 = evaluate_filter_2_momentum(
            df_m1,
            rsi_period=settings.RSI_PERIOD,
            rsi_ob=settings.RSI_OVERBOUGHT,
            rsi_os=settings.RSI_OVERSOLD,
        )

        # 3. Core Filter 3: Volatility & Market Quality
        f3 = evaluate_filter_3_volatility_quality(
            df_m1,
            atr_period=settings.ATR_PERIOD,
        )

        # Proposed direction from Filter 1 or Filter 2
        proposed_dir = f1.detected_direction if f1.status == "PASS" else f2.detected_direction

        # 4. Core Filter 4: Support & Resistance Proximity
        f4 = evaluate_filter_4_support_resistance(df_m1, proposed_direction=proposed_dir)

        # 5. Core Filter 5: Candlestick Confirmation
        f5 = evaluate_filter_5_candlestick(df_m1)

        # 6. Advanced Filter 6: Divergence Engine (Sniper reversal detection)
        f6 = evaluate_filter_6_divergence(df_m1)

        # 7. Advanced Filter 7: Bollinger Bands Mean Reversion
        f7 = evaluate_filter_7_bollinger(df_m1)

        # 8. Advanced Filter 8: Currency Strength Meter (CSM)
        f8 = evaluate_filter_8_csm(symbol, pair_changes)

        # 9. Advanced Filter 9: Session Liquidity Tier
        f9 = evaluate_filter_9_session_liquidity(candle_ts)

        # 10. Advanced Filter 10: Smart Money Concepts & FVG
        f10 = evaluate_filter_10_smc(df_m1)

        # 11. Advanced Filter 11: Oscillators Confluence (Stochastic & CCI)
        rsi_val = float(f2.indicator_values.get("rsi", 50.0))
        f11 = evaluate_filter_11_oscillators(df_m1, rsi_val=rsi_val)

        # Compute Sentiment & Fear/Greed Index
        fg_index = calculate_fear_and_greed_index(df_m1)
        csm_data = calculate_currency_strength_meter(pair_changes or {})

        core_filters = [f1, f2, f3, f4, f5]
        all_filters = [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11]

        # Strict agreement counting (NEVER count NEUTRAL as a directional vote)
        call_agreements = sum(
            1 for f in core_filters
            if f.status == "PASS" and f.detected_direction == "CALL"
        )
        put_agreements = sum(
            1 for f in core_filters
            if f.status == "PASS" and f.detected_direction == "PUT"
        )

        # Bonus agreement points from Divergence, Bollinger, CSM, SMC, and Oscillators
        if f6.status == "PASS" and f6.detected_direction == "CALL":
            call_agreements += 1
        elif f6.status == "PASS" and f6.detected_direction == "PUT":
            put_agreements += 1

        if f7.status == "PASS" and f7.detected_direction == "CALL":
            call_agreements += 1
        elif f7.status == "PASS" and f7.detected_direction == "PUT":
            put_agreements += 1

        if f8.status == "PASS" and f8.detected_direction == "CALL":
            call_agreements += 1
        elif f8.status == "PASS" and f8.detected_direction == "PUT":
            put_agreements += 1

        # SMC institutional weight (+2 points for high conviction)
        if f10.status == "PASS" and f10.detected_direction == "CALL":
            call_agreements += 2
        elif f10.status == "PASS" and f10.detected_direction == "PUT":
            put_agreements += 2

        # Oscillator confluence weight (+1 point)
        if f11.status == "PASS" and f11.detected_direction == "CALL":
            call_agreements += 1
        elif f11.status == "PASS" and f11.detected_direction == "PUT":
            put_agreements += 1

        # Session liquidity quality (+1 point bonus if high liquidity)
        if f9.status == "PASS":
            if call_agreements > put_agreements:
                call_agreements += 1
            elif put_agreements > call_agreements:
                put_agreements += 1

        # Strict Candlestick and Price Action Gate for Binary Options
        last_c = df_m1.iloc[-1]
        c_open = float(last_c["open"])
        c_high = float(last_c["high"])
        c_low = float(last_c["low"])
        c_close = float(last_c["close"])
        c_range = max(1e-6, c_high - c_low)
        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)
        body = abs(c_close - c_open)

        # For CALL: Candle must not be a heavy dumping red marubozu (falling knife)
        is_bearish_dump = (c_close < c_open) and (body > 0.65 * c_range) and (lower_wick < 0.25 * c_range)
        call_candle_ok = (c_close >= c_open or (lower_wick >= 0.35 * c_range)) and not is_bearish_dump

        # For PUT: Candle must not be a heavy pumping green marubozu
        is_bullish_pump = (c_close > c_open) and (body > 0.65 * c_range) and (upper_wick < 0.25 * c_range)
        put_candle_ok = (c_close <= c_open or (upper_wick >= 0.35 * c_range)) and not is_bullish_pump

        # Mandatory Filter Checks:
        trend_passed = (f1.status == "PASS") and (f1.detected_direction in ["CALL", "PUT"])
        quality_passed = (f3.status == "PASS") and (data_quality_status in ["VALID", "MARKET_CLOSED_WEEKEND"])

        direction = "NO TRADE"
        rule_score = 0.0
        reason_parts = []

        if not quality_passed:
            direction = "NO TRADE"
            reason_parts.append(f"رد سیگنال به علت نوسان نامساعد یا کیفیت داده: {f3.explanation}")
        elif not trend_passed:
            direction = "NO TRADE"
            reason_parts.append(f"رد سیگنال به علت عدم تأیید روند کلان M5/M15: {f1.explanation}")
        else:
            # STRICT TREND LOCK:
            # A CALL is ONLY allowed if the macro trend is strictly CALL (Bullish)
            # A PUT is ONLY allowed if the macro trend is strictly PUT (Bearish)
            # Counter-trend trading is 100% BANNED.
            is_macro_call = (f1.detected_direction == "CALL")
            is_macro_put = (f1.detected_direction == "PUT")

            # Setups inside the established macro trend:
            # 1. Trend Momentum Continuation
            is_call_trend_setup = is_macro_call and (f2.status == "PASS" and f2.detected_direction == "CALL")
            # 2. Pullback Reversal in Trend direction (e.g. bounce off Support/EMA/Lower BB)
            is_call_pullback_setup = is_macro_call and (
                (f4.detected_direction == "CALL" or f7.detected_direction == "CALL" or f6.detected_direction == "CALL" or f10.detected_direction == "CALL")
                and (f11.status == "PASS" and f11.detected_direction == "CALL")
            )

            is_put_trend_setup = is_macro_put and (f2.status == "PASS" and f2.detected_direction == "PUT")
            is_put_pullback_setup = is_macro_put and (
                (f4.detected_direction == "PUT" or f7.detected_direction == "PUT" or f6.detected_direction == "PUT" or f10.detected_direction == "PUT")
                and (f11.status == "PASS" and f11.detected_direction == "PUT")
            )

            # Check CALL execution (STRICTLY when macro trend is CALL):
            if is_macro_call and call_agreements >= self.min_agreement_count and (is_call_trend_setup or is_call_pullback_setup):
                if not call_candle_ok:
                    direction = "NO TRADE"
                    reason_parts.append("مردود به دلیل کندل ریزشی تند بدون سایه بازگشتی (ورود روی چاقوی در حال سقوط ممنوع است).")
                elif f4.status == "FAIL":
                    direction = "NO TRADE"
                    reason_parts.append(f"مردود به دلیل برخورد به مقاومت سرسخت نزدیک ({f4.indicator_values.get('dist_to_res_pips', 0)} پیپ).")
                else:
                    direction = "CALL"
                    rule_score = round(min(98.0, 68.0 + (call_agreements * 4.5)), 1)
                    reason_parts.append("★ سیگنال خرید در جهت روند صعودی کلان (M5/M15): تایید EMA، مومنتوم و توافق قوی فیلترها.")
                    if f10.status == "PASS" and f10.detected_direction == "CALL":
                        reason_parts.append("تاییدیه پول هوشمند (SMC/OrderBlock)")
                    if f11.status == "PASS" and f11.detected_direction == "CALL":
                        reason_parts.append("تایید همگرایی اسیلاتورها در کف (Stoch/CCI)")

            # Check PUT execution (STRICTLY when macro trend is PUT):
            elif is_macro_put and put_agreements >= self.min_agreement_count and (is_put_trend_setup or is_put_pullback_setup):
                if not put_candle_ok:
                    direction = "NO TRADE"
                    reason_parts.append("مردود به دلیل کندل جهشی تند بدون سایه بازگشتی (فروش روی شتاب صعودی ممنوع است).")
                elif f4.status == "FAIL":
                    direction = "NO TRADE"
                    reason_parts.append(f"مردود به دلیل برخورد به حمایت سرسخت نزدیک ({f4.indicator_values.get('dist_to_sup_pips', 0)} پیپ).")
                else:
                    direction = "PUT"
                    rule_score = round(min(98.0, 68.0 + (put_agreements * 4.5)), 1)
                    reason_parts.append("★ سیگنال فروش در جهت روند نزولی کلان (M5/M15): تایید EMA، مومنتوم و توافق قوی فیلترها.")
                    if f10.status == "PASS" and f10.detected_direction == "PUT":
                        reason_parts.append("تاییدیه پول هوشمند (SMC/OrderBlock)")
                    if f11.status == "PASS" and f11.detected_direction == "PUT":
                        reason_parts.append("تایید همگرایی اسیلاتورها در سقف (Stoch/CCI)")

            else:
                direction = "NO TRADE"
                max_agree = max(call_agreements, put_agreements)
                rule_score = round(min(65.0, max_agree * 11.0), 1)
                reason_parts.append(f"عدم احراز شرایط ستاپ هم‌راستا با روند (روند: {f1.detected_direction} | توافق فیلترها: {max_agree}/{self.min_agreement_count}). برای حفظ سرمایه سیگنالی صادر نشد.")

        # --- PRE-SIGNAL READINESS DETECTION ---
        # Pre-signal MUST ALSO be strictly locked to macro trend:
        is_pre_signal = False
        pre_signal_direction = "NONE"
        readiness_score = 0.0
        pre_signal_msg = ""

        if direction in ["CALL", "PUT"]:
            is_pre_signal = False
            pre_signal_direction = direction
            readiness_score = 100.0
            pre_signal_msg = f"سیگنال قطعی ورود {direction}! آماده اجرای سفارش در ثانیه ۰ ابتدای کندل ۵ دقیقه‌ای باشید."
        else:
            if f1.status == "PASS" and f1.detected_direction == "CALL" and call_agreements >= 3:
                is_pre_signal = True
                pre_signal_direction = "CALL"
                readiness_score = min(92.0, max(72.0, float(call_agreements * 18.0)))
                pre_signal_msg = f"⚡ هشدار آماده‌باش {symbol}: ستاپ صعودی هم‌راستای روند در حال شکل‌گیری است! در ثانیه ۰ کندل بعدی آماده ثبت خرید ۵ دقیقه‌ای باشید."
            elif f1.status == "PASS" and f1.detected_direction == "PUT" and put_agreements >= 3:
                is_pre_signal = True
                pre_signal_direction = "PUT"
                readiness_score = min(92.0, max(72.0, float(put_agreements * 18.0)))
                pre_signal_msg = f"⚡ هشدار آماده‌باش {symbol}: ستاپ نزولی هم‌راستای روند در حال شکل‌گیری است! در ثانیه ۰ کندل بعدی آماده ثبت فروش ۵ دقیقه‌ای باشید."
            else:
                readiness_score = round(min(50.0, max(call_agreements, put_agreements) * 10.0), 1)
                pre_signal_msg = "بازار در حالت نوسان عادی یا عدم هم‌راستایی فیلترها با روند؛ ستاپی برای ورود نیست."

        decision_reason = " | ".join(reason_parts)

        return {
            "id": signal_id,
            "symbol": symbol,
            "direction": direction,
            "created_at": candle_ts,
            "entry_price": entry_price,
            "expiry_time": expiry_ts,
            "data_source": data_source,
            "timeframe": "M5",
            "rule_agreement_score": rule_score,
            "strategy_version": self.strategy_version,
            "data_quality_status": data_quality_status,
            "decision_reason": decision_reason,
            "fear_and_greed": fg_index,
            "currency_strength": csm_data,
            "is_pre_signal": is_pre_signal,
            "pre_signal_direction": pre_signal_direction,
            "readiness_score": readiness_score,
            "pre_signal_message": pre_signal_msg,
            "recommended_timeframe": "M5 (تایم تحلیل و ورود)",
            "recommended_expiry_minutes": 5,
            "recommended_expiry_description": "انقضای ۵ دقیقه دقیقاً همگام با پایان کندل M5",
            "timing_guide": "در ثانیه ۰۰ تا ۰۳ شروع کندل جدید ۵ دقیقه‌ای در کوتکس وارد شوید.",
            "micro_timing_tip": "قانون بقای سرمایه: حداکثر ۱ تا ۲ درصد موجودی در هر معامله | بدون مارتینگل | توقف معامله پس از ۳ باخت متوالی.",
            "filters": [f.to_dict() for f in all_filters],
        }

strategy_engine = StrategyEngine(min_agreement_count=settings.MIN_RULE_AGREEMENT_COUNT)
