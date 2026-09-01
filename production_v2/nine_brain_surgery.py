from __future__ import annotations

"""Production-v2 nine-brain professional governance hardening.

This layer does not manufacture trading evidence and does not loosen any gate.
It separates present evidence from future invalidation rules and exposes an
explicit lifecycle/gate/next-event contract for every brain.
"""

from typing import Any
ENGINE_ORDER=("E1","E2","E3","E4","E5","E6","E7","E8","E9")
OWNERS={"E1":"MARKET_STATE","E2":"OPPORTUNITY_REGIME","E3":"MARKET_STRUCTURE","E4":"LIQUIDITY_AUCTION","E5":"LOCATION_VALUE","E6":"SETUP_FORMATION","E7":"CONFIRMATION","E8":"TRADE_ECONOMICS_RISK","E9":"FINAL_MARKET_CONTROL"}

def _text(value:Any)->str:return str(value or "").upper().strip()
def _list(value:Any)->list[Any]:
    if isinstance(value,(list,tuple,set)):return list(value)
    if value in (None,""):return []
    return [value]
def _active_codes(output):
    values=[]
    for key in ("reason_codes","reasons","blockers","risk_blockers","economic_blockers","conflicts"):values.extend(_list(output.get(key)))
    seen=set();result=[]
    for value in values:
        token=_text(value)
        if token and token not in seen:seen.add(token);result.append(token)
    return result
def _future_invalidations(output):
    seen=set();result=[]
    for value in _list(output.get("invalidations")):
        token=_text(value)
        if token and token not in seen:seen.add(token);result.append(token)
    return result
def _explicit_active_invalidations(output):
    value=output.get("active_invalidations")
    if isinstance(value,dict):return [_text(k) for k,v in value.items() if v]
    return [_text(v) for v in _list(value) if _text(v)]
def _next_event(engine_id,output):
    missing=_list(output.get("missing_evidence"))
    if missing:return _text(missing[0])
    for key in ("next_required_event","opportunity_next_event","confirmation_required","required_confirmation","required_evidence"):
        value=output.get(key)
        if isinstance(value,(list,tuple,set)) and value:return _text(list(value)[0])
        if value not in (None,""):return _text(value)
    return {"E1":"NEXT_CLOSED_M5_CANDLE_REVALIDATES_MARKET_STATE","E2":"DIRECTIONAL_CONVERGENCE_AND_AUCTION_ACCEPTANCE","E3":"NEXT_CAUSAL_STRUCTURE_EVENT_OR_PROTECTED_LEVEL_TEST","E4":"CLOSED_CANDLE_FOLLOW_THROUGH_OR_REJECTION_RECLAIM","E5":"ADVANTAGEOUS_LOCATION_WITH_SUFFICIENT_OPPOSING_SPACE","E6":"SETUP_SPECIFIC_FORMATION_EVIDENCE","E7":"VALID_CLOSED_CANDLE_CONFIRMATION","E8":"VALID_TRADE_GEOMETRY_AND_RISK_ACCEPTANCE","E9":"ALL_REQUIRED_GATES_PROVEN_WITH_NO_VETO"}[engine_id]
def _lifecycle(engine_id,output):
    if _explicit_active_invalidations(output):return "INVALIDATED"
    keys={"E1":("analysis_status",),"E2":("opportunity_maturity","opportunity_state"),"E3":("lifecycle","structure_state"),"E4":("auction_state","state"),"E5":("repricing_state","location_state"),"E6":("setup_state","state"),"E7":("confirmation_state","proof_state"),"E8":("risk_state","economic_state"),"E9":("decision",)}[engine_id]
    for key in keys:
        value=_text(output.get(key))
        if value:return value
    return "UNRESOLVED"
