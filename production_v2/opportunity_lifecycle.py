from __future__ import annotations

from typing import Any

ACTIVE_STATES = {"WATCHING", "WAITING", "READY"}
TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH"}
VALID_DIRECTIONS = {"BUY", "SELL"}

def _text(value: Any) -> str:
    return str(value or "").upper().strip()

def _identity(direction: Any, setup: Any, event_id: Any = None) -> str:
    d, s = _text(direction), _text(setup)
    if d not in VALID_DIRECTIONS or s in {"", "UNKNOWN", "NONE", "NO_SETUP"}: return ""
    return f"{d}|{s}"

def _stable_identity(previous: dict[str, Any], direction: str, setup: str, event_id: Any = None) -> str:
    pid = _text(previous.get("opportunity_id")); pd = _text(previous.get("direction")); ps = _text(previous.get("setup"))
    if pid and pd == direction and direction in VALID_DIRECTIONS and (ps in WATCH_SETUPS or _text(previous.get("state")) in ACTIVE_STATES): return pid
    return _identity(direction, setup, event_id)

def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:
    p, c = dict(previous or {}), dict(current or {})
    d = _text(c.get("direction")); setup = _text(c.get("setup") or c.get("setup_family")); candle = _text(c.get("candle")); event = _text(c.get("event_id"))
    pid = _text(p.get("opportunity_id")); ps = _text(p.get("state")); pd = _text(p.get("direction")); previous_setup = _text(p.get("setup"))
    oid = _stable_identity(p, d, setup, event)
    age = int(p.get("bars_waited", 0) or 0) + (1 if p else 0)
    invalidated = bool(c.get("invalidated")); candidate = bool(c.get("candidate")); ready = bool(c.get("ready")); executed = bool(c.get("executed"))
    base = {**p, "last_evaluated_candle": candle, "trade_authorized": False}
    if executed:
        return {**base, "state": "EXECUTED", "continuity": "E9_AUTHORIZED_EXECUTION_RECORDED", "trade_authorized": False, "invalidation_reason": None}
    if invalidated:
        return {**base, "state": "INVALIDATED", "continuity": "OPPORTUNITY_INVALIDATED", "opportunity_id": pid or oid, "bars_waited": age if p else 0, "invalidation_reason": "CURRENT_CANDLE_INVALIDATED"}
    if p and ps in TERMINAL:
        return {**c, "state": "REPLACED", "continuity": "NEW_OPPORTUNITY_AFTER_TERMINAL", "previous_opportunity_id": pid, "opportunity_id": _identity(d, setup, event), "direction": d, "setup": setup, "bars_waited": 0, "origin_candle": candle, "last_evaluated_candle": candle, "trade_authorized": False, "invalidation_reason": None}
    if p and pd in VALID_DIRECTIONS and d in VALID_DIRECTIONS and d != pd:
        return {**c, "state": "INVALIDATED", "continuity": "DIRECTION_CHANGED", "previous_opportunity_id": pid, "opportunity_id": pid, "direction": pd, "setup": previous_setup or setup, "bars_waited": age, "origin_candle": p.get("origin_candle") or candle, "last_evaluated_candle": candle, "trade_authorized": False, "invalidation_reason": "DIRECTION_CHANGED"}
    pending_watch = previous_setup in WATCH_SETUPS or ps in {"WATCHING", "OPPORTUNITY_WATCH"}
    if p and pending_watch and candidate and d == pd and "upstream_evidence" in c and not c.get("upstream_evidence"):
        return {**base, "state": "INVALIDATED", "continuity": "OPPORTUNITY_INVALIDATED", "opportunity_id": pid or oid, "direction": pd or d, "setup": previous_setup or setup, "bars_waited": age, "origin_candle": p.get("origin_candle") or candle, "last_evaluated_candle": candle, "trade_authorized": False, "wait_for": "NEW_CAUSAL_OPPORTUNITY", "invalidation_reason": "UPSTREAM_CAUSAL_EVIDENCE_LOST"}
    if p and pending_watch and candidate and d == pd and oid and setup and setup != previous_setup:
        return {**base, "state": "READY" if ready else "WAITING", "continuity": "PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY", "opportunity_id": oid, "direction": d, "setup": setup, "bars_waited": age, "origin_candle": p.get("origin_candle") or candle, "wait_for": c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"], "invalidation_reason": None}
    if p and pid and oid and pid != oid:
        return {**c, "state": "REPLACED", "continuity": "OPPORTUNITY_ID_CHANGED", "previous_opportunity_id": pid, "opportunity_id": oid, "bars_waited": 0, "origin_candle": candle, "last_evaluated_candle": candle, "trade_authorized": False, "invalidation_reason": "OPPORTUNITY_ID_CHANGED"}
    if ready and candidate and oid:
        return {**base, "state": "READY", "continuity": "ADVANCING_EXISTING_OPPORTUNITY", "opportunity_id": oid, "direction": d, "setup": setup, "bars_waited": age if p else 0, "origin_candle": p.get("origin_candle") or candle, "invalidation_reason": None}
    if candidate and oid:
        continuity = "CONTINUING_UPSTREAM_WATCH" if pending_watch else ("CONTINUING_EXISTING_OPPORTUNITY" if p else "NEW_OPPORTUNITY_WATCH")
        return {**base, "state": "WATCHING" if ps == "WATCHING" else "WAITING", "continuity": continuity, "opportunity_id": oid, "direction": d, "setup": setup, "bars_waited": age if p else 0, "origin_candle": p.get("origin_candle") or candle, "wait_for": c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"], "invalidation_reason": None}
    if p:
        if age > 5: return {**base, "state": "EXPIRED", "continuity": "OPPORTUNITY_EXPIRED", "opportunity_id": pid, "bars_waited": age, "wait_for": "NEW_CAUSAL_OPPORTUNITY", "invalidation_reason": "WATCH_MAX_AGE_REACHED"}
        return {**base, "state": "WATCHING" if ps == "WATCHING" else "WAITING", "continuity": "PRESERVING_PENDING_OPPORTUNITY", "opportunity_id": pid, "direction": pd, "setup": previous_setup, "bars_waited": age, "wait_for": "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION", "invalidation_reason": None}
    return {"state": "IDLE", "continuity": "NO_ACTIVE_PENDING_OPPORTUNITY", "opportunity_id": None, "direction": "NEUTRAL", "setup": "UNKNOWN", "bars_waited": 0, "origin_candle": candle, "last_evaluated_candle": candle, "trade_authorized": False, "invalidation_reason": None}
