from __future__ import annotations

from typing import Any

STAGES = ("WATCH", "CONFIRMED", "E6_THESIS", "E7_CONFIRMED", "E8_READY", "TRADE")
STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}
TERMINAL_STAGES = {"TOO_LATE", "EXPIRED", "INVALIDATED", "REPLACED"}
_PLACEHOLDERS = {"", "NONE", "UNKNOWN", "NO_SETUP", "NO_PLAUSIBLE_SETUP", "UNRESOLVED", "NOT_APPLICABLE", "PENDING"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _truth(value: Any) -> bool:
    return _text(value) in {"1", "TRUE", "YES", "PASS", "PASSED", "CONFIRMED", "READY", "TRADE"} if isinstance(value, str) else bool(value)


def _meaningful(value: Any) -> str:
    value = _text(value)
    return "" if value in _PLACEHOLDERS else value


def _requested_stage(current: dict[str, Any]) -> str:
    execution_state = _text(current.get("execution_state")); lifecycle_state = _text(current.get("lifecycle_state") or current.get("state"))
    if execution_state in TERMINAL_STAGES: return execution_state
    if lifecycle_state in TERMINAL_STAGES: return lifecycle_state
    if _truth(current.get("invalidated")): return "INVALIDATED"
    if _truth(current.get("e9_trade")): return "TRADE"
    if _truth(current.get("e8_ready")): return "E8_READY"
    confirmation = _text(current.get("e7_confirmation_state") or current.get("confirmation_state"))
    if _truth(current.get("e7_confirmed")) or confirmation in {"PASS", "PASSED", "CONFIRMED", "TRIGGER_CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"}: return "E7_CONFIRMED"
    if _truth(current.get("thesis_proven")): return "E6_THESIS"
    auction = _text(current.get("e4_state") or current.get("auction_state") or current.get("confirmation"))
    if _truth(current.get("confirmed")) or auction in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"}: return "CONFIRMED"
    if _truth(current.get("candidate")) and _text(current.get("direction")) in {"BUY", "SELL"}: return "WATCH"
    return "IDLE"


def _identity_direction(opportunity_id: Any) -> str:
    value = str(opportunity_id or "").strip()
    return _text(value.split("|", 1)[0]) if value else ""


def _identity_event(opportunity_id: Any) -> str:
    parts = str(opportunity_id or "").strip().split("|")
    return parts[2].strip() if len(parts) >= 3 else ""


def _identity(previous: dict[str, Any], current: dict[str, Any]) -> str:
    current_direction = _text(current.get("direction"))
    previous_direction = _text(previous.get("direction"))
    previous_id = str(previous.get("opportunity_id") or "").strip()
    current_event = str(current.get("event_id") or current.get("origin_event_id") or "").strip()
    previous_event = str(previous.get("event_id") or previous.get("origin_event_id") or _identity_event(previous_id) or "").strip()
    if previous_id and current_direction in {"BUY", "SELL"} and previous_direction == current_direction:
        if not current_event or not previous_event or current_event == previous_event:
            return previous_id
    explicit = str(current.get("opportunity_id") or "").strip()
    if explicit and current_direction in {"BUY", "SELL"}:
        explicit_direction = _identity_direction(explicit)
        explicit_event = _identity_event(explicit)
        if explicit_direction == current_direction and (not current_event or not explicit_event or explicit_event == current_event):
            return explicit
    if current_direction not in {"BUY", "SELL"}: return ""
    setup = _text(current.get("setup") or "OPPORTUNITY") or "OPPORTUNITY"; event = current_event
    return "|".join(part for part in (current_direction, setup, event) if part)


def _with_event(result: dict[str, Any], current: dict[str, Any], *, new_identity: bool = False) -> dict[str, Any]:
    event_id = current.get("event_id") or result.get("event_id")
    if event_id: result["event_id"] = event_id
    if new_identity:
        result["origin_event_id"] = current.get("origin_event_id") or event_id
    else:
        result["origin_event_id"] = result.get("origin_event_id") or current.get("origin_event_id") or event_id
    result["last_progression_candle"] = current.get("candle") or result.get("last_progression_candle") or result.get("last_evaluated_candle")
    return result


def _record_stage(result: dict[str, Any], stage: str, candle: Any) -> dict[str, Any]:
    history = list(result.get("stage_history") or [])
    if not history or history[-1].get("stage") != stage: history.append({"stage": stage, "candle": str(candle or "")})
    result["stage_history"] = history; result["stage_candle"] = str(candle or result.get("stage_candle") or ""); return result


def _terminal_result(previous: dict[str, Any], stage: str, current: dict[str, Any]) -> dict[str, Any]:
    reason = _text(current.get("invalidation_reason")) or stage; state = "INVALIDATED" if stage == "INVALIDATED" else "EXPIRED" if stage != "REPLACED" else "REPLACED"
    identity = _identity(previous, current)
    new_identity = bool(identity and identity != str(previous.get("opportunity_id") or "").strip())
    result = {**previous, "opportunity_id": identity or previous.get("opportunity_id"), "direction": _text(current.get("direction")) or previous.get("direction"), "lifecycle_stage": stage, "state": state, "lifecycle_state": stage, "opportunity_phase": stage, "trade_authorized": False, "wait_for_stage": "NEW_CAUSAL_OPPORTUNITY", "terminal_stage": stage, "terminal_reason": reason, "invalidation_reason": current.get("invalidation_reason") or previous.get("invalidation_reason") or reason}
    return _record_stage(_with_event(result, current, new_identity=new_identity), stage, current.get("candle"))


def _timing_fields(current: dict[str, Any]) -> dict[str, Any]:
    timing = current.get("opportunity_timing") if isinstance(current.get("opportunity_timing"), dict) else {}
    phase = _text(current.get("opportunity_phase") or timing.get("phase"))
    speed = _text(current.get("opportunity_speed") or current.get("opportunity_decision_speed") or timing.get("decision_speed"))
    confirmation_window = current.get("confirmation_window") or timing.get("confirmation_window")
    wait_for = current.get("wait_for") or timing.get("wait_for")
    chase_prohibited = bool(current.get("chase_prohibited", False))
    if phase == "EARLY_OPPORTUNITY":
        confirmation_window = confirmation_window or "NEXT_CLOSED_M5_CANDLE"
        wait_for = wait_for or ("FAST_CLOSED_CANDLE_CONFIRMATION" if speed == "FAST" else "CLOSED_CANDLE_CONFIRMATION")
    elif phase == "LATE_OPPORTUNITY":
        speed = "SLOW"
        confirmation_window = confirmation_window or "NEW_CAUSAL_EVENT"
        wait_for = "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
        chase_prohibited = True
    return {"opportunity_phase": phase, "opportunity_speed": speed, "confirmation_window": confirmation_window, "wait_for": wait_for, "chase_prohibited": chase_prohibited}


def _persist_evidence(result: dict[str, Any], previous: dict[str, Any], current: dict[str, Any]) -> None:
    """Carry live E6/E7 evidence forward unless explicitly invalidated or replaced."""
    previous_thesis = _meaningful(previous.get("thesis_state") or previous.get("e6_thesis_state"))
    current_thesis = _meaningful(current.get("thesis_state") or current.get("e6_thesis_state"))
    if previous_thesis and not current_thesis:
        result["thesis_state"] = previous_thesis
    elif current_thesis:
        result["thesis_state"] = current_thesis

    prior_missing = [str(x).strip() for x in (previous.get("missing_proof") or previous.get("missing_evidence") or []) if str(x).strip()]
    current_missing = [str(x).strip() for x in (current.get("missing_proof") or current.get("missing_evidence") or []) if str(x).strip()]
    if prior_missing and not _truth(current.get("invalidated")):
        result["missing_proof"] = list(dict.fromkeys(prior_missing + current_missing))

    prior_e7 = _meaningful(previous.get("e7_confirmation_state") or previous.get("confirmation_state"))
    current_e7 = _meaningful(current.get("e7_confirmation_state") or current.get("confirmation_state"))
    if prior_e7 in {"CONFIRMING", "DEVELOPING"} and current_e7 not in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY", "INVALIDATED"}:
        result["e7_confirmation_state"] = prior_e7
    elif current_e7:
        result["e7_confirmation_state"] = current_e7


def advance_lifecycle_stage(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:
    previous = dict(previous or {}); current = dict(current or {}); requested = _requested_stage(current); previous_stage = _text(previous.get("lifecycle_stage")) or "IDLE"
    if requested in TERMINAL_STAGES: return _terminal_result(previous, requested, current)
    if previous_stage in TERMINAL_STAGES:
        previous_event = _text(previous.get("event_id") or previous.get("origin_event_id")); current_event = _text(current.get("event_id") or current.get("origin_event_id"))
        if current_event and previous_event and current_event != previous_event: previous = {"stage_history": []}; previous_stage = "IDLE"
        else: return dict(previous)
    if requested == "IDLE":
        identity = _identity(previous, current); new_identity = bool(identity and identity != str(previous.get("opportunity_id") or "").strip())
        result = {**previous, "opportunity_id": identity, "lifecycle_stage": previous_stage if previous_stage in STAGES else "IDLE", "trade_authorized": False, "last_evaluated_candle": current.get("candle") or previous.get("last_evaluated_candle")}
        result = _with_event(result, current, new_identity=new_identity)
        if previous_stage in STAGES: result["wait_for_stage"] = STAGES[min(STAGE_RANK[previous_stage] + 1, len(STAGES) - 1)]; return _record_stage(result, previous_stage, current.get("candle"))
        result["wait_for_stage"] = "WATCH"; return result
    if requested == "TRADE" and not (_truth(current.get("e8_ready")) and _truth(current.get("e9_trade"))): requested = "E8_READY"
    current_rank = STAGE_RANK.get(requested, -1); previous_rank = STAGE_RANK.get(previous_stage, -1)
    if current_rank < 0: return dict(previous)
    if previous_rank < 0: stage = "WATCH" if current_rank > 0 else requested
    elif current_rank <= previous_rank: stage = previous_stage
    else: stage = requested
    identity = _identity(previous, current); new_identity = bool(identity and identity != str(previous.get("opportunity_id") or "").strip())
    result = {**previous, "opportunity_id": identity, "lifecycle_stage": stage, "last_evaluated_candle": current.get("candle") or previous.get("last_evaluated_candle"), "trade_authorized": stage == "TRADE", "terminal_stage": None, "terminal_reason": None, "direction": _text(current.get("direction")) or previous.get("direction")}
    result = _with_event(result, current, new_identity=new_identity)
    _persist_evidence(result, previous, current)
    timing = _timing_fields(current)
    result.update({key: value for key, value in timing.items() if value not in (None, "")})
    if stage == "WATCH":
        result.update(wait_for_stage=timing.get("wait_for") or "CONFIRMED", state="WATCHING", opportunity_phase=timing.get("opportunity_phase") or "OPPORTUNITY_WATCH", execution_state="NONE")
    elif stage == "CONFIRMED": result.update(wait_for_stage="E6_THESIS", state="WAITING", opportunity_phase="CONFIRMED", execution_state="NONE")
    elif stage == "E6_THESIS": result.update(wait_for_stage="E7_CONFIRMED", state="WAITING", opportunity_phase="E6_THESIS", execution_state="NONE")
    elif stage == "E7_CONFIRMED": result.update(wait_for_stage="E8_READY", state="WAITING", opportunity_phase="E7_CONFIRMED", execution_state="NONE")
    elif stage == "E8_READY": result.update(wait_for_stage="TRADE", state="READY", opportunity_phase="E8_READY", execution_state="NONE")
    elif stage == "TRADE": result.update(wait_for_stage="USER_ACTION_REQUIRED", state="ALERT_READY", opportunity_phase="TRADE", execution_state="ALERT_READY")
    return _record_stage(result, stage, current.get("candle"))
