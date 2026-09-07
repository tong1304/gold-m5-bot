from __future__ import annotations
from functools import wraps
from typing import Any
ACTIVE={"WATCHING","WAITING","READY"}
def install(module: Any)->None:
    if getattr(module,"_PROFESSIONAL_LIFECYCLE_CONTRACT_V2",False): return
    original=module.advance_opportunity
    original_directions=module.advance_opportunity_directions
    @wraps(original)
    def advance_opportunity(previous,current):
        previous=dict(previous or {}); current=dict(current or {}); result=original(previous,current)
        for key in ("opportunity_phase","opportunity_speed","confirmation_window","wait_for","chase_prohibited","thesis_status","upstream_evidence"):
            if key in current and key not in result: result[key]=current[key]
        ps=str(previous.get("setup") or "").upper(); cs=str(current.get("setup") or current.get("setup_family") or "").upper(); ts=str(current.get("thesis_status") or "").upper()
        if previous.get("state") in ACTIVE and ps in {"OPPORTUNITY_WATCH","AUCTION_WATCH","REGIME_WATCH"} and cs not in {"","UNKNOWN","NONE","NO_SETUP","OPPORTUNITY_WATCH","AUCTION_WATCH","REGIME_WATCH"} and ts in {"FORMING","VALIDATING","THESIS_FORMED","PROVEN"} and not current.get("ready"):
            result={**result,"state":"WAITING","lifecycle_state":"TRIGGER_PENDING","opportunity_phase":"TRIGGER_PENDING","setup":cs,"direction":current.get("direction"),"candidate":True,"trade_authorized":False,"ready":False,"continuity":"PROMOTED_PENDING_OPPORTUNITY_TO_SETUP"}
        return result
    @wraps(original_directions)
    def advance_opportunity_directions(previous,current_by_direction,*,leader="NEUTRAL",competition="UNCONTESTED"):
        result=original_directions(previous,current_by_direction,leader=leader,competition=competition); book=result.get("opportunities",{})
        for direction in ("BUY","SELL"):
            item=book.get(direction); current=current_by_direction.get(direction) or {}
            if isinstance(item,dict) and item.get("state")=="REPLACED" and current.get("candidate"):
                item=dict(item); item.update(state="WATCHING",lifecycle_state="OPPORTUNITY_WATCH",opportunity_phase="OPPORTUNITY_WATCH",continuity="NEW_CAUSAL_EVENT_NEW_ACTIVE_WATCH",trade_authorized=False); book[direction]=item
        if leader in {"BUY","SELL"} and isinstance(book.get(leader),dict): result["leader"]=leader
        result["active_directions"]=[d for d in ("BUY","SELL") if isinstance(book.get(d),dict) and book[d].get("state") in ACTIVE]
        return result
    module.advance_opportunity=advance_opportunity; module.advance_opportunity_directions=advance_opportunity_directions; module._PROFESSIONAL_LIFECYCLE_CONTRACT_V2=True
