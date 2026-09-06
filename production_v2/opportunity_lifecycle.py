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
    """Keep identity across the same causal event; wording gaps never create a new opportunity."""
    pid = _event_key(previous.get("opportunity_id"))
    pd = _text(previous.get("direction"))
    ps = _text(previous.get("setup"))
    state = _text(previous.get("state"))
    previous_event = previous.get("event_id") or previous.get("origin_event_id")
    current_event = _event_key(event_id)
    previous_event_key = _event_key(previous_event)
    current_setup = _text(setup)

    if not pid or pd != direction or direction not in VALID_DIRECTIONS:
        return _identity(direction, setup, event_id)

    if previous_event_key and current_event:
        if _same_event(previous_event_key, current_event):
            if ps in WATCH_SETUPS and current_setup in WATCH_SETUPS:
                return pid
            if ps in WATCH_SETUPS and current_setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
                return pid
            if ps == current_setup and state in ACTIVE_STATES:
                return pid
        return _identity(direction, setup, event_id)

    # Missing event on one or both observations is an evidence/wording gap,
    # not a new causal event. Preserve the active watch identity and event anchor.
    if previous_event_key and not current_event and ps in WATCH_SETUPS and state in ACTIVE_STATES:
        return pid

    if not previous_event_key and not current_event and ps in WATCH_SETUPS and state in ACTIVE_STATES:
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
        return "DEVELOPING" if thesis_proven else "FORMING"
    return "TRIGGER_PENDING"