def _gate_state(engine_id,output,active_invalidations):
    if active_invalidations:return "BLOCKED"
    active=set(_active_codes(output));lifecycle=_lifecycle(engine_id,output);state=_text(output.get("state"))
    if any("DATA" in code and "FAIL" in code for code in active):return "BLOCKED"
    if engine_id=="E1":return "READY" if lifecycle in {"COMPLETE","VALIDATED","STABLE"} and state not in {"UNCLEAR","UNRESOLVED"} else "PENDING"
    if engine_id=="E2":return "READY" if _text(output.get("opportunity_maturity")) in {"CONFIRMED","ACTIONABLE"} else "PENDING"
    if engine_id=="E3":return "READY" if lifecycle in {"ESTABLISHED","CONFIRMED","VALIDATED"} and state not in {"MIXED","UNRESOLVED","TRANSITION"} else "PENDING"
    if engine_id=="E4":return "READY" if lifecycle in {"CONFIRMED","TERMINALLY_CONFIRMED","RECLAIMED","ACCEPTED","REJECTED"} else "PENDING"
    if engine_id=="E5":return "BLOCKED" if active & {"INVALID_TRADE_GEOMETRY","NO_USABLE_STRUCTURAL_TARGET","EFFECTIVE_SPACE_BELOW_MINIMUM"} else ("READY" if lifecycle in {"ADVANTAGEOUS","FAVORABLE","ACCEPTED","REPRICING_CONFIRMED"} else "PENDING")
    if engine_id=="E6":return "READY" if lifecycle in {"MATURE","TRADE_READY","VALIDATED","CONFIRMED"} else "PENDING"
    if engine_id=="E7":return "READY" if lifecycle in {"PROVEN","CONFIRMED","VALIDATED","TRADE_READY"} else "PENDING"
    if engine_id=="E8":return "BLOCKED" if active & {"INVALID_TRADE_GEOMETRY","INVALID_RISK_GEOMETRY","REAL_RR_BELOW_MINIMUM","STOP_QUALITY_TOO_LOW","TARGET_REALISM_TOO_LOW","PROBABILITY_EDGE_NOT_TRUSTWORTHY","NO_USABLE_STRUCTURAL_TARGET"} else ("READY" if _text(output.get("risk_state")) in {"READY","RISK_READY","TRADE_READY","VALIDATED","PASS","PASSED"} or _text(output.get("economic_state")) in {"ECONOMICALLY_ACCEPTABLE","TRADE_READY","VALIDATED"} else "PENDING")
    if engine_id=="E9":return "READY" if _text(output.get("decision")) in {"BUY","SELL"} and not active else "BLOCKED"
    return "PENDING"
def harden_engine(engine_id,raw_output):
    if engine_id not in OWNERS:raise ValueError(f"unknown engine_id: {engine_id}")
    output=dict(raw_output or {});active=_active_codes(output);future=_future_invalidations(output);active_invalidations=_explicit_active_invalidations(output);gate_state=_gate_state(engine_id,output,active_invalidations);lifecycle=_lifecycle(engine_id,output)
    output["future_invalidation_conditions"]=future;output["active_invalidations"]=active_invalidations;output["active_reason_codes"]=active;output["surgery_boundary"]="PRESENT_EVIDENCE_SEPARATED_FROM_FUTURE_INVALIDATION_RULES"
    output["professional_contract"]={"engine":engine_id,"owner":OWNERS[engine_id],"decision_authority":"E9_ONLY","can_create_thesis":engine_id in {"E2","E6"},"can_authorize_entry":False,"closed_candle_only":True,"lifecycle":lifecycle,"gate_state":gate_state,"blockers":list(active_invalidations)+[x for x in active if x not in active_invalidations],"next_required_event":_next_event(engine_id,output),"active_invalidated":bool(active_invalidations)}
    if engine_id=="E1" and _text(output.get("analysis_status"))=="COMPLETE":output["data_integrity_current"]="VALIDATED";output["data_integrity_future_failures"]=[x for x in future if "DATA" in x]
    elif engine_id=="E3" and _text(output.get("lifecycle"))=="TRANSITION":output["transition_is_not_invalidation"]=True
    elif engine_id=="E4":
        state=_text(output.get("auction_state"));response=_text(output.get("response_actor") or "UNCLEAR");proven=state in {"CONFIRMED","TERMINALLY_CONFIRMED","RECLAIMED","ACCEPTED","REJECTED"};output["auction_confirmation_proven"]=proven;output["raw_response_actor"]=response;eligible=bool(proven and response in {"BUYERS","SELLERS","BUYER","SELLER"});output["control_actor_eligible"]=eligible;output["response_actor_for_control"]=response if eligible else "UNCLEAR";output["response_actor"] = response if eligible else "UNCLEAR";output["auction_confirmation_pending"]=state=="PENDING"
    elif engine_id=="E2":
        maturity=_text(output.get("opportunity_maturity") or output.get("opportunity_state"));output["direction_for_market_control"]=_text(output.get("direction") or output.get("opportunity_direction")) if maturity in {"CONFIRMED","ACTIONABLE"} else "NEUTRAL";output["directional_claim_authority"]="E2_OPPORTUNITY_ONLY"
    elif engine_id=="E5":
        repricing=_text(output.get("repricing_direction"));output["direction_for_market_control"]=repricing if repricing in {"BUY","SELL"} else "NEUTRAL";output["directional_claim_authority"]="E5_REPRICING_ONLY"
    elif engine_id=="E6":output["setup_authorization"]="NONE"
    elif engine_id=="E7":output["confirmation_authorization"]="PROOF_ONLY"
    elif engine_id=="E8":output["execution_authorization"]="NONE"
    elif engine_id=="E9":output["master_authority"]="SOLE_FINAL_AUTHORITY";output["upstream_evidence_only"]=True
    return output
def harden_all(outputs):return {engine_id:harden_engine(engine_id,outputs.get(engine_id,{})) for engine_id in ENGINE_ORDER if engine_id in outputs}
