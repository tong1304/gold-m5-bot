from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    for value in (
        output.get("direction"),
        output.get("opportunity_direction"),
        output.get("structure_direction"),
        output.get("pressure"),
        output.get("trend_state"),
        output.get("finding"),
    ):
        text = _text(value)
        if text in {"BUY", "UP", "BULLISH", "TREND_UP"} or text.startswith(("BUY ", "BUY_", "BUY:")):
            return "BUY"
        if text in {"SELL", "DOWN", "BEARISH", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_", "SELL:")):
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


def reconcile_causal_evidence(engines: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Reconcile E1-E6 evidence into a non-executable causal thesis state.

    This function deliberately prefers NO_SETUP over a fabricated thesis when
    directional evidence conflicts. It does not authorize trades.
    """
    engines = {key: dict(value or {}) for key, value in (engines or {}).items()}
    e1, e2, e3, e4, e5, e6 = (engines.get(key, {}) for key in ("E1", "E2", "E3", "E4", "E5", "E6"))

    e1_direction = _direction(e1)
    e2_direction = _direction(e2)
    e3_direction = _direction(e3)
    e4_direction = _direction(e4)

    votes = [d for d in (e1_direction, e2_direction, e3_direction) if d in {"BUY", "SELL"}]
    buy_votes = votes.count("BUY")
    sell_votes = votes.count("SELL")
    direction = "BUY" if buy_votes >= 2 and buy_votes > sell_votes else "SELL" if sell_votes >= 2 and sell_votes > buy_votes else "NEUTRAL"

    reasons: list[str] = []
    evidence: list[str] = []
    wait_for: list[str] = []

    if direction == "NEUTRAL":
        reasons.append("DIRECTIONAL_CONFLICT")
        wait_for.extend(["DIRECTIONAL_EDGE", "E6_CAUSAL_SETUP_PROOF"])
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}

    conflicting = any(d in {"BUY", "SELL"} and d != direction for d in (e1_direction, e2_direction, e3_direction, e4_direction))
    if conflicting:
        reasons.append("DIRECTIONAL_CONFLICT")
        wait_for.extend(["DIRECTIONAL_ALIGNMENT", "E6_CAUSAL_SETUP_PROOF"])
        return {"state": "NO_SETUP", "direction": "NEUTRAL", "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}

    e2_text = " ".join(_text(e2.get(key)) for key in ("finding", "opportunity_maturity", "state"))
    e2_reasons = _text(e2.get("reasons"))
    e2_eligible = not any(token in e2_reasons for token in ("NO_ELIGIBLE_OPPORTUNITY_PATH", "THESIS_INVALIDATED", "HARD_VETO"))
    e2_developing = any(token in e2_text for token in ("DEVELOPING", "PENDING", "CONFIRMED"))
    if not e2_eligible:
        reasons.append("E2_OPPORTUNITY_UNRESOLVED")
        wait_for.append("E2_ELIGIBLE_OPPORTUNITY_PATH")

    e4_state = _text(e4.get("auction_state") or e4.get("auction_phase"))
    e4_pending = e4_state in {"PENDING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
    e4_confirmed = e4_state in {"CONFIRMED", "TERMINALLY_CONFIRMED"}
    if e4_pending:
        evidence.append("E4_AUCTION_PENDING")
        wait_for.append("AUCTION_CONFIRMATION")
    elif e4_confirmed:
        evidence.append("E4_AUCTION_CONFIRMED")
    else:
        wait_for.append("LIQUIDITY_CONFIRMATION")

    if _space_ok(e5, direction):
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

    if e2_eligible and (e4_pending or e4_confirmed) and _space_ok(e5, direction):
        if "CONFIRMED" in e2_text:
            return {"state": "THESIS_CONFIRMED_SETUP_NOT_FORMED", "direction": direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for + ["E6_CAUSAL_SETUP_PROOF"]}
        if e2_developing:
            return {"state": "DEVELOPING_THESIS", "direction": direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for + ["E6_CAUSAL_SETUP_PROOF"]}

    reasons.append("NO_CAUSAL_SETUP")
    if "E6_CAUSAL_SETUP_PROOF" not in wait_for:
        wait_for.append("E6_CAUSAL_SETUP_PROOF")
    return {"state": "NO_SETUP", "direction": direction, "ready": False, "evidence": evidence, "reasons": reasons, "wait_for": wait_for}
