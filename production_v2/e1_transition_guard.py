from __future__ import annotations

from typing import Any

from .e1_reconciliation import analyze_e1 as _reconciled_analyze_e1


def _atr14(bars: list[dict[str, Any]]) -> float:
    trs: list[float] = []
    prev = None
    for b in bars[-14:]:
        try:
            h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return sum(trs) / len(trs) if trs else 0.0


def _slope(closes: list[float], atr: float, start: int, end: int) -> float:
    if atr <= 0 or end <= start or len(closes) < end:
        return 0.0
    return (closes[-start] - closes[-end]) / atr


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Final E1 transition guard.

    Detects a genuine regime handoff when a previously persistent direction is
    replaced by a strong opposite recent impulse. A reversal is classified as
    TRANSITION first; it is never converted into a trade decision.
    """
    result = _reconciled_analyze_e1(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result
    clean = [b for b in (bars or []) if isinstance(b, dict) and all(k in b for k in ("high", "low", "close"))]
    if len(clean) < 50:
        return result
    closes = [float(b["close"]) for b in clean]
    atr = _atr14(clean)
    # Compare the established prior 30-candle context with the latest 10.
    prior = _slope(closes, atr, 10, 40)
    recent = _slope(closes, atr, 0, 10)
    if abs(prior) >= 0.35 and abs(recent) >= 0.80 and (prior > 0) != (recent > 0):
        conflicts = list(result.get("conflicts", []))
        if "RECENT_IMPULSE_VS_PRIOR_CONTEXT" not in conflicts:
            conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")
        result["market_state"] = "TRANSITION"
        result["trend_state"] = "NONE"
        result["transition"] = "PRESENT"
        result["conflicts"] = conflicts
        result["reasons"] = conflicts + ["REGIME_CONFLICT_ACTIVE"]
        pr = result["professional_reasoning"]
        pr["primary_state"] = "TRANSITION"
        pr["market_state"] = "TRANSITION"
        pr["trend_confirmed"] = False
        pr["trend_maturity"] = "DIRECTIONAL_ONLY"
        pr["classification_reason"] = "recent_impulse_conflicts_with_prior_persistent_context"
        pr["prior_context_slope_atr"] = round(prior, 4)
        pr["recent_impulse_slope_atr"] = round(recent, 4)
        result["reasoning_trace"].append(f"TRANSITION_GUARD -> prior30_context={prior:.3f} recent10={recent:.3f}")
        result["reasoning_trace"].append("TRANSITION_GUARD -> prior regime replaced by recent impulse; confirmation withheld")
    return result
