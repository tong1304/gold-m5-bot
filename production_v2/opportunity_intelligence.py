from __future__ import annotations

"""Opportunity-first intelligence for the Production V2 trading brain.

This layer is deliberately non-authoritative: it discovers, ranks and preserves
opportunities without weakening E8 risk controls or E9 final authority.
"""

from typing import Any

DIRECTIONS = ("BUY", "SELL")


def _out(results: dict[str, Any], key: str) -> dict[str, Any]:
    item = results.get(key)
    value = getattr(item, "output", item)
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP"} or text.startswith(("BUY ", "BUY_")):
            return "BUY"
        if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_")):
            return "SELL"
    return "NEUTRAL"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def _event(e4: dict[str, Any]) -> str:
    return _text(e4.get("event") or e4.get("auction_event") or e4.get("liquidity_event") or e4.get("finding"))


def _event_strength(event: str) -> float:
    score = 0.0
    for token, points in (
        ("SWEEP", 25), ("FAILED_BREAK", 25), ("RECLAIM", 22),
        ("REJECTION", 20), ("ACCEPTANCE", 18), ("BREAK", 12),
        ("LIQUIDITY", 10),
    ):
        if token in event:
            score = max(score, float(points))
    return score


def _space(e5: dict[str, Any], direction: str) -> float:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    return _number(e5.get(key) or e5.get("available_space_atr"))


def _location_score(e5: dict[str, Any], direction: str) -> float:
    value = _text(e5.get("value_state") or e5.get("location_state") or e5.get("finding"))
    location = _text(e5.get("structural_location") or e5.get("location"))
    if direction == "BUY" and ("DISCOUNT" in value or location in {"AT_SUPPORT", "BELOW_VALUE"}):
        return 15.0
    if direction == "SELL" and ("PREMIUM" in value or location in {"AT_RESISTANCE", "ABOVE_VALUE"}):
        return 15.0
    if value in {"EQUILIBRIUM", "FAIR_VALUE"}:
        return 7.0
    return 0.0


def _structure_score(e3: dict[str, Any], direction: str) -> float:
    score = 0.0
    for value in (e3.get("structure_direction"), e3.get("external_state"), e3.get("internal_state"), e3.get("direction")):
        if _direction(value) == direction:
            score += 7.0
    if _text(e3.get("structure_integrity") or "VALID") == "VALID":
        score += 6.0
    return min(score, 20.0)


def _pressure_score(e1: dict[str, Any], direction: str) -> float:
    return 15.0 if _direction(e1.get("directional_pressure") or e1.get("pressure") or e1.get("pressure_direction")) == direction else 0.0


def _regime_score(e1: dict[str, Any], e2: dict[str, Any], direction: str) -> float:
    d = _direction(e2.get("direction") or e2.get("opportunity_direction"))
    state = _text(e1.get("market_state") or e1.get("trend_state") or e1.get("state"))
    if d == direction:
        return 5.0
    if direction in state:
        return 4.0
    return 0.0


def _counterflow(e3: dict[str, Any], direction: str) -> bool:
    for key in ("internal_state", "external_state", "structure_direction"):
        d = _direction(e3.get(key))
        if d in DIRECTIONS and d != direction:
            return True
    return False


def _entry_style(event: str, e6: dict[str, Any], e7: dict[str, Any], space: float) -> str:
    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("proof_state"))
    trigger = any(e7.get(k) is True for k in ("trigger_observed", "valid_trigger", "closed_candle_trigger"))
    if trigger and confirmation in {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"}:
        return "CONFIRMED"
    if any(token in event for token in ("SWEEP", "FAILED_BREAK", "REJECTION", "RECLAIM")) and space >= 1.0:
        return "EARLY"
    if any(token in event for token in ("BREAK", "ACCEPTANCE")):
        return "RETEST"
    return "CONFIRMED" if _text(e6.get("opportunity_stage")) in {"SETUP_THESIS", "MATURE"} else "WAIT"


def build_opportunity_intelligence(results: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    e1, e2, e3, e4, e5, e6, e7, e8 = (_out(results, key) for key in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"))
    event = _event(e4)
    event_id = str(e4.get("event_id") or e4.get("auction_event_id") or e4.get("event_candle_id") or "")
    candidates: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        event_score = _event_strength(event)
        structure = _structure_score(e3, direction)
        pressure = _pressure_score(e1, direction)
        location = _location_score(e5, direction)
        regime = _regime_score(e1, e2, direction)
        space = _space(e5, direction)
        space_score = min(10.0, max(0.0, space * 5.0))
        causal = 25.0 if event_score > 0 and _direction(e4.get("direction"), e4.get("response_actor")) == direction else event_score
        score = min(100.0, round(causal + structure + pressure + location + regime + space_score, 2))
        if score < 40.0 and not (event_score and (structure or pressure or location)):
            continue
        counter = _counterflow(e3, direction)
        stage = "HIGH_OPPORTUNITY" if score >= 80 else "ACTIONABLE" if score >= 70 else "WATCH" if score >= 55 else "DEVELOPING"
        style = _entry_style(event, e6, e7, space)
        candidates.append({
            "direction": direction,
            "family": _text(e6.get("setup_family") or e6.get("setup") or ("LIQUIDITY_RESPONSE" if "SWEEP" in event else "AUCTION_OPPORTUNITY")),
            "score": score,
            "stage": stage,
            "entry_style": style,
            "event": event,
            "event_id": event_id,
            "available_space_atr": round(space, 4),
            "counterflow": counter,
            "evidence": {
                "causal_event": causal,
                "structure": structure,
                "pressure": pressure,
                "location": location,
                "regime": regime,
                "space": space_score,
            },
            "thesis_persistence": "PRESERVE_UNTIL_INVALIDATED",
        })
    candidates.sort(key=lambda x: (-x["score"], x["direction"]))
    leader = candidates[0] if candidates else None
    previous = previous or {}
    previous_id = str(previous.get("opportunity_id") or "")
    persistence = "NEW" if not leader or leader["event_id"] != previous_id else "PERSISTING"
    return {
        "architecture": "OPPORTUNITY_FIRST_PROFESSIONAL_TRADER_BRAIN",
        "version": "1.0",
        "authority": "NON_AUTHORITATIVE_UNTIL_E9",
        "principle": "INCOMPLETE_PROOF_IS_NOT_ABSENCE_OF_OPPORTUNITY",
        "candidates": candidates,
        "leader": leader,
        "leader_direction": leader["direction"] if leader else "NEUTRAL",
        "leader_score": leader["score"] if leader else 0.0,
        "leader_stage": leader["stage"] if leader else "NO_OPPORTUNITY",
        "leader_entry_style": leader["entry_style"] if leader else "WAIT",
        "opportunity_persistence": persistence,
        "previous_opportunity_id": previous_id,
        "opportunity_id": f"{leader['direction']}|{leader['family']}|{leader['event_id']}" if leader and leader["event_id"] else (previous_id if leader else ""),
        "preservation_rule": "KEEP_ACTIVE_UNTIL_STRUCTURAL_OR_CAUSAL_INVALIDATION_OR_EXPIRY",
        "risk_boundary": "E8_AND_E9_REMAIN_FINAL_RISK_AUTHORITIES",
    }
