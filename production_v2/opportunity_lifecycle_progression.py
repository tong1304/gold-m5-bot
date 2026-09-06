from __future__ import annotations

from typing import Any

STAGES = ("WATCH", "CONFIRMED", "E6_THESIS", "E7_CONFIRMED", "E8_READY", "TRADE")
STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}
TERMINAL_STAGES = {"TOO_LATE", "EXPIRED", "INVALIDATED", "REPLACED"}


def _text(value: Any) -> str: return str(value or "").upper().strip()
def _truth(value: Any) -> bool: return _text(value) in {"1", "TRUE", "YES", "PASS", "PASSED", "CONFIRMED", "READY", "TRADE"} if isinstance(value, str) else bool(value)


def _requested_stage(current: dict[str, Any]) -> str:
    execution_state = _text(current.get("execution_state")); lifecycle_state = _text(current.get("lifecycle_state") or current.get("state"))
    if execution_state in TERMINAL_STAGES: return execution_state
    if lifecycle_state in TERMINAL_STAGES: return lifecycle_state
    if _truth(current.get("invalidated")): return "INVALIDATED"
    if execution_state == "POSITION_OPEN" or _truth(current.get("e9_trade")): return "TRADE"
    if _truth(current.get("e8_ready")): return "E8_READY"
    confirmation = _text(current.get("e7_confirmation_state") or current.get("confirmation_state"))
    if _truth(current.get("e7_confirmed")) or confirmation in {"PASS", "PASSED", "CONFIRMED", "TRIGGER_CONFIRMED"}: return "E7_CONFIRMED"
    if _truth(current.get("thesis_proven")): return "E6_THESIS"
    auction = _text(current.get("e4_state") or current.get("auction_state") or current.get("confirmation"))
    if _truth(current.get("confirmed")) or auction in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"}: return "CONFIRMED"
    if _truth(current.get("candidate")): return "WATCH"
    return "IDLE"


def _identity(previous: dict[str, Any], current: dict[str, Any]) -> str:
    existing = str(previous.get("opportunity_id") or current.get("opportunity_id") or "").strip()
    if existing: return existing
    direction = _text(current.get("direction")) or "NEUTRAL"; setup = _text(current.get("setup") or "OPPORTUNITY") or "OPPORTUNITY"; event = str(current.get("event_id") or current.get("origin_event_id") or "").strip()
    return "|".join(part for part in (direction, setup, event) if part)


def _with_event(result: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Advance the event clock while keeping opportunity_id anchored to its origin."""
    event_id = current.get("event_id") or result.get("event_id")
    if event_id: result["event_id"] = event_id
    result["origin_event_id"] = result.get("origin_event_id") or current.get("origin_event_id") or event_id
    return result


def _terminal_result(previous: dict[str, Any], stage: str, current: dict[str, Any]) -> dict[str, Any]:
    reason = _text(current.get("invalidation_reason")) or stage; state = "INVALIDATED" if stage == "INVALIDATED" else "EXPIRED" if stage != "REPLACED" else "REPLACED"
    result = {**previous, "opportunity_id": _identity(previous, current), "lifecycle_stage": stage, "state": state, "lifecycle_state": stage, "opportunity_phase": stage, "trade_authorized": False, "wait_for_stage": "NEW_CAUSAL_OPPORTUNITY", "terminal_stage": stage, "terminal_reason": reason, "invalidation_reason": current.get("invalidation_reason") or previous.get("invalidation_reason") or reason, "last_evaluated_candle": current.get("candle") or previous.get("last_evaluated_candle")}
    result = _with_event(result, current)
    return _record_stage(result, stage, current.get("candle"))


def _record_stage(result: dict[str, Any], stage: str, candle: Any) -> dict[str, Any]:
    history = list(result.get("stage_history") or [])
    if not history or history[-1].get("stage") != stage: history.append({"stage": stage, "candle": str(candle or "")})
    result["stage_history"] = history; result["stage_candle"] = str(candle or result.get("stage_candle") or ""); return result


def advance_lifecycle_stage(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:
    previous = dict(previous or {}); current = dict(current or {}); requested = _requested_stage(current); previous_stage = _text(previous.get("lifecycle_stage")) or "IDLE"
    if requested in TERMINAL_STAGES: return _terminal_result(previous, requested, current)
    if previous_stage in TERMINAL_STAGES:
        previous_event = _text(previous.get("event_id") or previous.get("origin_event_id")); current_event = _text(current.get("event_id") or current.get("origin_event_id"))
        if current_event and previous_event and current_event != previous_event: previous = {"stage_history": []}; previous_stage = "IDLE"
        else: return dict(previous)
    if requested == "IDLE":
        result = {**previous, "opportunity_id": _identity(previous, current), "lifecycle_stage": previous_stage if previous_stage in STAGES else "IDLE", "trade_authorized": False, "last_evaluated_candle": current.get("candle") or previous.get("last_evaluated_candle")}
        result = _with_event(result, current)
        if previous_stage in STAGES: result["wait_for_stage"] = STAGES[min(STAGE_RANK[previous_stage] + 1, len(STAGES) - 1)]; return _record_stage(result, previous_stage, current.get("candle"))
        result["wait_for_stage"] = "WATCH"; return result
    if requested == "TRADE" and not (_truth(current.get("e8_ready")) and (_truth(current.get("e9_trade")) or _text(current.get("execution_state")) == "POSITION_OPEN")): requested = "E8_READY"
    current_rank = STAGE_RANK.get(requested, -1); previous_rank = STAGE_RANK.get(previous_stage, -1)
    if current_rank < 0: return dict(previous)
    if previous_rank < 0: stage = "WATCH" if current_rank > 0 else requested
    elif current_rank <= previous_rank: stage = previous_stage
    else: stage = STAGES[previous_rank + 1]
    result = {**previous, "opportunity_id": _identity(previous, current), "lifecycle_stage": stage, "last_evaluated_candle": current.get("candle") or previous.get("last_evaluated_candle"), "trade_authorized": stage == "TRADE", "terminal_stage": None, "terminal_reason": None}
    result = _with_event(result, current)
    if stage == "WATCH": result.update(wait_for_stage="CONFIRMED", state="WATCHING", opportunity_phase="OPPORTUNITY_WATCH")
    elif stage == "CONFIRMED": result.update(wait_for_stage="E6_THESIS", state="WAITING", opportunity_phase="CONFIRMED")
    elif stage == "E6_THESIS": result.update(wait_for_stage="E7_CONFIRMED", state="WAITING", opportunity_phase="E6_THESIS")
    elif stage == "E7_CONFIRMED": result.update(wait_for_stage="E8_READY", state="WAITING", opportunity_phase="E7_CONFIRMED")
    elif stage == "E8_READY": result.update(wait_for_stage="TRADE", state="READY", opportunity_phase="E8_READY")
    elif stage == "TRADE": result.update(wait_for_stage="POSITION_OPEN", state="EXECUTED", opportunity_phase="TRADE", execution_state="ORDER_INTENT")
    return _record_stage(result, stage, current.get("candle"))
