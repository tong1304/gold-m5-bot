from __future__ import annotations

"""Non-authoritative conflict ledger for the nine-brain market picture."""

from typing import Any
from .contracts import EngineResult

DIRECTIONS = {"BUY", "SELL"}


def _out(results: dict[str, EngineResult], engine_id: str) -> dict[str, Any]:
    engine = results.get(engine_id)
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value or "").upper().strip()


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _direction(output: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(output.get(key))
        if value in DIRECTIONS:
            return value
        if value in {"UP", "BULLISH", "TREND_UP"}:
            return "BUY"
        if value in {"DOWN", "BEARISH", "TREND_DOWN"}:
            return "SELL"
        if value.startswith("BUY ") or value.startswith("BUY_"):
            return "BUY"
        if value.startswith("SELL ") or value.startswith("SELL_"):
            return "SELL"
    return "NEUTRAL"


def _auction_event_direction(event: str) -> str:
    """Map causal auction event semantics to directional implication."""
    text = _text(event)
    if any(token in text for token in ("HIGH_FAILED_BREAK", "HIGH_REJECTION", "HIGH_SWEEP_REJECTION", "HIGH_SWEEP", "HIGH_LIQUIDITY_REJECTION")):
        return "SELL"
    if any(token in text for token in ("LOW_FAILED_BREAK", "LOW_REJECTION", "LOW_SWEEP_REJECTION", "LOW_SWEEP", "LOW_LIQUIDITY_REJECTION")):
        return "BUY"
    if "HIGH_ACCEPTANCE" in text or "HIGH_BREAK" in text:
        return "BUY"
    if "LOW_ACCEPTANCE" in text or "LOW_BREAK" in text:
        return "SELL"
    return "NEUTRAL"


def _item(code: str, severity: str, brains: tuple[str, ...], authority: str, explanation: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "severity": severity, "brains": list(brains), "authority": authority, "explanation": explanation, "evidence": evidence, "resolution": "E9_RECONCILE_WITHOUT_REWRITING_UPSTREAM_FACTS"}


def build_conflict_ledger(results: dict[str, EngineResult]) -> dict[str, Any]:
    e1, e3, e4, e5, e6, e7, e8 = (_out(results, x) for x in ("E1", "E3", "E4", "E5", "E6", "E7", "E8"))
    conflicts: list[dict[str, Any]] = []
    d1 = _direction(e1, ("trend_state", "pressure", "structure", "market_state", "finding"))
    d3 = _direction(e3, ("structure_direction", "external_state", "internal_state", "finding"))
    d6 = _direction(e6, ("direction", "direction_thesis", "thesis_direction", "finding"))
    d5 = _direction(e5, ("direction", "location_direction", "finding"))

    claimed = [(brain, direction) for brain, direction in (("E1", d1), ("E3", d3), ("E6", d6)) if direction in DIRECTIONS]
    if len({direction for _, direction in claimed}) > 1:
        conflicts.append(_item("DIRECTION_EVIDENCE_CONFLICT", "HIGH", tuple(brain for brain, _ in claimed), "E1/E3/E6_ROLE_BOUNDARIES", "Market-state, structure, and setup evidence point in different directions.", {brain: direction for brain, direction in claimed}))

    e3_structure = _text(e3.get("structure_direction") or e3.get("external_state") or e3.get("active_regime") or e3.get("finding"))
    e4_event = _text(e4.get("event") or e4.get("event_type") or e4.get("auction_event") or e4.get("liquidity_event") or e4.get("finding"))
    e4_response = _text(e4.get("response_actor") or e4.get("response_direction") or e4.get("directional_implication"))
    e4_direction = _direction(e4, ("directional_implication", "response_direction", "auction_direction", "direction"))
    if e4_direction not in DIRECTIONS:
        e4_direction = _auction_event_direction(e4_event)
    if d3 in DIRECTIONS and e4_direction in DIRECTIONS and d3 != e4_direction:
        conflicts.append(_item("STRUCTURE_AUCTION_CONFLICT", "MEDIUM", ("E3", "E4"), "E9_RECONCILIATION", "Market structure and the newest auction/liquidity response imply opposite directions; preserve both observations until E9 reconciles them.", {"E3_structure_direction": d3, "E3_structure_state": e3_structure, "E4_event": e4_event, "E4_response": e4_response, "E4_direction": e4_direction}))

    structural_location = _text(e5.get("structural_location") or e5.get("location_state"))
    long_space = _num(e5.get("available_space_atr_long")); short_space = _num(e5.get("available_space_atr_short"))
    if d6 == "BUY" and (structural_location in {"AT_RESISTANCE", "RESISTANCE", "PREMIUM_AT_RESISTANCE"} or (long_space is not None and long_space < 0.5)):
        conflicts.append(_item("DIRECTION_LOCATION_CONFLICT", "HIGH", ("E5", "E6"), "E5", "Bullish setup direction exists, but current location or upside space materially constrains the trade path.", {"setup_direction": d6, "structural_location": structural_location or "UNKNOWN", "available_space_atr_long": long_space}))
    if d6 == "SELL" and (structural_location in {"AT_SUPPORT", "SUPPORT", "DISCOUNT_AT_SUPPORT"} or (short_space is not None and short_space < 0.5)):
        conflicts.append(_item("DIRECTION_LOCATION_CONFLICT", "HIGH", ("E5", "E6"), "E5", "Bearish setup direction exists, but current location or downside space materially constrains the trade path.", {"setup_direction": d6, "structural_location": structural_location or "UNKNOWN", "available_space_atr_short": short_space}))

    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("proof_state")); setup_state = _text(e6.get("setup_state") or e6.get("state") or e6.get("opportunity_state"))
    if d6 in DIRECTIONS and confirmation in {"PENDING", "UNPROVEN", "INCOMPLETE", "UNRESOLVED"} and setup_state in {"ESTABLISHED", "VALIDATING", "MATURE", "READY", "TRADE_READY", "CONFIRMED", "VALIDATED"}:
        conflicts.append(_item("SETUP_CONFIRMATION_TENSION", "MEDIUM", ("E6", "E7"), "E7", "A directional setup exists, but confirmation has not yet crossed its proof gate.", {"setup_direction": d6, "setup_state": setup_state, "confirmation_state": confirmation}))

    risk_state = _text(e8.get("risk_state") or e8.get("economic_state") or e8.get("decision_state"))
    if d6 in DIRECTIONS and risk_state in {"UNRESOLVED", "BLOCKED", "INVALID", "NOT_READY", "RISK_NOT_READY"}:
        conflicts.append(_item("SETUP_ECONOMICS_TENSION", "HIGH", ("E6", "E8"), "E8", "A setup thesis exists, but trade economics or risk survivability is not ready.", {"setup_direction": d6, "risk_state": risk_state}))

    value_state = _text(e5.get("value_state"))
    if d6 == "SELL" and value_state == "PREMIUM":
        conflicts.append(_item("VALUE_SUPPORTS_SELL", "LOW", ("E5", "E6"), "E5", "Premium location is directionally supportive of a short thesis, but is not entry confirmation.", {"value_state": value_state}))
    elif d6 == "BUY" and value_state == "DISCOUNT":
        conflicts.append(_item("VALUE_SUPPORTS_BUY", "LOW", ("E5", "E6"), "E5", "Discount location is directionally supportive of a long thesis, but is not entry confirmation.", {"value_state": value_state}))

    blocking = sum(1 for item in conflicts if item["severity"] == "HIGH"); tensions = sum(1 for item in conflicts if item["severity"] == "MEDIUM"); supportive = sum(1 for item in conflicts if item["severity"] == "LOW")
    return {"schema": "CROSS_BRAIN_CONFLICT_LEDGER_V2", "authority": "NON_AUTHORITATIVE", "principle": "ONE_MARKET_REALITY;_SPECIALISTS_MAY_DISAGREE_WITHIN_THEIR_BOUNDARIES", "conflicts": conflicts, "summary": {"total": len(conflicts), "blocking_conflicts": blocking, "tensions": tensions, "supportive_relations": supportive, "has_conflict": bool(conflicts)}}
