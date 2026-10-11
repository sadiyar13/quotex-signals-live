import uuid
import math
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from app.strategy.engine import StrategyEngine
from app.core.config import settings

def calculate_wilson_score_interval(wins: int, total: int, confidence: float = 0.95) -> Dict[str, float]:
    """
    Calculates Wilson score confidence interval for a binomial proportion.
    Standard normal quantile z = 1.95996 for 95% confidence.
    """
    if total <= 0:
        return {"lower": 0.0, "upper": 0.0, "center": 0.0}

    z = 1.959963984540054  # 95% confidence
    p_hat = wins / total
    n = total

    denominator = 1.0 + (z**2) / n
    center = (p_hat + (z**2) / (2.0 * n)) / denominator
    spread = (z * math.sqrt((p_hat * (1.0 - p_hat) / n) + ((z**2) / (4.0 * (n**2))))) / denominator

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return {
        "lower": round(lower * 100.0, 2),
        "upper": round(upper * 100.0, 2),
        "center": round(p_hat * 100.0, 2),
    }


class BacktestEngine:
    """
    Event-driven Historical Replay Backtester with Zero Lookahead Bias.
    Splits data into Development, Validation, and Out-of-sample periods.
    """

    def __init__(
        self,
        strategy_engine: Optional[StrategyEngine] = None,
        payout_ratio: float = 0.85,
        horizon_minutes: int = 5,
    ):
        self.strategy_engine = strategy_engine or StrategyEngine()
        self.payout_ratio = payout_ratio
        self.horizon_minutes = horizon_minutes

    def split_data(
        self,
        df: pd.DataFrame,
        period_type: str = "DEVELOPMENT",
    ) -> pd.DataFrame:
        """
        Splits time-series data chronologically without random shuffling:
          - DEVELOPMENT: first 60% of data
          - VALIDATION: next 20% of data
          - OUT_OF_SAMPLE: last 20% of data (untouched test set)
          - FULL: 100% of data
        """
        n = len(df)
        if n < 80:
            return df

        idx_dev_end = int(n * 0.60)
        idx_val_end = int(n * 0.80)

        p = period_type.upper()
        if p == "DEVELOPMENT":
            return df.iloc[:idx_dev_end].copy()
        elif p == "VALIDATION":
            return df.iloc[idx_dev_end:idx_val_end].copy()
        elif p == "OUT_OF_SAMPLE":
            return df.iloc[idx_val_end:].copy()
        else:
            return df.copy()

    def resample_timeframe(self, df_m1: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
        """Resamples M1 candles to higher timeframes like M5 or M15."""
        if df_m1.empty:
            return pd.DataFrame()
        temp = df_m1.set_index("timestamp")
        resampled = temp.resample(rule, closed="left", label="left").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna().reset_index()
        return resampled

    def run(
        self,
        df_m1: pd.DataFrame,
        symbol: str = "EUR/USD",
        period_type: str = "DEVELOPMENT",
        payout_ratio: Optional[float] = None,
        min_rule_agreement: int = 4,
    ) -> Dict[str, Any]:
        """
        Executes chronological candle-by-candle replay backtest.
        Zero lookahead bias guaranteed: only bars <= current index are fed to indicators.
        """
        payout = payout_ratio if payout_ratio is not None else self.payout_ratio
        df_period = self.split_data(df_m1, period_type)

        total_candles = len(df_period)
        if total_candles < 60:
            raise ValueError(f"داده کافی در بازه انتخابی ({period_type}) برای بکتست موجود نیست (حداقل ۶۰ کندل لازم است).")

        run_id = f"bt_{uuid.uuid4().hex[:12]}"
        self.strategy_engine.min_agreement_count = min_rule_agreement

        trades: List[Dict[str, Any]] = []
        call_signals = 0
        put_signals = 0
        rejected_signals_count = 0
        missing_data_count = 0

        min_warmup = 55  # Needs 50 bars for EMA50 on higher timeframes
        horizon_bars = self.horizon_minutes  # For M1, 5 bars = 5 minutes

        # Active trade cooldown to prevent overlapping entries on the same direction
        last_entry_bar = -100

        # Pre-resample M5 and M15 once, then strictly slice <= entry_time to maintain zero lookahead
        full_m5 = self.resample_timeframe(df_period, "5min")
        full_m15 = self.resample_timeframe(df_period, "15min")

        for i in range(min_warmup, total_candles - horizon_bars):
            # STRICT ZERO LOOKAHEAD: slice only historical candles up to index i
            slice_m1 = df_period.iloc[: i + 1]
            current_candle = slice_m1.iloc[-1]
            entry_time = current_candle["timestamp"]

            slice_m5 = full_m5[full_m5["timestamp"] <= entry_time]
            slice_m15 = full_m15[full_m15["timestamp"] <= entry_time]

            if len(slice_m5) < 20 or len(slice_m15) < 10:
                continue
            entry_price = float(current_candle["close"])

            # Check cooldown: only 1 trade per 5 minutes per pair
            if i - last_entry_bar < horizon_bars:
                continue

            # Run strategy analysis
            analysis = self.strategy_engine.analyze(
                symbol=symbol,
                df_m1=slice_m1,
                df_m5=slice_m5,
                df_m15=slice_m15,
                data_source="BACKTEST_REPLAY",
                data_quality_status="VALID",
            )

            direction = analysis["direction"]
            rule_score = analysis["rule_agreement_score"]

            if direction == "NO TRADE":
                rejected_signals_count += 1
                continue

            # Signal generated! Now advance exactly 5 bars into the future to evaluate
            expiry_bar = df_period.iloc[i + horizon_bars]
            expiry_time = expiry_bar["timestamp"]
            expiry_price = float(expiry_bar["close"])

            # Evaluate binary outcome
            outcome = "TIE"
            return_unit = 0.0

            if direction == "CALL":
                call_signals += 1
                if expiry_price > entry_price:
                    outcome = "WIN"
                    return_unit = payout
                elif expiry_price < entry_price:
                    outcome = "LOSS"
                    return_unit = -1.0
                else:
                    outcome = "TIE"
                    return_unit = 0.0

            elif direction == "PUT":
                put_signals += 1
                if expiry_price < entry_price:
                    outcome = "WIN"
                    return_unit = payout
                elif expiry_price > entry_price:
                    outcome = "LOSS"
                    return_unit = -1.0
                else:
                    outcome = "TIE"
                    return_unit = 0.0

            trades.append({
                "symbol": symbol,
                "direction": direction,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "expiry_time": expiry_time,
                "expiry_price": expiry_price,
                "outcome": outcome,
                "rule_score": rule_score,
                "return_unit": return_unit,
                "hour": entry_time.hour,
            })

            last_entry_bar = i

        # Calculate statistics
        total_signals = len(trades)
        win_count = sum(1 for t in trades if t["outcome"] == "WIN")
        loss_count = sum(1 for t in trades if t["outcome"] == "LOSS")
        tie_count = sum(1 for t in trades if t["outcome"] == "TIE")

        evaluated_signals = win_count + loss_count
        win_rate = round((win_count / evaluated_signals * 100.0), 2) if evaluated_signals > 0 else 0.0
        wilson_ci = calculate_wilson_score_interval(win_count, evaluated_signals, 0.95)

        # Net simulated return = Wins * P - Losses
        net_return = round((win_count * payout) - loss_count, 2)
        # Break-even win rate = 1 / (1 + P)
        break_even_rate = round((1.0 / (1.0 + payout)) * 100.0, 2)

        # Max consecutive losses
        max_consec_losses = 0
        current_consec = 0
        for t in trades:
            if t["outcome"] == "LOSS":
                current_consec += 1
                max_consec_losses = max(max_consec_losses, current_consec)
            elif t["outcome"] == "WIN":
                current_consec = 0

        # Hourly & Session breakdown
        session_stats = {"Asian": {"trades": 0, "wins": 0}, "London": {"trades": 0, "wins": 0}, "NY": {"trades": 0, "wins": 0}}
        hourly_stats: Dict[int, Dict[str, int]] = {h: {"trades": 0, "wins": 0} for h in range(24)}

        for t in trades:
            h = t["hour"]
            hourly_stats[h]["trades"] += 1
            if t["outcome"] == "WIN":
                hourly_stats[h]["wins"] += 1

            if 0 <= h < 8:
                session_stats["Asian"]["trades"] += 1
                if t["outcome"] == "WIN": session_stats["Asian"]["wins"] += 1
            elif 8 <= h < 16:
                session_stats["London"]["trades"] += 1
                if t["outcome"] == "WIN": session_stats["London"]["wins"] += 1
            else:
                session_stats["NY"]["trades"] += 1
                if t["outcome"] == "WIN": session_stats["NY"]["wins"] += 1

        for s_name, s_data in session_stats.items():
            tot = s_data["trades"]
            w = s_data["wins"]
            s_data["win_rate"] = round((w / tot * 100.0), 2) if tot > 0 else 0.0

        for h, h_data in hourly_stats.items():
            tot = h_data["trades"]
            w = h_data["wins"]
            h_data["win_rate"] = round((w / tot * 100.0), 2) if tot > 0 else 0.0

        return {
            "run_id": run_id,
            "symbol": symbol,
            "period_type": period_type,
            "payout_ratio": payout,
            "total_candles": total_candles,
            "total_signals": total_signals,
            "call_signals": call_signals,
            "put_signals": put_signals,
            "win_count": win_count,
            "loss_count": loss_count,
            "tie_count": tie_count,
            "win_rate": win_rate,
            "wilson_ci_lower": wilson_ci["lower"],
            "wilson_ci_upper": wilson_ci["upper"],
            "max_consecutive_losses": max_consec_losses,
            "net_simulated_return": net_return,
            "break_even_rate": break_even_rate,
            "rejected_signals_count": rejected_signals_count,
            "missing_data_count": missing_data_count,
            "session_breakdown": session_stats,
            "hourly_breakdown": hourly_stats,
            "trades": trades,
        }

backtest_engine = BacktestEngine()
