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
    if any(token in event for token in ("HIGH_ACCEPTANCE", "HIGH_BREAK", "HIGH_SWEEP_REJECTION", "HIGH_FAILED_BREAK_RECLAIM")):
        return "BUY" if "ACCEPTANCE" in event or ("BREAK" in event and "RECLAIM" not in event) else "SELL"
    if any(token in event for token in ("LOW_ACCEPTANCE", "LOW_BREAK", "LOW_SWEEP_REJECTION", "LOW_FAILED_BREAK_RECLAIM")):
        return "SELL" if "ACCEPTANCE" in event or ("BREAK" in event and "RECLAIM" not in event) else "BUY"
    return "NEUTRAL"


def reconcile_causal_evidence(engines: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Reconcile E1-E6 into opportunity discovery and non-executable setup states."""
    engines = {key: dict(value or {}) for key, value in (engines or {}).items()}
    e1, e2, e3, e4, e5, e6 = (engines.get(key, {}) for key in ("E1", "E2", "E3", "E4", "E5", "E6"))
    e1_direction, e2_direction, e3_direction, e4_direction = _direction(e1), _direction(e2), _direction(e3), _event_direction(e4)
    votes = [d for d in (e1_direction, e2_direction, e3_direction) if d in {"BUY", "SELL"}]
    buy_votes, sell_votes = votes.count("BUY"), votes.count("SELL")
    direction = "BUY" if buy_votes >= 2 and buy_votes > sell_votes else "SELL" if sell_votes >= 2 and sell_votes > buy_votes else "NEUTRAL"
    reasons: list[str] = []
    evidence: list[str] = []
    wait_for: list[str] = []

    if direction == "NEUTRAL":
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": ["DIRECTIONAL_CONFLICT"], "wait_for": ["DIRECTIONAL_EDGE", "E6_CAUSAL_SETUP_PROOF"]}

    e2_text = " ".join(_text(e2.get(key)) for key in ("finding", "opportunity_maturity", "state"))
    e2_reasons = _text(e2.get("reasons"))
    e2_eligible = not any(token in e2_reasons for token in ("THESIS_INVALIDATED", "HARD_VETO"))
    e2_path_blocked = "NO_ELIGIBLE_OPPORTUNITY_PATH" in e2_reasons
    e2_developing = any(token in e2_text for token in ("DEVELOPING", "PENDING", "CONFIRMED"))
    if not e2_eligible:
        reasons.append("E2_OPPORTUNITY_UNRESOLVED")
        wait_for.append("E2_ELIGIBLE_OPPORTUNITY_PATH")

    # An opposing E4 event is counter-flow evidence, not automatic opportunity
    # invalidation when the E1/E3 directional core agrees. It becomes a hard
    # conflict only when the upstream directional core itself disagrees.
    e4_counterflow = e4_direction in {"BUY", "SELL"} and e4_direction != direction
    core_aligned = e1_direction == direction and e3_direction == direction
    e2_opposes_core = e2_direction in {"BUY", "SELL"} and e2_direction != direction
    if e2_opposes_core:
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": ["DIRECTIONAL_CONFLICT", "E2_DIRECTION_CONFLICT"], "wait_for": ["DIRECTIONAL_ALIGNMENT", "E6_CAUSAL_SETUP_PROOF"]}
    if e4_counterflow and not core_aligned:
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

    space_ok = _space_ok(e5, direction)
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
        return {"state": "CAUSAL_SETUP", "direction": direction, "ready": True, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}

    # Opportunity-first discovery deliberately does NOT require usable target
    # space. Space is an execution/economics constraint; it should be monitored
    # while the market thesis is alive rather than erase the opportunity itself.
    e1_e3_aligned = e1_direction == direction and e3_direction == direction
    auction_present = e4_pending or e4_confirmed or bool(_text(e4.get("event") or e4.get("finding")))
    if e1_e3_aligned and auction_present and not e2_developing:
        evidence.extend(["E1_DIRECTIONAL_CONTEXT", "E3_STRUCTURE_SUPPORT"])
        if e4_direction == direction:
            evidence.append("E4_DIRECTIONAL_EVENT")
        if not space_ok:
            evidence.append("SPACE_CONSTRAINT_TRACKED_NOT_OPPORTUNITY_INVALIDATION")
        if e2_path_blocked:
            reasons.append("E2_OPPORTUNITY_PATH_UNPROVEN")
        wait_for.append("E2_OPPORTUNITY_CONFIRMATION")
        wait_for.append("E6_CAUSAL_SETUP_PROOF")
        if not space_ok:
            wait_for.append("SUFFICIENT_STRUCTURAL_SPACE")
        if e4_counterflow:
            return {"state": "CONTESTED_OPPORTUNITY_WATCH", "direction": direction, "ready": False, "evidence": list(dict.fromkeys(evidence)), "reasons": list(dict.fromkeys(reasons)), "wait_for": list(dict.fromkeys(wait_for))}
        return {"state": "OPPORTUNITY_WATCH", "direction": direction, "ready": False, "evidence": list(dict.fromkeys(evidence)), "reasons": list(dict.fromkeys(reasons)), "wait_for": list(dict.fromkeys(wait_for))}

    if e2_eligible and (e4_pending or e4_confirmed) and space_ok:
        if "CONFIRMED" in e2_text:
            return {"state": "THESIS_CONFIRMED_SETUP_NOT_FORMED", "direction": direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for + ["E6_CAUSAL_SETUP_PROOF"]}
        if e2_developing:
            return {"state": "DEVELOPING_THESIS", "direction": direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for + ["E6_CAUSAL_SETUP_PROOF"]}

    reasons.append("NO_CAUSAL_SETUP")
    if "E6_CAUSAL_SETUP_PROOF" not in wait_for:
        wait_for.append("E6_CAUSAL_SETUP_PROOF")
    return {"state": "NO_SETUP", "direction": direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}
