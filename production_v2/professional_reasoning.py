"""Shared professional-trader reasoning guardrails for E1-E9.

This layer enriches each brain without taking ownership from neighboring brains.
It makes uncertainty, counter-evidence, invalidation and next-action explicit.
"""
from __future__ import annotations

from typing import Any


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, x))


def _first(result: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in result and result[key] not in (None, "", [], {}):
            return result[key]
    return None


def _collect(result: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value and value not in out:
            out.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item and item not in out:
                    out.append(item)
    return out


def apply_professional_layer(result: dict[str, Any], brain: str) -> dict[str, Any]:
    """Add professional reasoning fields while preserving the brain's authority boundary."""
    if not isinstance(result, dict):
        return result

    r = dict(result)
    confidence = _clamp(_first(r, "confidence", "regime_confidence", "setup_confidence", "confirmation_confidence", "risk_confidence"), 0.0)
    vetoes = _collect(r, ("hard_veto", "vetoes", "invalidation_evidence", "invalidations", "conflicts"))
    reasons = _collect(r, ("counter_evidence", "missing_evidence", "why_not_trade", "reasons"))

    if confidence >= 0.80:
        uncertainty = "LOW"
    elif confidence >= 0.60:
        uncertainty = "MODERATE"
    elif confidence > 0:
        uncertainty = "HIGH"
    else:
        uncertainty = "VERY_HIGH"

    if vetoes:
        invalidation_state = "PRESENT"
    elif reasons:
        invalidation_state = "CHALLENGED"
    else:
        invalidation_state = "NONE_OBSERVED"

    # Counter-evidence is deliberately exposed rather than hidden by a score.
    r["professional_reasoning"] = {
        **(r.get("professional_reasoning") if isinstance(r.get("professional_reasoning"), dict) else {}),
        "brain": brain,
        "evidence_first": True,
        "counter_evidence": reasons,
        "invalidation": vetoes,
        "uncertainty": uncertainty,
        "invalidation_state": invalidation_state,
    }
    r["counter_evidence"] = list(dict.fromkeys(_collect(r, ("counter_evidence",)) + reasons))
    r["invalidation_evidence"] = list(dict.fromkeys(_collect(r, ("invalidation_evidence",)) + vetoes))
    r["uncertainty"] = uncertainty
    r["uncertainty_score"] = round(1.0 - confidence, 3)
    r["invalidation_state"] = invalidation_state

    # Professional decision hygiene: never turn uncertainty into permission.
    decision = _first(r, "decision", "final_decision", "trade_decision", "action")
    if brain == "E9" and isinstance(decision, str):
        upper = decision.upper()
        if upper in {"BUY", "SELL", "EXECUTE", "TRADE"} and (vetoes or uncertainty in {"HIGH", "VERY_HIGH"}):
            r["decision"] = "NO_TRADE"
            r["final_decision"] = "NO_TRADE"
            r["decision_override"] = "PROFESSIONAL_UNCERTAINTY_OR_INVALIDATION_GUARD"
            r["why_not_trade"] = list(dict.fromkeys(_collect(r, ("why_not_trade",)) + ["UNCERTAINTY_OR_INVALIDATION_GUARD"]))

    r["next_action"] = "WAIT" if invalidation_state != "NONE_OBSERVED" or uncertainty in {"HIGH", "VERY_HIGH"} else _first(r, "next_action") or "CONTINUE_DOWNSTREAM_VALIDATION"
    return r
