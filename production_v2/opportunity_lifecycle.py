from __future__ import annotations
from typing import Any

ACTIVE_STATES={"WATCHING","WAITING","READY"}
TERMINAL={"INVALIDATED","EXPIRED","REPLACED"}
WATCH_SETUPS={"OPPORTUNITY_WATCH","AUCTION_WATCH","REGIME_WATCH"}
VALID_DIRECTIONS={"BUY","SELL"}
MAX_WATCH_BARS=5

def _text(v:Any)->str:return str(v or "").upper().strip()
def _identity(direction:Any,setup:Any,event_id:Any=None)->str:
    d,s=_text(direction),_text(setup)
    return f"{d}|{s}" if d in VALID_DIRECTIONS and s not in {"","UNKNOWN","NONE","NO_SETUP"} else ""
def _stable_identity(previous:dict[str,Any],direction:str,setup:str,event_id:Any=None)->str:
    pid=_text(previous.get("opportunity_id")); pd=_text(previous.get("direction")); ps=_text(previous.get("setup")); state=_text(previous.get("state"))
    return pid if pid and pd==direction and direction in VALID_DIRECTIONS and (ps in WATCH_SETUPS or state in ACTIVE_STATES) else _identity(direction,setup,event_id)
def _active_previous(p:dict[str,Any])->bool:return bool(_text(p.get("opportunity_id")) and _text(p.get("direction")) in VALID_DIRECTIONS and _text(p.get("state")) in ACTIVE_STATES)

def advance_opportunity(previous:dict[str,Any]|None,current:dict[str,Any])->dict[str,Any]:
    """Canonical closed-candle opportunity lifecycle. It never grants execution authority."""
    p,c=dict(previous or {}),dict(current or {}); d=_text(c.get("direction")); setup=_text(c.get("setup") or c.get("setup_family")); candle=_text(c.get("candle")); oid=_stable_identity(p,d,setup,c.get("event_id")); pid=_text(p.get("opportunity_id")); ps=_text(p.get("state")); pd=_text(p.get("direction")); previous_setup=_text(p.get("setup")); active=_active_previous(p); age=int(p.get("bars_waited",0) or 0)+(1 if active else 0); invalidated=bool(c.get("invalidated")); candidate=bool(c.get("candidate")); ready=bool(c.get("ready")); base={**p,"last_evaluated_candle":candle,"trade_authorized":False}
    if c.get("execution_state")=="POSITION_OPEN": return {**base,"state":"EXECUTED","continuity":"POSITION_OPEN","execution_state":"POSITION_OPEN"}
    if invalidated:
        if not active:return {"state":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None}
        return {**base,"state":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"bars_waited":age,"invalidation_reason":c.get("invalidation_reason") or "CURRENT_CANDLE_INVALIDATED"}
    if active and pd in VALID_DIRECTIONS and d in VALID_DIRECTIONS and d!=pd:return {**base,"state":"INVALIDATED","continuity":"DIRECTION_CHANGED","opportunity_id":pid,"direction":pd,"setup":previous_setup or setup,"bars_waited":age,"invalidation_reason":"DIRECTION_CHANGED"}
    pending=active and (previous_setup in WATCH_SETUPS or ps in {"WATCHING","WAITING"})
    if pending and bool(c.get("upstream_evidence_lost") or c.get("causal_evidence_lost")):return {**base,"state":"INVALIDATED","continuity":"UPSTREAM_CAUSAL_EVIDENCE_LOST","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"UPSTREAM_CAUSAL_EVIDENCE_LOST"}
    if pending and candidate and d==pd and oid and setup not in WATCH_SETUPS and setup not in {"","UNKNOWN","NONE","NO_SETUP"}:return {**base,"state":"READY" if ready else "WAITING","continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],"invalidation_reason":None}
    if active and pid and oid and pid!=oid:return {**c,"state":"REPLACED","continuity":"OPPORTUNITY_ID_CHANGED","previous_opportunity_id":pid,"opportunity_id":oid,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"OPPORTUNITY_ID_CHANGED"}
    if active and ready and candidate and oid:return {**base,"state":"READY","continuity":"ADVANCING_EXISTING_OPPORTUNITY","opportunity_id":pid or oid,"direction":d or pd,"setup":setup or previous_setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"invalidation_reason":None}
    if candidate and oid:
        if active and age>MAX_WATCH_BARS:return {**base,"state":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd or d,"setup":previous_setup or setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        return {**base,"state":"WATCHING","continuity":"CONTINUING_UPSTREAM_WATCH" if pending else ("CONTINUING_EXISTING_OPPORTUNITY" if active else "NEW_OPPORTUNITY_WATCH"),"opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if active else 0,"origin_candle":p.get("origin_candle") if active else candle,"wait_for":c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],"invalidation_reason":None}
    if active:
        if age>MAX_WATCH_BARS:return {**base,"state":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        return {**base,"state":ps if ps in ACTIVE_STATES else "WAITING","continuity":"PRESERVING_PENDING_OPPORTUNITY","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION","invalidation_reason":None}
    return {"state":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None}
