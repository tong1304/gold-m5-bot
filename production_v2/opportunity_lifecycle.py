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
    if d not in VALID_DIRECTIONS or s in {"","UNKNOWN","NONE","NO_SETUP"}: return ""
    return f"{d}|{s}"


def _stable_identity(previous:dict[str,Any],direction:str,setup:str,event_id:Any=None)->str:
    pid=_text(previous.get("opportunity_id")); pd=_text(previous.get("direction")); ps=_text(previous.get("setup")); state=_text(previous.get("state"))
    if pid and pd==direction and direction in VALID_DIRECTIONS and (ps in WATCH_SETUPS or state in {"WATCHING","WAITING","READY"}):
        return pid
    return _identity(direction,setup,event_id)


def _active_previous(p:dict[str,Any])->bool:
    oid=_text(p.get("opportunity_id")); state=_text(p.get("state")); direction=_text(p.get("direction"))
    return bool(oid and direction in VALID_DIRECTIONS and state in ACTIVE_STATES)


def advance_opportunity(previous:dict[str,Any]|None,current:dict[str,Any])->dict[str,Any]:
    """Advance an opportunity across closed candles.

    Absence of a fresh E6 candidate is not itself invalidation. A pending
    opportunity remains alive until explicit causal evidence loss, direction
    reversal, or the bounded watch-age expiry is proven. Lifecycle never grants
    execution authority.
    """
    p=dict(previous or {}); c=dict(current or {})
    d=_text(c.get("direction")); setup=_text(c.get("setup") or c.get("setup_family")); candle=_text(c.get("candle")); event=_text(c.get("event_id"))
    oid=_stable_identity(p,d,setup,event); pid=_text(p.get("opportunity_id")); ps=_text(p.get("state")); pd=_text(p.get("direction")); previous_setup=_text(p.get("setup"))
    active_prev=_active_previous(p)
    age=int(p.get("bars_waited",0) or 0)+(1 if active_prev else 0)
    invalidated=bool(c.get("invalidated")); candidate=bool(c.get("candidate")); ready=bool(c.get("ready"))
    if bool(c.get("executed")):
        return {**p,"state":"EXECUTE","continuity":"E9_AUTHORIZED_EXECUTION","trade_authorized":False,"execution_handoff":True,"last_evaluated_candle":candle,"invalidation_reason":None}
    base={**p,"last_evaluated_candle":candle,"trade_authorized":False}
    if invalidated:
        if not active_prev:
            return {"state":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None}
        return {**base,"state":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"bars_waited":age,"invalidation_reason":c.get("invalidation_reason") or "CURRENT_CANDLE_INVALIDATED"}
    if active_prev and pd in VALID_DIRECTIONS and d in VALID_DIRECTIONS and d!=pd:
        return {**c,"state":"INVALIDATED","continuity":"DIRECTION_CHANGED","previous_opportunity_id":pid,"opportunity_id":pid,"direction":pd,"setup":previous_setup or setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"DIRECTION_CHANGED"}
    pending_watch=active_prev and (previous_setup in WATCH_SETUPS or ps in {"WATCHING","WAITING"})
    explicit_evidence_loss=bool(c.get("upstream_evidence_lost") or c.get("causal_evidence_lost"))
    if pending_watch and explicit_evidence_loss:
        return {**base,"state":"INVALIDATED","continuity":"OPPORTUNITY_INVALIDATED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"UPSTREAM_CAUSAL_EVIDENCE_LOST"}
    if pending_watch and candidate and d==pd and oid and setup not in WATCH_SETUPS and setup not in {"","UNKNOWN","NONE","NO_SETUP"}:
        return {**base,"state":"READY" if ready else "WAITING","continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY","opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"wait_for":c.get("wait_for") or ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],"invalidation_reason":None}
    if active_prev and pid and oid and pid!=oid:
        return {**c,"state":"REPLACED","continuity":"OPPORTUNITY_ID_CHANGED","previous_opportunity_id":pid,"opportunity_id":oid,"bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":"OPPORTUNITY_ID_CHANGED"}
    if active_prev and ready and candidate and oid:
        return {**base,"state":"READY","continuity":"ADVANCING_EXISTING_OPPORTUNITY","opportunity_id":pid or oid,"direction":d or pd,"setup":setup or previous_setup,"bars_waited":age,"origin_candle":p.get("origin_candle") or candle,"invalidation_reason":None}
    if candidate and oid:
        if active_prev and age>MAX_WATCH_BARS:
            return {**base,"state":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd or d,"setup":previous_setup or setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        continuity="CONTINUING_UPSTREAM_WATCH" if pending_watch else ("CONTINUING_EXISTING_OPPORTUNITY" if active_prev else "NEW_OPPORTUNITY_WATCH")
        return {**base,"state":"WATCHING","continuity":continuity,"opportunity_id":oid,"direction":d,"setup":setup,"bars_waited":age if active_prev else 0,"origin_candle":p.get("origin_candle") if active_prev else candle,"wait_for":c.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],"invalidation_reason":None}
    if active_prev:
        if age>MAX_WATCH_BARS:
            return {**base,"state":"EXPIRED","continuity":"OPPORTUNITY_EXPIRED","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"WATCH_MAX_AGE_REACHED"}
        return {**base,"state":ps if ps in ACTIVE_STATES else "WAITING","continuity":"PRESERVING_PENDING_OPPORTUNITY","opportunity_id":pid,"direction":pd,"setup":previous_setup,"bars_waited":age,"wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION","invalidation_reason":None}
    return {"state":"IDLE","continuity":"NO_ACTIVE_PENDING_OPPORTUNITY","opportunity_id":None,"direction":"NEUTRAL","setup":"UNKNOWN","bars_waited":0,"origin_candle":candle,"last_evaluated_candle":candle,"trade_authorized":False,"invalidation_reason":None}


def advance_lifecycle(previous:dict[str,Any]|None,current:dict[str,Any],*,bar_id:str,max_watch_bars:int=MAX_WATCH_BARS)->dict[str,Any]:
    p=dict(previous or {}); c=dict(current or {}); d=_text(c.get("direction")); setup=_text(c.get("setup_family") or c.get("setup")); pid=_text(p.get("opportunity_id")); oid=_text(c.get("opportunity_id")) or _stable_identity(p,d,setup,c.get("event_id")); age=int(p.get("age_bars",0) or 0)+(1 if p else 0)
    if c.get("invalidated"):return {**c,"opportunity_id":oid or pid,"lifecycle_state":"INVALIDATED","age_bars":age if p else 0,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
    if p and _text(p.get("direction")) in VALID_DIRECTIONS and d in VALID_DIRECTIONS and _text(p.get("direction"))!=d:return {**c,"lifecycle_state":"INVALIDATED","previous_opportunity_id":pid,"opportunity_id":pid or oid,"age_bars":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY","invalidation_reason":"DIRECTION_CHANGED"}
    if c.get("thesis_proven") and oid:return {**c,"lifecycle_state":"SETUP_THESIS","opportunity_id":oid,"age_bars":age,"thesis_bar_id":str(bar_id),"wait_for":"E7_CONFIRMATION"}
    if p and pid and oid and pid!=oid:return {**c,"lifecycle_state":"REPLACED","previous_opportunity_id":pid,"opportunity_id":oid,"age_bars":0,"wait_for":"CURRENT_OPPORTUNITY_PROOF"}
    if age>max_watch_bars:return {**c,"lifecycle_state":"EXPIRED","opportunity_id":oid or pid,"age_bars":age,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
    if c.get("causal_opportunity") or (p and _text(p.get("lifecycle_state")) in {"OPPORTUNITY_WATCH","SETUP_THESIS"}) or p:return {**c,"lifecycle_state":"OPPORTUNITY_WATCH","opportunity_id":oid or pid,"age_bars":age,"wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"}
    return {**c,"lifecycle_state":"ABSENT","opportunity_id":oid or pid,"age_bars":0,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
