from __future__ import annotations
from typing import Any

ACTIVE_STATES = {"WATCHING", "WAITING", "READY"}
TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH"}
VALID_DIRECTIONS = {"BUY", "SELL"}
MAX_WATCH_BARS = 5


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _event_key(v: Any) -> str:
    return str(v or "").strip()


def _identity(direction: Any, setup: Any, event_id: Any = None) -> str:
    d, s, event = _text(direction), _text(setup), _event_key(event_id)
    if d not in VALID_DIRECTIONS or s in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
        return ""
    return f"{d}|{s}|{event}" if event else f"{d}|{s}"


def _same_event(previous_event: Any, current_event: Any) -> bool:
    p, c = _event_key(previous_event), _event_key(current_event)
    if p and c:
        return p.casefold() == c.casefold()
    return not p and not c


def _stable_identity(previous: dict[str, Any], direction: str, setup: str, event_id: Any = None) -> str:
    pid = _event_key(previous.get("opportunity_id")); pd = _text(previous.get("direction")); ps = _text(previous.get("setup")); state = _text(previous.get("state"))
    previous_event = previous.get("event_id") or previous.get("origin_event_id")
    if pid and pd == direction and direction in VALID_DIRECTIONS and _same_event(previous_event, event_id):
        if ps in WATCH_SETUPS and _text(setup) in WATCH_SETUPS:
            return pid
        if ps not in WATCH_SETUPS and ps == _text(setup) and state in ACTIVE_STATES:
            return pid
        if ps in WATCH_SETUPS and _text(setup) not in WATCH_SETUPS and _text(setup) not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
            return pid
    return _identity(direction, setup, event_id)


def _active_previous(p: dict[str, Any]) -> bool:
    return bool(_text(p.get("opportunity_id")) and _text(p.get("direction")) in VALID_DIRECTIONS and _text(p.get("state")) in ACTIVE_STATES)


def _phase(state: str, setup: str, thesis_proven: bool, ready: bool, invalidated: bool) -> str:
    if invalidated:
        return "INVALIDATED"
    if state == "EXPIRED":
        return "EXPIRED"
    if ready:
        return "EXECUTABLE"
    if setup in WATCH_SETUPS:
        return "FORMING" if not thesis_proven else "DEVELOPING"
    if thesis_proven:
        return "TRIGGER_PENDING"
    return "WATCHING"


