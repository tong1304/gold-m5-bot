from __future__ import annotations

from typing import Any

from . import e2_brain as _e2_brain


def _promote_directional_context(output: dict[str, Any]) -> dict[str, Any]:
    """Keep a directional opportunity hypothesis alive until confirmation.

    E2 owns opportunity formation, not entry confirmation. When the core has
    independently identified a directional TREND but has not yet observed a
    mature pullback/continuation event, expose the best opportunity hypothesis
    as DEVELOPING instead of collapsing it into WAIT_FOR_REPRICING. E7 remains
    responsible for confirmation and E9 remains the only trade authority.
    """
    if not isinstance(output, dict):
        return output

    regime = str(output.get("regime") or "").upper()
    direction = str(output.get("direction") or "").upper()
    opportunity = str(output.get("opportunity") or "").upper()

    if regime != "TREND" or direction not in {"UP", "DOWN"}:
        return output
    if opportunity not in {"WAIT_FOR_REPRICING", "WAIT_FOR_RANGE_EDGE"}:
        return output

    out = dict(output)
    out["opportunity"] = "TREND_PULLBACK_CONTINUATION"
    out["phase"] = "DEVELOPING"
    out["opportunity_state"] = "DEVELOPING"
    out["opportunity_maturity"] = "DEVELOPING"
    out["quality"] = "DEVELOPING"
    out["opportunity_quality"] = "MEDIUM"
    out["opportunity_decision"] = "WATCH"
    out["edge_assessment"] = "EDGE_CONDITIONAL"
    out["timing_state"] = "READY_FOR_CONFIRMATION"

    missing = list(out.get("missing_evidence") or [])
    missing = [x for x in missing if "clear directional commitment / repricing" not in str(x).lower()]
    for item in ("controlled pullback with directional holding/rejection", "follow-through after pullback"):
        if item not in missing:
            missing.append(item)
    out["missing_evidence"] = missing

    counter = list(out.get("counter_evidence") or [])
    counter = [x for x in counter if "no concrete opportunity setup" not in str(x).lower()]
    out["counter_evidence"] = counter
    out["counter_evidence_severity"] = "MATERIAL" if counter else "MINOR"
    out["thesis"] = (
        f"TREND/{direction} creates TREND_PULLBACK_CONTINUATION at DEVELOPING; "
        "the opportunity thesis is valid context, but confirmation is still required downstream."
    )
    out["why_not_trade"] = [
        "opportunity thesis is developing; the controlled pullback is not yet sufficiently established",
        "entry confirmation belongs to E7; E2 does not infer it from context",
    ]
    out["professional_reasoning"] = dict(out.get("professional_reasoning") or {})
    out["professional_reasoning"].update({
        "conclusion": out["thesis"],
        "timing": "READY_FOR_CONFIRMATION",
        "opportunity_quality": "MEDIUM",
        "opportunity_decision": "WATCH",
        "edge_assessment": "EDGE_CONDITIONAL",
        "required_evidence": list(missing),
        "entry_authorized": False,
        "confirmation_authority": "E7",
    })
    codes = [c for c in list(out.get("reason_codes") or []) if c != "MISSING_OPPORTUNITY_CONFIRMATION"]
    if "OPPORTUNITY_THESIS_ESTABLISHED" not in codes:
        codes.append("OPPORTUNITY_THESIS_ESTABLISHED")
    codes.append("CONFIRMATION_PENDING")
    out["reason_codes"] = list(dict.fromkeys(codes))
    return out


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 wrapper: opportunity thesis first, confirmation later."""
    out = _e2_brain._ORIGINAL_ANALYZE_E2(snapshot) if hasattr(_e2_brain, "_ORIGINAL_ANALYZE_E2") else _e2_brain.analyze_e2(snapshot)
    return _promote_directional_context(out)


_ORIGINAL_ANALYZE_E2 = _e2_brain.analyze_e2
_e2_brain._ORIGINAL_ANALYZE_E2 = _ORIGINAL_ANALYZE_E2
_e2_brain.analyze_e2 = analyze_e2
