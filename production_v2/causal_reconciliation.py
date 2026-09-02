from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    for value in (output.get("direction"), output.get("opportunity_direction"), output.get("structure_direction"), output.get("pressure"), output.get("trend_state"), output.get("finding")):
        text = _text(value)
        if text in {"BUY", "UP", "BULLISH", "TREND_UP"} or text.startswith(("BUY ", "BUY_", "BUY:", "BULLISH_")):
            return "BUY"
        if text in {"SELL", "DOWN", "BEARISH", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_", "SELL:", "BEARISH_")):
            return "SELL"
    return "NEUTRAL"


def _space_ok(e5: dict[str, Any], direction: str) -> bool:
    reasons = _text(e5.get("reasons"))
    if direction == "BUY" and "LONG_SPACE_CONSTRAINED" in reasons:
        return False
    if direction == "SELL" and "SHORT_SPACE_CONSTRAINED" in reasons:
        return False
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    value = e5.get(key)
    if isinstance(value, (int, float)):
        return value >= 1.0
    return True


def _event_direction(e4: dict[str, Any]) -> str:
    direction = _direction(e4)
    if direction != "NEUTRAL":
        return direction
    event = _text(e4.get("event") or e4.get("finding"))
    if "FAILED_BREAK_RECLAIM" in event:
        actor = _text(e4.get("response_actor"))
        if actor in {"BUYERS", "BUY", "UP"}:
            return "BUY"
        if actor in {"SELLERS", "SELL", "DOWN"}:
            return "SELL"
        if "UP" in event:
            return "BUY"
        if "DOWN" in event:
            return "SELL"
    if any(token in event for token in ("HIGH_SWEEP_REJECTION", "HIGH_REJECTION")):
        return "SELL"
    if any(token in event for token in ("LOW_SWEEP_REJECTION", "LOW_REJECTION")):
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return "NEUTRAL"


def reconcile_causal_evidence(engines: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Reconcile E1-E6 into opportunity discovery and non-executable setup states."""
    engines = {key: dict(value or {}) for key, value in (engines or {}).items()}
    e1, e2, e3, e4, e5, e6 = (engines.get(key, {}) for key in ("E1", "E2", "E3", "E4", "E5", "E6"))
    e1_direction, e2_direction, e3_direction, e4_direction = _direction(e1), _direction(e2), _direction(e3), _event_direction(e4)
    e2_text = " ".join(_text(e2.get(key)) for key in ("finding", "opportunity_maturity", "state"))
    e2_reasons = _text(e2.get("reasons") or e2.get("reason_codes"))
    e2_eligible = not any(token in e2_reasons for token in ("THESIS_INVALIDATED", "HARD_VETO"))
    e2_developing = any(token in e2_text for token in ("DEVELOPING", "PENDING", "EMERGING", "UNRESOLVED"))
    e2_confirmed = "CONFIRMED" in e2_text
    reasons: list[str] = []
    evidence: list[str] = []
    wait_for: list[str] = []

    # Execution-grade direction still uses the multi-brain vote. Opportunity
    # discovery is intentionally broader and is evaluated below.
    votes = [d for d in (e1_direction, e2_direction, e3_direction) if d in {"BUY", "SELL"}]
    buy_votes, sell_votes = votes.count("BUY"), votes.count("SELL")
    direction = "BUY" if buy_votes >= 2 and buy_votes > sell_votes else "SELL" if sell_votes >= 2 and sell_votes > buy_votes else "NEUTRAL"

    # Discovery anchor: a confirmed external structure direction may be enough to
    # open a WATCH when E2 has not vetoed it and E4 supplies a live auction event.
    # This does NOT promote the event to a setup or trade.
    discovery_direction = direction
    if discovery_direction == "NEUTRAL":
        if e3_direction in {"BUY", "SELL"} and e2_direction == "NEUTRAL" and e2_eligible:
            discovery_direction = e3_direction
        elif e1_direction in {"BUY", "SELL"} and e2_direction == "NEUTRAL" and e2_eligible and e3_direction == "NEUTRAL":
            discovery_direction = e1_direction

    if discovery_direction == "NEUTRAL":
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": ["DIRECTIONAL_CONFLICT"], "wait_for": ["DIRECTIONAL_EDGE", "E6_CAUSAL_SETUP_PROOF"]}

    if e2_direction in {"BUY", "SELL"} and e2_direction != discovery_direction:
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": ["DIRECTIONAL_CONFLICT", "E2_DIRECTION_CONFLICT"], "wait_for": ["DIRECTIONAL_ALIGNMENT", "E6_CAUSAL_SETUP_PROOF"]}

    e1_e3_aligned = e1_direction == discovery_direction and e3_direction == discovery_direction
    e4_counterflow = e4_direction in {"BUY", "SELL"} and e4_direction != discovery_direction
    if e4_counterflow and not e1_e3_aligned:
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": ["DIRECTIONAL_CONFLICT"], "wait_for": ["DIRECTIONAL_ALIGNMENT", "E6_CAUSAL_SETUP_PROOF"]}
    if e4_counterflow:
        reasons.append("E4_COUNTERFLOW_EVENT")
        evidence.append("E4_COUNTERFLOW_IS_COUNTER_EVIDENCE_NOT_INVALIDATION")
        wait_for.append("E4_DIRECTIONAL_RESOLUTION")

    e4_state = _text(e4.get("auction_state") or e4.get("auction_phase"))
    e4_pending = e4_state in {"PENDING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
    e4_confirmed = e4_state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"} or "TERMINAL" in e4_state
    if e4_pending:
        evidence.append("E4_AUCTION_PENDING")
        wait_for.append("AUCTION_CONFIRMATION")
    elif e4_confirmed:
        evidence.append("E4_AUCTION_CONFIRMED")
    else:
        wait_for.append("LIQUIDITY_CONFIRMATION")

    space_ok = _space_ok(e5, discovery_direction)
    if space_ok:
        evidence.append("STRUCTURAL_SPACE_ACCEPTABLE")
    else:
        reasons.append("STRUCTURAL_SPACE_INSUFFICIENT")
        wait_for.append("SUFFICIENT_STRUCTURAL_SPACE")

    e6_setup = _text(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type"))
    e6_has_setup = e6_setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
    e6_reasons = _text(e6.get("reasons") or e6.get("reason_codes"))
    if e6_has_setup and "CAUSAL_SETUP_PROOF_INCOMPLETE" not in e6_reasons and not any(token in e6_reasons for token in ("DIRECTIONAL_EVIDENCE_CONFLICT", "STRUCTURAL_SPACE_INSUFFICIENT")):
        evidence.append("E6_SETUP_PRESENT")
        return {"state": "CAUSAL_SETUP", "direction": discovery_direction, "ready": True, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}

    auction_present = e4_pending or e4_confirmed or bool(_text(e4.get("event") or e4.get("finding")))
    # Opportunity-first discovery accepts one strong upstream anchor (E3 external
    # structure, or E1 pressure) plus a live auction. Economics remain attached as
    # counter-evidence and are never silently discarded.
    anchor_present = e3_direction == discovery_direction or e1_direction == discovery_direction
    if anchor_present and auction_present and e2_eligible and not e2_confirmed:
        if e3_direction == discovery_direction:
            evidence.append("E3_DIRECTIONAL_ANCHOR")
        if e1_direction == discovery_direction:
            evidence.append("E1_DIRECTIONAL_CONTEXT")
        if e2_developing:
            evidence.append("E2_DEVELOPING_OPPORTUNITY")
        if e4_direction == discovery_direction:
            evidence.append("E4_DIRECTIONAL_EVENT")
        if not space_ok:
            evidence.append("SPACE_CONSTRAINT_TRACKED_NOT_OPPORTUNITY_INVALIDATION")
        if not e2_developing:
            reasons.append("E2_OPPORTUNITY_PATH_UNPROVEN")
        wait_for.extend(["E2_OPPORTUNITY_CONFIRMATION", "E6_CAUSAL_SETUP_PROOF"])
        if not space_ok:
            wait_for.append("SUFFICIENT_STRUCTURAL_SPACE")
        state = "CONTESTED_OPPORTUNITY_WATCH" if e4_counterflow or not space_ok or not e1_e3_aligned else "OPPORTUNITY_WATCH"
        return {"state": state, "direction": discovery_direction, "ready": False, "evidence": list(dict.fromkeys(evidence)), "reasons": list(dict.fromkeys(reasons)), "wait_for": list(dict.fromkeys(wait_for))}

    if e2_eligible and (e4_pending or e4_confirmed) and space_ok:
        if e2_confirmed:
            return {"state": "THESIS_CONFIRMED_SETUP_NOT_FORMED", "direction": discovery_direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for + ["E6_CAUSAL_SETUP_PROOF"]}
        if e2_developing:
            return {"state": "DEVELOPING_THESIS", "direction": discovery_direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for + ["E6_CAUSAL_SETUP_PROOF"]}

    reasons.append("NO_CAUSAL_SETUP")
    if "E6_CAUSAL_SETUP_PROOF" not in wait_for:
        wait_for.append("E6_CAUSAL_SETUP_PROOF")
    return {"state": "NO_SETUP", "direction": discovery_direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}
