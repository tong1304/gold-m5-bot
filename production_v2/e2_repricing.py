from __future__ import annotations

from typing import Any


_DIRECTIONAL_OPPORTUNITIES = {
    "TREND_PULLBACK_CONTINUATION",
    "TREND_CONTINUATION",
    "BREAKOUT_CONTINUATION",
}


def preserve_repricing_thesis(output: dict[str, Any]) -> dict[str, Any]:
    """Keep a still-valid directional E2 thesis alive while waiting for repricing.

    This is deliberately E2-only. It never creates an entry, trigger, risk plan,
    gate, or trade decision. An explicitly invalidated thesis is never resurrected.
    """
    result = dict(output)
    reasons = list(result.get("reason_codes") or [])
    invalidation = list(result.get("invalidation_evidence") or [])
    direction = str(result.get("direction") or "NEUTRAL").upper()
    regime = str(result.get("regime") or "").upper()
    opportunity = str(result.get("opportunity") or "").upper()
    evidence_map = result.get("evidence_map") or {}
    space_ok = evidence_map.get("space_ok")
    overextended = bool(evidence_map.get("overextended"))

    if invalidation or "THESIS_INVALIDATED" in reasons:
        return result
    if regime != "TREND" or direction not in {"UP", "DOWN"}:
        return result
    if opportunity not in _DIRECTIONAL_OPPORTUNITIES:
        return result

    # A directional thesis remains alive when the market has not invalidated it,
    # but current location/path is poor for participation and repricing is needed.
    missing = list(result.get("missing_evidence") or [])
    poor_location = space_ok is False or overextended or str(result.get("location_context") or "") in {"EDGE_LOW", "EDGE_HIGH"}
    if not poor_location:
        return result

    result["opportunity_state"] = "WAITING_REPRICING"
    result["opportunity_maturity"] = "WAITING_REPRICING"
    result["timing_state"] = "WAIT_FOR_REPRICING"
    result["opportunity_decision"] = "WATCH"
    result["edge_assessment"] = "EDGE_CONDITIONAL"
    result["counter_evidence_severity"] = "MATERIAL" if result.get("counter_evidence") else "NONE"
    if "WAITING_REPRICING" not in reasons:
        reasons.append("WAITING_REPRICING")
    result["reason_codes"] = list(dict.fromkeys(reasons))
    result["missing_evidence"] = list(dict.fromkeys(missing + ["repricing into a favorable participation area"]))
    result["why_not_trade"] = list(dict.fromkeys(list(result.get("why_not_trade") or []) + ["current location is unfavorable; preserve thesis and wait for repricing"]))

    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning["timing"] = "WAIT_FOR_REPRICING"
    reasoning["opportunity_decision"] = "WATCH"
    reasoning["repricing_required"] = True
    reasoning["thesis_preserved"] = True
    reasoning["entry_authorized"] = False
    result["professional_reasoning"] = reasoning
    return result
