from __future__ import annotations
from typing import Any

TERMINAL={"INVALIDATED","EXPIRED","REPLACED"}

def _text(v:Any)->str:return str(v or "").upper().strip()

def _identity(direction:Any,setup:Any)->str:
    d,s=_text(direction),_text(setup)
    return f"{d}|{s}" if d in {"BUY","SELL"} and s not in {"","UNKNOWN","NONE","NO_SETUP"} else ""

def advance_lifecycle(previous:dict[str,Any]|None,current:dict[str,Any],*,bar_id:str,max_watch_bars:int=5)->dict[str,Any]:
    prev=dict(previous or {}); cur=dict(current or {})
    cid=_text(cur.get("opportunity_id")) or _identity(cur.get("direction"),cur.get("setup_family") or cur.get("setup"))
    pid=_text(prev.get("opportunity_id")); cd=_text(cur.get("direction")); pd=_text(prev.get("direction")); ps=_text(prev.get("lifecycle_state"))
    age=int(prev.get("age_bars") or 0)+(1 if prev else 0)
    base={**cur,"opportunity_id":cid or pid,"bar_id":str(bar_id),"age_bars":age}
    if bool(cur.get("invalidated")):
        return {**base,"lifecycle_state":"INVALIDATED","wait_for":"NEW_CAUSAL_OPPORTUNITY"}
    if prev and ps in TERMINAL:
        return {**base,"lifecycle_state":"REPLACED","previous_opportunity_id":pid,"age_bars":0,"wait_for":"NEW_CAUSAL_OPPORTUNITY"}
    if prev and pd in {"BUY","SELL"} and cd in {"BUY","SELL"} and pd!=cd:
        return {**base,"lifecycle_state":"REPLACED","previous_opportunity_id":pid,"age_bars":0,"wait_for":"CURRENT_OPPORTUNITY_PROOF"}
    if prev and pid and cid and pid!=cid:
        return {**base,"lifecycle_state":"REPLACED","previous_opportunity_id":pid,"age_bars":0,"wait_for":"CURRENT_OPPORTUNITY_PROOF"}
    if bool(cur.get("thesis_proven")) and cid:
        return {**base,"lifecycle_state":"SETUP_THESIS","thesis_bar_id":str(bar_id),"wait_for":"E7_CONFIRMATION"}
    if age>max_watch_bars:
        return {**base,"lifecycle_state":"EXPIRED","wait_for":"NEW_CAUSAL_OPPORTUNITY","expiration_reason":"WATCH_MAX_AGE_REACHED"}
    if bool(cur.get("causal_opportunity")) and cid:
        return {**base,"lifecycle_state":"OPPORTUNITY_WATCH","wait_for":"CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"}
    return {**base,"lifecycle_state":"INVALIDATED" if prev else "ABSENT","wait_for":"NEW_CAUSAL_OPPORTUNITY"}