def _anchor(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    current_anchor = current.get("causal_event_anchor")
    if isinstance(current_anchor, dict) and current_anchor.get("event_id"):
        return dict(current_anchor)
    previous_anchor = previous.get("causal_event_anchor")
    if isinstance(previous_anchor, dict) and previous_anchor.get("event_id"):
        return dict(previous_anchor)
    return {}


def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    p, c = dict(previous or {}), dict(current or {})
    d = _text(c.get("direction")); setup = _text(c.get("setup") or c.get("setup_family")); candle = _text(c.get("candle")); event_id = c.get("event_id") or c.get("origin_event_id")
    oid = _stable_identity(p, d, setup, event_id); pid = _event_key(p.get("opportunity_id")); ps = _text(p.get("state")); pd = _text(p.get("direction")); previous_setup = _text(p.get("setup")); active = _active_previous(p)
    previous_event = p.get("event_id") or p.get("origin_event_id"); same_event = _same_event(previous_event, event_id); previous_candle = _text(p.get("last_evaluated_candle")); same_candle = bool(active and candle and previous_candle and candle == previous_candle)
    event_continuity = same_event or (active and previous_event and not event_id and pd == d and previous_setup in WATCH_SETUPS) or (active and not previous_event and not event_id and pd == d and previous_setup in WATCH_SETUPS)
    age = int(p.get("bars_waited", 0) or 0) + (1 if active and not same_candle and event_continuity else 0)
    invalidated = bool(c.get("invalidated")); candidate = bool(c.get("candidate")); ready = bool(c.get("ready")); thesis_proven = bool(c.get("thesis_proven"))
    causal_anchor = _anchor(p, c)
    base = {**p, "last_evaluated_candle": candle, "trade_authorized": False, "event_id": event_id or p.get("event_id"), "origin_event_id": p.get("origin_event_id") or event_id or p.get("origin_event_id"), "causal_event_anchor": causal_anchor}

    if c.get("execution_state") == "POSITION_OPEN":
        return {**base, "state": "EXECUTED", "lifecycle_state": "EXECUTED", "opportunity_phase": "EXECUTED", "continuity": "POSITION_OPEN", "execution_state": "POSITION_OPEN"}
    if invalidated:
        if not active:
            return {"state":"IDLE","lifecycle_state":"IDLE","opportunity_phase":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"event_id":event_id,"origin_event_id":event_id,"causal_event_anchor":causal_anchor}
        return {**base,"state":"INVALIDATED","lifecycle_state":"INVALIDATED","opportunity_phase":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"invalidation_reason":c.get("invalidation_reason") or "CURRENT_CANDLE_INVALIDATED"}
    if active and pd in VALID_DIRECTIONS and d in VALID_DIRECTIONS and d != pd:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"DIRECTION_CHANGED_REPLACED_OPPORTUNITY","previous_opportunity_id":pid,"opportunity_id":oid or _identity(d,setup,event_id),"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"DIRECTION_CHANGED","causal_event_anchor":causal_anchor}
    if active and not same_event and oid and pid and oid != pid:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"NEW_CAUSAL_EVENT_REPLACED_ACTIVE_OPPORTUNITY","previous_opportunity_id":pid,"opportunity_id":oid,"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"NEW_CAUSAL_EVENT","causal_event_anchor":causal_anchor}

    pending_watch = active and previous_setup in WATCH_SETUPS
    if pending_watch and age >= MAX_WATCH_BARS:
        return {**base,"state":"EXPIRED","lifecycle_state":"EXPIRED","opportunity_phase":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
    if pending_watch and bool(c.get("upstream_evidence_lost") or c.get("causal_evidence_lost")):
        return {**base,"state":"INVALIDATED","lifecycle_state":"INVALIDATED","opportunity_phase":"INVALIDATED","continuity":"UPSTREAM_CAUSAL_EVIDENCE_LOST","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"UPSTREAM_CAUSAL_EVIDENCE_LOST"}

    if pending_watch and thesis_proven and d == pd and oid and setup not in WATCH_SETUPS and setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
        state = "READY" if ready else "WAITING"
        phase = "EXECUTABLE" if ready else "TRIGGER_PENDING"
        return {**base,"state":state,"lifecycle_state":phase,"opportunity_phase":phase,"continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],"invalidation_reason":None}

    if active and pid and oid and pid != oid:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"OPPORTUNITY_ID_CHANGED","previous_opportunity_id":pid,"opportunity_id":oid,"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"OPPORTUNITY_ID_CHANGED","causal_event_anchor":causal_anchor}
    if active and ready and candidate and oid:
        phase = "EXECUTABLE"
        return {**base,"state":"READY","lifecycle_state":phase,"opportunity_phase":phase,"continuity":"ADVANCING_EXISTING_OPPORTUNITY","opportunity_id":pid or oid,"direction":d or pd,"setup":setup or previous_setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"invalidation_reason":None}

    if candidate and oid:
        if setup in WATCH_SETUPS:
            state = "WATCHING"
            lifecycle_state = "OPPORTUNITY_WATCH"
        elif pending_watch and not thesis_proven:
            state = "WATCHING"
            lifecycle_state = "OPPORTUNITY_WATCH"
        else:
            state = "WAITING" if not ready else "READY"
            lifecycle_state = "EXECUTABLE" if ready else "TRIGGER_PENDING"
        phase = "OPPORTUNITY_WATCH" if pending_watch and not thesis_proven else _phase(state, setup, thesis_proven, ready, False)
        if setup in WATCH_SETUPS and pending_watch:
            continuity = "CONTINUING_UPSTREAM_WATCH"
        elif pending_watch and not thesis_proven:
            continuity = "PRESERVING_PENDING_OPPORTUNITY"
        else:
            continuity = "CONTINUING_EXISTING_OPPORTUNITY" if active else "NEW_OPPORTUNITY_WATCH"
        return {**base,"state":state,"lifecycle_state":lifecycle_state,"opportunity_phase":phase,"continuity":continuity,"opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if active else 0,"origin_candle":p.get("origin_candle") if active else candle,"wait_for":c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],"invalidation_reason":None}
    if active:
        if age >= MAX_WATCH_BARS:
            return {**base,"state":"EXPIRED","lifecycle_state":"EXPIRED","opportunity_phase":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        phase = "TRIGGER_PENDING" if thesis_proven else "OPPORTUNITY_WATCH"
        return {**base,"state":ps if ps in ACTIVE_STATES else "WATCHING","lifecycle_state":phase,"opportunity_phase":phase,"continuity":"THESIS_PROVEN_TRIGGER_PENDING" if thesis_proven else "PRESERVING_PENDING_OPPORTUNITY","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION" if not thesis_proven else (c.get("wait_for") or "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"),"invalidation_reason":None}
    return {"state":"IDLE","lifecycle_state":"IDLE","opportunity_phase":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"event_id":event_id,"origin_event_id":event_id,"causal_event_anchor":causal_anchor}


def advance_opportunity_directions(previous: dict[str, Any] | None, current_by_direction: dict[str, dict[str, Any]], *, leader: str = "NEUTRAL", competition: str = "UNCONTESTED") -> dict[str, Any]:
    """Advance BUY and SELL independently; leadership never terminates the counter-direction watch."""
    previous = dict(previous or {})
    previous_map = previous.get("opportunities") if isinstance(previous.get("opportunities"), dict) else {}
    output: dict[str, dict[str, Any]] = {}
    for direction in ("BUY", "SELL"):
        current = dict(current_by_direction.get(direction) or {})
        if not current:
            current = {"candidate": False, "direction": direction, "setup": "OPPORTUNITY_WATCH", "ready": False, "thesis_proven": False, "invalidated": False, "candle": previous.get("last_evaluated_candle"), "causal_event_anchor": previous.get("causal_event_anchor") if isinstance(previous.get("causal_event_anchor"), dict) else {}}
        current["direction"] = direction
        prior = previous_map.get(direction) if isinstance(previous_map.get(direction), dict) else None
        output[direction] = advance_opportunity(prior, current)
    active = [item for item in output.values() if _text(item.get("state")) in ACTIVE_STATES]
    if leader not in VALID_DIRECTIONS or not any(_text(item.get("direction")) == leader for item in active):
        leader = "NEUTRAL" if not active else _text(active[0].get("direction"))
    return {"opportunities": output, "leader": leader, "competition": _text(competition) if _text(competition) else "UNCONTESTED", "active_directions": [direction for direction in ("BUY", "SELL") if _text(output[direction].get("state")) in ACTIVE_STATES], "trade_authorized": False, "state": output.get(leader, {}).get("state", "IDLE") if leader in output else "IDLE", "opportunity_id": output.get(leader, {}).get("opportunity_id") if leader in output else None, "direction": leader, "bars_waited": output.get(leader, {}).get("bars_waited", 0) if leader in output else 0, "last_evaluated_candle": max((_text(item.get("last_evaluated_candle")) for item in output.values()), default="")}


def advance_lifecycle(previous: dict[str, Any] | None, current: dict[str, Any] | None, bar_id: Any = None) -> dict[str, Any]:
    c = dict(current or {})
    if bar_id is not None:
        c.setdefault("candle", bar_id)
    result = advance_opportunity(previous, c)
    state = _text(result.get("state")); setup = _text(result.get("setup"))
    lifecycle_state = str(result.get("lifecycle_state") or ("OPPORTUNITY_WATCH" if state == "WATCHING" or setup in WATCH_SETUPS else state)).upper()
    phase = str(result.get("opportunity_phase") or lifecycle_state).upper()
    return {**result,"lifecycle_state":lifecycle_state,"opportunity_phase":phase,"age_bars":int(result.get("bars_waited",0) or 0),"wait_for":result.get("wait_for") or "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"}
