from __future__ import annotations

from datetime import datetime
from typing import Any

DIRECTIONS = {"BUY", "SELL"}
STAGES = {
    "NO_OPPORTUNITY", "DETECTED", "WATCH", "THESIS_FORMED", "ARMED",
    "CONFIRMED", "EXECUTE", "MANAGE", "INVALIDATED", "EXPIRED", "SUPERSEDED",
}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "TREND_UP"} or text.startswith("BUY "):
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "TREND_DOWN"} or text.startswith("SELL "):
        return "SELL"
    return "NEUTRAL"


def _parse(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.astimezone()
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.astimezone()
    except ValueError:
        return None


def canonical_event_clock(e4: dict[str, Any] | None, current_candle: Any) -> dict[str, Any]:
    """Single event clock for every downstream consumer.

    The nested E4 age is retained only as an audit field. Timestamp distance between
    the causal event candle and the current closed candle is authoritative.
    """
    e4 = dict(e4 or {})
    event_id = str(e4.get("event_id") or e4.get("auction_event_id") or "").strip()
    event_candle = str(e4.get("event_candle_id") or "").strip()
    if not event_candle and event_id:
        event_candle = event_id.split("|", 1)[0]
    event_ts = _parse(event_candle)
    current_ts = _parse(current_candle)
    if event_ts is not None and current_ts is not None and current_ts >= event_ts:
        age = int((current_ts - event_ts).total_seconds() // 300)
    else:
        try:
            age = max(0, int(e4.get("event_age_bars", 0) or 0))
        except (TypeError, ValueError):
            age = 0
    return {
        "event_id": event_id,
        "event_candle": event_candle,
        "current_candle": str(current_candle or "").strip(),
        "age_bars": max(0, age),
        "source": "E4_CAUSAL_EVENT_TIMESTAMP",
        "nested_e4_age_bars": e4.get("event_age_bars"),
        "clock_consistent": e4.get("event_age_bars") in (None, "", age),
    }


def _e4_direction(e4: dict[str, Any]) -> str:
    direct = _direction(e4.get("direction") or e4.get("directional_implication") or e4.get("response_direction"))
    if direct != "NEUTRAL":
        return direct
    event = _text(e4.get("event") or e4.get("finding"))
    if any(token in event for token in ("HIGH_SWEEP_REJECTION", "HIGH_REJECTION", "HIGH_FAILED_BREAK", "HIGH_LIQUIDITY_REJECTION")):
        return "SELL"
    if any(token in event for token in ("LOW_SWEEP_REJECTION", "LOW_REJECTION", "LOW_FAILED_BREAK", "LOW_LIQUIDITY_REJECTION")):
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return "NEUTRAL"


def _has_causal_event(e4: dict[str, Any]) -> bool:
    event = _text(e4.get("event") or e4.get("finding"))
    return bool(event and not any(token in event for token in ("NONE", "NO_LIQUIDITY", "NO_CONFIRMED")))


def derive_opportunity_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Derive opportunity lifecycle without granting execution authority."""
    e1 = dict(payload.get("e1") or {})
    e2 = dict(payload.get("e2") or {})
    e3 = dict(payload.get("e3") or {})
    e4 = dict(payload.get("e4") or {})
    e5 = dict(payload.get("e5") or {})
    e6 = dict(payload.get("e6") or {})
    e7 = dict(payload.get("e7") or {})
    e8 = dict(payload.get("e8") or {})
    e9 = dict(payload.get("e9") or {})

    clock = canonical_event_clock(e4, payload.get("candle"))
    event_direction = _e4_direction(e4)
    e6_direction = _direction(e6.get("direction") or e6.get("direction_thesis"))
    e1_direction = _direction(e1.get("directional_pressure") or e1.get("pressure") or e1.get("trend_state"))
    e2_direction = _direction(e2.get("direction") or e2.get("opportunity_direction"))
    direction = event_direction if event_direction in DIRECTIONS else e6_direction if e6_direction in DIRECTIONS else e2_direction
    if direction not in DIRECTIONS:
        direction = e1_direction

    counter: list[str] = []
    if e1_direction in DIRECTIONS and direction in DIRECTIONS and e1_direction != direction:
        counter.append("E1_COUNTER_EVIDENCE")
    if e3.get("external_state") and _direction(e3.get("external_state")) in DIRECTIONS and _direction(e3.get("external_state")) != direction:
        counter.append("E3_EXTERNAL_COUNTER_EVIDENCE")
    if _text(e3.get("internal_state")) == "MIXED":
        counter.append("E3_INTERNAL_COUNTER_EVIDENCE")

    thesis = bool(e6.get("e6_thesis_proven") or e6.get("setup_exists") or _text(e6.get("thesis_status")) in {"FORMING", "MATURE", "PROVEN", "CONTESTED_WATCH"})
    invalidated = bool(e6.get("invalidated") or _text(e6.get("state")) == "INVALIDATED" or _text(e6.get("thesis_status")) == "INVALIDATED")
    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation"))
    confirmed = confirmation in {"CONFIRMED", "PASS"} and not invalidated
    pre = e8.get("pre_economics") if isinstance(e8.get("pre_economics"), dict) else {}
    pre_tradeable = bool(pre.get("tradeable", _text(e8.get("economic_state")) in {"PRECHECK_PASS", "PASS", "READY"}))
    if not pre:
        pre_tradeable = _text(e8.get("economic_state")) not in {"BLOCKED", "INVALID", "NOT_READY", "UNAVAILABLE"}
    space_key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        space = float(e5.get(space_key, pre.get("space_atr", 0.0)) or 0.0)
    except (TypeError, ValueError):
        space = 0.0
    tradeability = "CONSTRAINED" if space > 0.0 and space < 0.75 else "GOOD" if space >= 0.75 else "UNKNOWN"
    if pre.get("tradeable") is False:
        tradeability = "CONSTRAINED"

    if invalidated:
        stage = "INVALIDATED"
        wait_for = "NEW_CAUSAL_OPPORTUNITY"
    elif confirmed and bool(e9.get("trade_ready")) and _text(e9.get("decision")) == "TRADE":
        stage = "EXECUTE"
        wait_for = "EXECUTION"
    elif confirmed:
        stage = "CONFIRMED"
        wait_for = "E9_EXECUTION_AUTHORIZATION"
    elif thesis and pre_tradeable:
        stage = "ARMED"
        wait_for = "E7_SETUP_SPECIFIC_CONFIRMATION"
    elif thesis or event_direction in DIRECTIONS:
        stage = "THESIS_FORMED" if thesis else "WATCH"
        wait_for = "E7_SETUP_SPECIFIC_CONFIRMATION" if thesis else "E6_CAUSAL_SETUP_PROOF"
    elif _has_causal_event(e4):
        stage = "DETECTED"
        wait_for = "E6_CAUSAL_SETUP_PROOF"
    else:
        stage = "NO_OPPORTUNITY"
        wait_for = "NEW_CAUSAL_OPPORTUNITY"

    if stage == "ARMED" and not pre_tradeable:
        stage = "THESIS_FORMED"
        wait_for = "E8_PRE_ECONOMICS"

    execution_authorized = stage == "EXECUTE" and _text(e9.get("decision")) == "TRADE" and bool(e9.get("trade_ready"))
    return {
        "schema": "PROFESSIONAL_OPPORTUNITY_STATE_V1",
        "stage": stage,
        "direction": direction,
        "event_direction": event_direction,
        "opportunity_id": str(e6.get("opportunity_id") or e4.get("event_id") or "").strip(),
        "causal_event_id": clock["event_id"],
        "canonical_event_clock": clock,
        "thesis_proven": thesis,
        "confirmation_state": confirmation or "PENDING",
        "economic_state": _text(e8.get("economic_state") or e8.get("risk_state") or "UNKNOWN"),
        "tradeability": tradeability,
        "counter_evidence": list(dict.fromkeys(counter)),
        "execution_authorized": execution_authorized,
        "wait_for": wait_for,
        "chase_prohibited": clock["age_bars"] > 1,
        "closed_candle_only": True,
        "e9_authority": True,
    }


def attach(snapshot: dict[str, Any]) -> dict[str, Any]:
    state = derive_opportunity_state(snapshot)
    return {**snapshot, "professional_opportunity": state}
