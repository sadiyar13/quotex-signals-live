import numpy as np
import pandas as pd
from typing import Dict, Any, List

def calculate_currency_strength_meter(
    pair_changes: Dict[str, float]
) -> Dict[str, Any]:
    """
    Currency Strength Meter (CSM) for the 8 major currencies:
      EUR, USD, GBP, JPY, AUD, CAD, CHF, NZD
    
    Scores each currency from 0.0 (weakest) to 10.0 (strongest), centered at 5.0.
    In binary options, high-probability trades occur when:
      Base Currency is STRONG (> 6.0) AND Quote Currency is WEAK (< 4.0) -> CALL
      Base Currency is WEAK (< 4.0) AND Quote Currency is STRONG (> 6.0) -> PUT
    """
    # Raw relative performance vs USD (% change over recent 20 bars)
    eur_vs_usd = pair_changes.get("EUR/USD", 0.0)
    gbp_vs_usd = pair_changes.get("GBP/USD", 0.0)
    aud_vs_usd = pair_changes.get("AUD/USD", 0.0)
    nzd_vs_usd = pair_changes.get("NZD/USD", 0.0)
    usd_vs_jpy = pair_changes.get("USD/JPY", 0.0)
    usd_vs_chf = pair_changes.get("USD/CHF", 0.0)
    usd_vs_cad = pair_changes.get("USD/CAD", 0.0)

    # Invert quotes where USD is base
    jpy_vs_usd = -usd_vs_jpy
    chf_vs_usd = -usd_vs_chf
    cad_vs_usd = -usd_vs_cad

    raw_scores = {
        "EUR": eur_vs_usd,
        "GBP": gbp_vs_usd,
        "AUD": aud_vs_usd,
        "NZD": nzd_vs_usd,
        "CAD": cad_vs_usd,
        "CHF": chf_vs_usd,
        "JPY": jpy_vs_usd,
    }

    # USD score is the negative average of the others
    usd_score = -float(np.mean(list(raw_scores.values())))
    raw_scores["USD"] = usd_score

    # Normalize to 0.0 - 10.0 scale centered around 5.0
    normalized_csm = {}
    for curr, val in raw_scores.items():
        # Typical 20-bar forex move is +/- 0.3%
        scaled = 5.0 + (val / 0.25) * 2.5
        normalized_csm[curr] = round(float(np.clip(scaled, 0.5, 9.8)), 1)

    # Sort descending
    sorted_ranking = sorted(normalized_csm.items(), key=lambda x: x[1], reverse=True)

    return {
        "scores": normalized_csm,
        "ranking": [{"currency": c, "strength": s} for c, s in sorted_ranking],
        "strongest": sorted_ranking[0][0],
        "weakest": sorted_ranking[-1][0],
    }

def evaluate_pair_csm_alignment(symbol: str, csm_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates whether the specific pair has strong directional divergence."""
    parts = symbol.split("/")
    if len(parts) != 2:
        return {"status": "PASS", "detected_direction": "NEUTRAL", "explanation": "فرمت نماد نامعتبر است."}

    base, quote = parts[0], parts[1]
    scores = csm_data.get("scores", {})
    base_score = scores.get(base, 5.0)
    quote_score = scores.get(quote, 5.0)
    diff = round(base_score - quote_score, 1)

    if diff >= 2.0:
        return {
            "status": "PASS",
            "detected_direction": "CALL",
            "diff": diff,
            "base_score": base_score,
            "quote_score": quote_score,
            "explanation": f"تایید قدرت ارزها (CSM): ارز پایه {base} با نمره {base_score} قوی‌تر از ارز مظنه {quote} با نمره {quote_score} است (اختلاف +{diff}).",
        }
    elif diff <= -2.0:
        return {
            "status": "PASS",
            "detected_direction": "PUT",
            "diff": diff,
            "base_score": base_score,
            "quote_score": quote_score,
            "explanation": f"تایید قدرت ارزها (CSM): ارز مظنه {quote} با نمره {quote_score} قوی‌تر از ارز پایه {base} با نمره {base_score} است (اختلاف {diff}).",
        }
    else:
        return {
            "status": "NEUTRAL",
            "detected_direction": "NEUTRAL",
            "diff": diff,
            "base_score": base_score,
            "quote_score": quote_score,
            "explanation": f"تعادل نسبی قدرت دو ارز ({base}: {base_score} vs {quote}: {quote_score}). واگرایی شدیدی بین دو ارز مشاهده نمی‌شود.",
        }
