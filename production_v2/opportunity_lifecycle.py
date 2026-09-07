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
    d, s, e = _text(direction), _text(setup), _event_key(event_id)
    if d not in VALID_DIRECTIONS or s in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
        return ""
    return f"{d}|{s}|{e}" if e else f"{d}|{s}"


def _same_event(a: Any, b: Any) -> bool:
    a, b = _event_key(a), _event_key(b)
    return a.casefold() == b.casefold() if a and b else (not a and not b)


def _active(p: dict[str, Any]) -> bool:
    return bool(_event_key(p.get("opportunity_id")) and _text(p.get("direction")) in VALID_DIRECTIONS and _text(p.get("state")) in ACTIVE_STATES)


def _anchor(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    a = current.get("causal_event_anchor")
    if isinstance(a, dict) and a.get("event_id"):
        return dict(a)
    a = previous.get("causal_event_anchor")
    return dict(a) if isinstance(a, dict) else {}


def _stable_identity(previous: dict[str, Any], direction: str, setup: str, event_id: Any = None) -> str:
    pid = _event_key(previous.get("opportunity_id"))
    pd = _text(previous.get("direction"))
    ps = _text(previous.get("setup"))
    if not pid or pd != direction:
        return _identity(direction, setup, event_id)
    pe = _event_key(previous.get("event_id") or previous.get("origin_event_id"))
    ce = _event_key(event_id)
    if pe and ce and _same_event(pe, ce):
        return pid
    if ps in WATCH_SETUPS and _text(previous.get("state")) in ACTIVE_STATES:
        # A new causal event replaces the event anchor, but the lifecycle remains
        # an active WATCH. The terminal REPLACED record belongs to history, not
        # to the active state returned to the pipeline.
        return _identity(direction, setup, ce)
    return _identity(direction, setup, ce)


def _base(p: dict[str, Any], c: dict[str, Any], event_id: Any, candle: str, anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        **p,
        "last_evaluated_candle": candle,
        "trade_authorized": False,
        "event_id": event_id or p.get("event_id"),
        "origin_event_id": p.get("origin_event_id") or event_id or p.get("origin_event_id"),
        "causal_event_anchor": anchor,
    }


def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    p, c = dict(previous or {}), dict(current or {})
    d = _text(c.get("direction")); setup = _text(c.get("setup") or c.get("setup_family"))
    candle = _text(c.get("candle")); event_id = c.get("event_id") or c.get("origin_event_id")
    pid = _event_key(p.get("opportunity_id")); ps = _text(p.get("state")); pd = _text(p.get("direction")); previous_setup = _text(p.get("setup")); active = _active(p)
    previous_event = p.get("event_id") or p.get("origin_event_id")
    same_event = _same_event(previous_event, event_id)
    previous_candle = _text(p.get("last_evaluated_candle"))
    same_candle = bool(active and candle and previous_candle and candle == previous_candle)
    continuity = same_event or (active and pd == d and previous_setup in WATCH_SETUPS)
    age = int(p.get("bars_waited", 0) or 0) + (1 if active and not same_candle and continuity else 0)
    invalidated = bool(c.get("invalidated")); candidate = bool(c.get("candidate")); ready = bool(c.get("ready")); thesis = bool(c.get("thesis_proven"))
    anchor = _anchor(p, c)
    base = _base(p, c, event_id, candle, anchor)

    if c.get("execution_state") == "POSITION_OPEN":
        return {**base, "state":"EXECUTED", "lifecycle_state":"EXECUTED", "opportunity_phase":"EXECUTED", "continuity":"POSITION_OPEN", "execution_state":"POSITION_OPEN"}

    if invalidated:
        if not active:
            return {"state":"IDLE","lifecycle_state":"IDLE","opportunity_phase":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"event_id":event_id,"origin_event_id":event_id,"causal_event_anchor":anchor}
        return {**base,"state":"INVALIDATED","lifecycle_state":"INVALIDATED","opportunity_phase":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"invalidation_reason":c.get("invalidation_reason") or "CURRENT_CANDLE_INVALIDATED"}

    # Direction changes are genuine replacement events.
    if active and pd in VALID_DIRECTIONS and d in VALID_DIRECTIONS and d != pd:
        return {**c,"state":"REPLACED","lifecycle_state":"REPLACED","opportunity_phase":"REPLACED","continuity":"DIRECTION_CHANGED_REPLACED_OPPORTUNITY","previous_opportunity_id":pid,"opportunity_id":_identity(d,setup,event_id),"event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"DIRECTION_CHANGED","causal_event_anchor":anchor}

    # A new same-direction causal event must become the new ACTIVE WATCH.
    # Do not expose REPLACED as the active state; historical replacement is
    # represented by previous_opportunity_id and continuity metadata.
    new_event = bool(active and pd == d and previous_event and event_id and not same_event)
    if new_event and previous_setup in WATCH_SETUPS:
        oid = _identity(d, setup or "OPPORTUNITY_WATCH", event_id)
        return {**c,"state":"WATCHING","lifecycle_state":"OPPORTUNITY_WATCH","opportunity_phase":"OPPORTUNITY_WATCH","continuity":"NEW_CAUSAL_EVENT_REPLACED_ACTIVE_WATCH","previous_opportunity_id":pid,"opportunity_id":oid,"direction":d,"setup":setup or "OPPORTUNITY_WATCH","event_id":event_id,"origin_event_id":event_id,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"wait_for":c.get("wait_for") or "NEXT_CLOSED_M5_CANDLE","causal_event_anchor":anchor}

    pending_watch = active and previous_setup in WATCH_SETUPS
    if pending_watch and age >= MAX_WATCH_BARS:
        return {**base,"state":"EXPIRED","lifecycle_state":"EXPIRED","opportunity_phase":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
    if pending_watch and bool(c.get("upstream_evidence_lost") or c.get("causal_evidence_lost")):
        return {**base,"state":"INVALIDATED","lifecycle_state":"INVALIDATED","opportunity_phase":"INVALIDATED","continuity":"UPSTREAM_CAUSAL_EVIDENCE_LOST","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"UPSTREAM_CAUSAL_EVIDENCE_LOST"}

    oid = _stable_identity(p, d, setup, event_id)
    if pending_watch and thesis and d == pd and setup not in WATCH_SETUPS and setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}:
        state = "READY" if ready else "WAITING"
        phase = "EXECUTABLE" if ready else "TRIGGER_PENDING"
        return {**base,"state":state,"lifecycle_state":phase,"opportunity_phase":phase,"continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY","opportunity_id":oid or pid,"direction":d,"setup":setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],"invalidation_reason":None}

    if active and ready and candidate:
        return {**base,"state":"READY","lifecycle_state":"EXECUTABLE","opportunity_phase":"EXECUTABLE","continuity":"ADVANCING_EXISTING_OPPORTUNITY","opportunity_id":pid or oid,"direction":d or pd,"setup":setup or previous_setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"invalidation_reason":None}

    if candidate and oid:
        watch = setup in WATCH_SETUPS or (pending_watch and not thesis)
        if watch:
            state, lifecycle, phase = "WATCHING", "OPPORTUNITY_WATCH", "OPPORTUNITY_WATCH"
        else:
            state = "READY" if ready else "WAITING"
            lifecycle = "EXECUTABLE" if ready else "TRIGGER_PENDING"
            phase = lifecycle
        return {**base,"state":state,"lifecycle_state":lifecycle,"opportunity_phase":phase,"continuity":"CONTINUING_UPSTREAM_WATCH" if setup in WATCH_SETUPS and pending_watch else ("PRESERVING_PENDING_OPPORTUNITY" if pending_watch else ("CONTINUING_EXISTING_OPPORTUNITY" if active else "NEW_OPPORTUNITY_WATCH")),"opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if active else 0,"origin_candle":p.get("origin_candle") if active else candle,"wait_for":c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],"invalidation_reason":None}

    if active:
        phase = "TRIGGER_PENDING" if thesis else "OPPORTUNITY_WATCH"
        return {**base,"state":ps if ps in ACTIVE_STATES else "WATCHING","lifecycle_state":phase,"opportunity_phase":phase,"continuity":"THESIS_PROVEN_TRIGGER_PENDING" if thesis else "PRESERVING_PENDING_OPPORTUNITY","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":c.get("wait_for") or ("E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION" if thesis else "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"),"invalidation_reason":None}

    return {"state":"IDLE","lifecycle_state":"IDLE","opportunity_phase":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None,"event_id":event_id,"origin_event_id":event_id,"causal_event_anchor":anchor}


def advance_opportunity_directions(previous: dict[str, Any] | None, current_by_direction: dict[str, dict[str, Any]], *, leader: str = "NEUTRAL", competition: str = "UNCONTESTED") -> dict[str, Any]:
    previous = dict(previous or {})
    previous_map = previous.get("opportunities") if isinstance(previous.get("opportunities"), dict) else {}
    output = {}
    for direction in ("BUY", "SELL"):
        current = dict(current_by_direction.get(direction) or {})
        current.setdefault("direction", direction)
        if not current.get("candle"):
            current["candle"] = previous.get("last_evaluated_candle")
        prior = previous_map.get(direction) if isinstance(previous_map.get(direction), dict) else None
        output[direction] = advance_opportunity(prior, current)
    active = [v for v in output.values() if _text(v.get("state")) in ACTIVE_STATES]
    if leader not in VALID_DIRECTIONS or not any(_text(v.get("direction")) == leader for v in active):
        leader = "NEUTRAL" if not active else _text(active[0].get("direction"))
    lead = output.get(leader, {}) if leader in output else {}
    return {"opportunities":output,"leader":leader,"competition":_text(competition) or "UNCONTESTED","active_directions":[d for d in ("BUY","SELL") if _text(output[d].get("state")) in ACTIVE_STATES],"trade_authorized":False,"state":lead.get("state","IDLE"),"opportunity_id":lead.get("opportunity_id"),"direction":leader,"bars_waited":lead.get("bars_waited",0),"last_evaluated_candle":max((_text(v.get("last_evaluated_candle")) for v in output.values()),default="")}


def advance_lifecycle(previous: dict[str, Any] | None, current: dict[str, Any] | None, bar_id: Any = None) -> dict[str, Any]:
    c = dict(current or {})
    if bar_id is not None:
        c.setdefault("candle", bar_id)
    result = advance_opportunity(previous, c)
    state = _text(result.get("state")); setup = _text(result.get("setup"))
    lifecycle = _text(result.get("lifecycle_state")) or ("OPPORTUNITY_WATCH" if state == "WATCHING" or setup in WATCH_SETUPS else state)
    phase = _text(result.get("opportunity_phase")) or lifecycle
    return {**result,"lifecycle_state":lifecycle,"opportunity_phase":phase,"age_bars":int(result.get("bars_waited",0) or 0),"wait_for":result.get("wait_for") or "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"}
