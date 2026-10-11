import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional

def find_swing_levels(
    df: pd.DataFrame,
    left_bars: int = 5,
    right_bars: int = 2,
    lookback_total: int = 60,
) -> Dict[str, Any]:
    """
    Identifies recent swing highs and swing lows strictly using historical candles.
    A swing high at bar k is confirmed at bar k + right_bars if high[k] >= high[k-left_bars...k+right_bars].
    This ensures ZERO lookahead bias because right_bars bars have already closed.
    
    Returns:
      - swing_highs: List of price levels (sorted descending)
      - swing_lows: List of price levels (sorted ascending)
      - nearest_resistance: lowest swing high above current close
      - nearest_support: highest swing low below current close
      - dist_to_resistance_pips
      - dist_to_support_pips
    """
    if len(df) < left_bars + right_bars + 1:
        return {
            "swing_highs": [],
            "swing_lows": [],
            "nearest_resistance": None,
            "nearest_support": None,
            "dist_to_resistance_pips": None,
            "dist_to_support_pips": None,
        }

    subset = df.iloc[-lookback_total:] if len(df) > lookback_total else df
    highs = subset["high"].values
    lows = subset["low"].values
    current_close = float(df["close"].iloc[-1])

    swing_highs: List[float] = []
    swing_lows: List[float] = []

    n = len(subset)
    # The last bar index that can be confirmed is n - 1 - right_bars
    for i in range(left_bars, n - right_bars):
        window_highs = highs[i - left_bars : i + right_bars + 1]
        window_lows = lows[i - left_bars : i + right_bars + 1]
        
        # Check swing high
        if highs[i] == np.max(window_highs):
            swing_highs.append(round(float(highs[i]), 5))
            
        # Check swing low
        if lows[i] == np.min(window_lows):
            swing_lows.append(round(float(lows[i]), 5))

    # Deduplicate close levels
    def cluster_levels(levels: List[float], tolerance: float = 0.0003) -> List[float]:
        if not levels:
            return []
        sorted_lvls = sorted(levels)
        clustered = [sorted_lvls[0]]
        for lvl in sorted_lvls[1:]:
            if abs(lvl - clustered[-1]) > tolerance:
                clustered.append(lvl)
            else:
                clustered[-1] = (clustered[-1] + lvl) / 2.0
        return [round(x, 5) for x in clustered]

    clean_highs = cluster_levels(swing_highs)
    clean_lows = cluster_levels(swing_lows)

    resistances = [h for h in clean_highs if h > current_close]
    supports = [l for l in clean_lows if l < current_close]

    nearest_res = min(resistances) if resistances else None
    nearest_sup = max(supports) if supports else None

    # Calculate pip distance (assuming standard 4-digit / 2-digit FX pip)
    pip_scale = 100.0 if current_close > 50.0 else 10000.0

    dist_res_pips = round((nearest_res - current_close) * pip_scale, 2) if nearest_res else None
    dist_sup_pips = round((current_close - nearest_sup) * pip_scale, 2) if nearest_sup else None

    return {
        "swing_highs": clean_highs,
        "swing_lows": clean_lows,
        "nearest_resistance": nearest_res,
        "nearest_support": nearest_sup,
        "dist_to_resistance_pips": dist_res_pips,
        "dist_to_support_pips": dist_sup_pips,
        "current_close": current_close,
    }
