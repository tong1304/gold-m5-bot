from __future__ import annotations
from typing import Any

ACTIVE_STATES={"WATCHING","WAITING","READY"}
TERMINAL={"INVALIDATED","EXPIRED","REPLACED"}

def _text(v:Any)->str:return str(v or "").upper().strip()
def _identity(direction:Any,setup:Any,event_id:Any=None)->str:
    d,s,e=_text(direction),_text(setup),_text(event_id)
    if d not in {"BUY","SELL"} or s in {"","UNKNOWN","NONE","NO_SETUP"}: return ""
    return f"{d}|{s}|{e}" if e else f"{d}|{s}"

def advance_opportunity(previous:dict[str,Any]|None,current:dict[str,Any])->dict[str,Any]:
    """Advance E6 opportunity state across closed candles; never authorize execution."""
    p=dict(previous or {}); c=dict(current or {})
    d=_text(c.get("direction")); setup=_text(c.get("setup") or c.get("setup_family")); event=_text(c.get("event_id")); candle=_text(c.get("candle"))
    oid=_identity(d,setup,event); pid=_text(p.get("opportunity_id")); ps=_text(p.get("state")); pd=_text(p.get("direction")); psetup=_text(p.get("setup"))
    age=int(p.get("bars_waited",0) or 0)+(1 if p else 0)
    invalidated=bool(c.get("invalidated")); candidate=bool(c.get("candidate")); ready=bool(c.get("ready")); executed=bool(c.get("executed"))
    base={**p,"last_evaluated_candle":candle,"trade_authorized":False}
    if executed:return {**base,"state":"EXECUTE","continuity":"E9_AUTHORIZED_EXECUTION","trade_authorized":True,"invalidation_reason":None}
    if invalidated:return {**base,"state":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid or oid,"bars_waited":age if p else 0,"invalidation_reason":"CURRENT_CANDLE_INVALIDATED"}
    if p and ps in TERMINAL:return {**c,"state":"REPLACED","continuity":"NEW_OPPORTUNITY_AFTER_TERMINAL","previous_opportunity_id":pid,"opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None}
    if p and pd in {"BUY","SELL"} and d in {"BUY","SELL"} and d!=pd:return {**c,"state":"REPLACED","continuity":"DIRECTION_CHANGED","previous_opportunity_id":pid,"opportunity_id":oid,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"DIRECTION_CHANGED"}
    pending_watch=pset.startswith(("OPPORTUNITY_WATCH","AUCTION_WATCH","REGIME_WATCH"))
    if p and pending_watch and candidate and d==pd and oid and oid!=pid:
        return {**base,"state":"READY" if ready else "WAITING","continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],"invalidation_reason":None}
    if p and pid and oid and pid!=oid:return {**c,"state":"REPLACED","continuity":"OPPORTUNITY_ID_CHANGED","previous_opportunity_id":pid,"opportunity_id":oid,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"OPPORTUNITY_ID_CHANGED"}
    if ready and candidate and oid:return {**base,"state":"READY","continuity":"ADVANCING_TO_EXECUTION_GATE","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if p else 0,"origin_candle":p.get("origin_candle") or candle,"invalidation_reason":None}
    if candidate and oid:
        if p and age>5:return {**base,"state":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        return {**base,"state":"WATCHING" if ps=="WATCHING" else "WAITING","continuity":"CONTINUING_UPSTREAM_WATCH" if p else "NEW_DEVELOPING_OPPORTUNITY","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if p else 0,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],"invalidation_reason":None}
    if p:return {**base,"state":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"THESIS_NOT_PRESERVED"}
    return {"state":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None}

def advance_lifecycle(previous:dict[str,Any]|None,current:dict[str,Any],*,bar_id:str,max_watch_bars:int=5)->dict[str,Any]:
    """Explicit E6 lifecycle API used by tests and future callers."""
    p=dict(previous or {}); c=dict(current or {}); d=_text(c.get("direction")); setup=_text(c.get("setup_family") or c.get("setup")); oid=_text(c.get("opportunity_id")) or _identity(d,setup,c.get("event_id")); pid=_text(p.get("opportunity_id")); age=int(p.get("age_bars",0) or 0)+(1 if p else 0)
    if c.get("invalidated"):return {**c,"opportunity_id":oid or pid,"lifecycle_state":"INVALIDATED","age_bars":age if p else 0,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
    if p and pid and oid and pid!=oid:return {**c,"lifecycle_state":"REPLACED","previous_opportunity_id":pid,"opportunity_id":oid,"age_bars":0,"wait_for":"CURRENT_OPPORTUNITY_PROOF"}
    if p and _text(p.get("direction")) in {"BUY","SELL"} and d in {"BUY","SELL"} and _text(p.get("direction"))!=d:return {**c,"lifecycle_state":"REPLACED","previous_opportunity_id":pid,"opportunity_id":oid,"age_bars":0,"wait_for":"CURRENT_OPPORTUNITY_PROOF"}
    if c.get("thesis_proven") and oid:return {**c,"lifecycle_state":"SETUP_THESIS","opportunity_id":oid,"age_bars":age,"thesis_bar_id":str(bar_id),"wait_for":"E7_CONFIRMATION"}
    if age>max_watch_bars:return {**c,"lifecycle_state":"EXPIRED","opportunity_id":oid or pid,"age_bars":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
    if c.get("causal_opportunity") and oid:return {**c,"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":oid,"age_bars":age,"wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"}
    return {**c,"lifecycle_state":"INVALIDATED" if p else "ABSENT","opportunity_id":oid or pid,"age_bars":age if p else 0,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