def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    p, c = dict(previous or {}), dict(current or {})
    d = _text(c.get("direction")); setup = _text(c.get("setup") or c.get("setup_family")); candle = _text(c.get("candle")); event_id = c.get("event_id") or c.get("origin_event_id")
    oid = _stable_identity(p, d, setup, event_id); pid = _event_key(p.get("opportunity_id")); ps = _text(p.get("state")); pd = _text(p.get("direction")); previous_setup = _text(p.get("setup")); active = _active_previous(p)
    previous_event = p.get("event_id") or p.get("origin_event_id"); same_event = _same_event(previous_event, event_id); previous_candle = _text(p.get("last_evaluated_candle")); same_candle = bool(active and candle and previous_candle and candle == previous_candle)
    age = int(p.get("bars_waited", 0) or 0) + (1 if active and not same_candle and same_event else 0)
    invalidated = bool(c.get("invalidated")); candidate = bool(c.get("candidate")); ready = bool(c.get("ready")); thesis_proven = bool(c.get("thesis_proven"))
    base = {**p, "last_evaluated_candle": candle, "trade_authorized": False, "event_id": event_id or p.get("event_id"), "origin_event_id": p.get("origin_event_id") or event_id}

    if c.get("execution_state") == "POSITION_OPEN":
        return {**base, "state": "EXECUTED", "lifecycle_state": "EXECUTED", "opportunity_phase": "EXECUTED", "continuity": "POSITION_OPEN", "execution_state": "POSITION_OPEN"}
    if invalidated:
        if not active:
            return {"state":"IDLE","lifecycle_state":"IDLE","opportunity_phase":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"event_id":event_id,"origin_event_id":event_id}
        return {**base,"state":"INVALIDATED","lifecycle_state":"INVALIDATED","opportunity_phase":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"invalidation_reason":c.get("invalidation_reason") or "CURRENT_CANDLE_INVALIDATED"}
    if active and pd in VALID_DIRECTIONS and d in VALID_DIRECTIONS and d != pd:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"DIRECTION_CHANGED_REPLACED_OPPORTUNITY","previous_opportunity_id":pid,"opportunity_id":oid or _identity(d,setup,event_id),"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"DIRECTION_CHANGED"}
    if active and not same_event and oid and pid and oid != pid:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"NEW_CAUSAL_EVENT_REPLACED_ACTIVE_OPPORTUNITY","previous_opportunity_id":pid,"opportunity_id":oid,"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"NEW_CAUSAL_EVENT"}

    pending_watch = active and previous_setup in WATCH_SETUPS
    if pending_watch and age >= MAX_WATCH_BARS:
        return {**base,"state":"EXPIRED","lifecycle_state":"EXPIRED","opportunity_phase":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
    if pending_watch and bool(c.get("upstream_evidence_lost") or c.get("causal_evidence_lost")):
        return {**base,"state":"INVALIDATED","lifecycle_state":"INVALIDATED","opportunity_phase":"INVALIDATED","continuity":"UPSTREAM_CAUSAL_EVIDENCE_LOST","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"UPSTREAM_CAUSAL_EVIDENCE_LOST"}

    # Promotion from an upstream watch is authorized only by E6's explicit
    # thesis proof. A setup-family/candidate flag alone is not sufficient.
    if pending_watch and thesis_proven and d == pd and oid and setup not in WATCH_SETUPS and setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
        state = "READY" if ready else "WAITING"
        phase = "EXECUTABLE" if ready else "TRIGGER_PENDING"
        return {**base,"state":state,"lifecycle_state":phase,"opportunity_phase":phase,"continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],"invalidation_reason":None}
    if active and pid and oid and pid != oid:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"OPPORTUNITY_ID_CHANGED","previous_opportunity_id":pid,"opportunity_id":oid,"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"OPPORTUNITY_ID_CHANGED"}
    if active and ready and candidate and oid:
        phase = "EXECUTABLE"
        return {**base,"state":"READY","lifecycle_state":phase,"opportunity_phase":phase,"continuity":"ADVANCING_EXISTING_OPPORTUNITY","opportunity_id":pid or oid,"direction":d or pd,"setup":setup or previous_setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"invalidation_reason":None}
    if candidate and oid:
        state = "WATCHING" if setup in WATCH_SETUPS else "WAITING"
        phase = _phase(state, setup, thesis_proven, ready, False)
        continuity = "CONTINUING_UPSTREAM_WATCH" if pending_watch else ("CONTINUING_EXISTING_OPPORTUNITY" if active else "NEW_OPPORTUNITY_WATCH")
        return {**base,"state":state,"lifecycle_state":phase,"opportunity_phase":phase,"continuity":continuity,"opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if active else 0,"origin_candle":p.get("origin_candle") if active else candle,"wait_for":c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],"invalidation_reason":None}
    if active:
        if age >= MAX_WATCH_BARS:
            return {**base,"state":"EXPIRED","lifecycle_state":"EXPIRED","opportunity_phase":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        # An active opportunity that has not proved its causal thesis remains a watch,
        # even when E6 reports the event setup family but no candidate.
        phase = "TRIGGER_PENDING" if thesis_proven else "OPPORTUNITY_WATCH"
        return {**base,"state":ps if ps in ACTIVE_STATES else "WATCHING","lifecycle_state":phase,"opportunity_phase":phase,"continuity":"THESIS_PROVEN_TRIGGER_PENDING" if thesis_proven else "PRESERVING_PENDING_OPPORTUNITY","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION" if not thesis_proven else (c.get("wait_for") or "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"),"invalidation_reason":None}
    return {"state":"IDLE","lifecycle_state":"IDLE","opportunity_phase":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"event_id":event_id,"origin_event_id":event_id}


def advance_lifecycle(previous: dict[str, Any] | None, current: dict[str, Any] | None, bar_id: Any = None) -> dict[str, Any]:
    c = dict(current or {})
    if bar_id is not None:
        c.setdefault("candle", bar_id)
    result = advance_opportunity(previous, c)
    state = _text(result.get("state")); setup = _text(result.get("setup"))
    lifecycle_state = str(result.get("lifecycle_state") or ("OPPORTUNITY_WATCH" if state == "WATCHING" or setup in WATCH_SETUPS else state)).upper()
    phase = str(result.get("opportunity_phase") or lifecycle_state).upper()
    return {**result,"lifecycle_state":lifecycle_state,"opportunity_phase":phase,"age_bars":int(result.get("bars_waited",0) or 0),"wait_for":result.get("wait_for") or "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"}
