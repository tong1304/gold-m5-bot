from __future__ import annotations
from typing import Any
from .contracts import EngineResult
NAME="Master Decision Brain"
QUESTION="Should this trade be taken after reconciling all relevant evidence?"
ARCHITECTURE="E9_MASTER_DECISION_MARKET_CONTROL_V54"
VERSION="54.0"
DIRECTIONS={"BUY","SELL"}
HARD_CONFLICT_CODES={"THESIS_INVALIDATED","MARKET_STATE_CONFLICT","STRUCTURE_THESIS_CONFLICT","OPPOSING_LIQUIDITY_THESIS","EXTERNAL_INTERNAL_STRUCTURE_CONFLICT","E6_THESIS_INVALIDATED","E7_CONFIRMATION_INVALIDATED","E8_RISK_INVALIDATED","STRUCTURE_INVALIDATED","BULLISH_STRUCTURE_INVALIDATED","BEARISH_STRUCTURE_INVALIDATED","E3_STRUCTURE_INVALIDATED","E3_THESIS_INVALIDATED"}
ECONOMIC_BLOCKERS={"INVALID_TRADE_GEOMETRY","INVALID_RISK_GEOMETRY","RISK_GEOMETRY_INVALID","REAL_RR_BELOW_MINIMUM","EXECUTION_COST_TOO_HIGH","STRUCTURAL_SURVIVAL_NOT_PROVEN","EFFECTIVE_SPACE_UNRELIABLE","EFFECTIVE_SPACE_BELOW_MINIMUM","STRESSED_PROBABILITY_BELOW_MINIMUM","TARGET_REALISM_TOO_LOW","STOP_QUALITY_TOO_LOW","PROBABILITY_EDGE_NOT_TRUSTWORTHY","NO_USABLE_STRUCTURAL_TARGET","RISK_QUALITY_BELOW_DECISION_THRESHOLD"}
BLOCKER_PRIORITY=("THESIS_INVALIDATED","E6_THESIS_INVALIDATED","E7_CONFIRMATION_INVALIDATED","E8_RISK_INVALIDATED","E3_STRUCTURE_INVALIDATED","STRUCTURE_INVALIDATED","BULLISH_STRUCTURE_INVALIDATED","BEARISH_STRUCTURE_INVALIDATED","E3_THESIS_INVALIDATED","MARKET_STATE_CONFLICT","STRUCTURE_THESIS_CONFLICT","OPPOSING_LIQUIDITY_THESIS","EXTERNAL_INTERNAL_STRUCTURE_CONFLICT","INVALID_TRADE_GEOMETRY","INVALID_RISK_GEOMETRY","RISK_GEOMETRY_INVALID","REAL_RR_BELOW_MINIMUM","EXECUTION_COST_TOO_HIGH","STRUCTURAL_SURVIVAL_NOT_PROVEN","EFFECTIVE_SPACE_UNRELIABLE","EFFECTIVE_SPACE_BELOW_MINIMUM","STRESSED_PROBABILITY_BELOW_MINIMUM","TARGET_REALISM_TOO_LOW","STOP_QUALITY_TOO_LOW","PROBABILITY_EDGE_NOT_TRUSTWORTHY","NO_USABLE_STRUCTURAL_TARGET","ENTRY_CONFIRMATION_NOT_PROVEN","SETUP_NOT_MATURE","RISK_NOT_READY","RISK_QUALITY_BELOW_DECISION_THRESHOLD","DIRECTION_UNRESOLVED")
CONFIRMATION_PROVEN={"PROVEN","CONFIRMED","VALIDATED","TRADE_READY"}
MATURITY_READY={"MATURE","TRADE_READY","VALIDATED","CONFIRMED"}
RISK_READY_STATES={"READY","RISK_READY","ECONOMICALLY_ACCEPTABLE","TRADE_READY","VALIDATED","PASS","PASSED","COMPLETE"}
def _out(e): return dict(e.output or {}) if e else {}
def _text(v): return str(v or "").upper().strip()
def _dedupe(v): return list(dict.fromkeys(str(x) for x in v if x))
def _codes(o):
    a=[]
    for k in ("reason_codes","reasons","counter_evidence","blockers","risk_blockers","economic_blockers","conflicts","invalidations"):
        v=o.get(k)
        if isinstance(v,str): a.append(v)
        elif isinstance(v,(list,tuple,set)): a.extend(v)
    return _dedupe([_text(x) for x in a if x])
def _engine_codes(e): return _dedupe(_codes(_out(e))+[_text(x) for x in (e.reason_codes or ()) if x]) if e else []
def _direction(*vals):
    for v in vals:
        x=_text(v)
        if x in DIRECTIONS:return x
        if x.startswith(("BUY ","BUY_","BUY:")):return "BUY"
        if x.startswith(("SELL ","SELL_","SELL:")):return "SELL"
        if x in {"UP","BULLISH"} or any(k in x for k in ("LONG","BUYERS","TREND_UP")):return "BUY"
        if x in {"DOWN","BEARISH"} or any(k in x for k in ("SHORT","SELLERS","TREND_DOWN")):return "SELL"
    return "NEUTRAL"
def _clean_setup(v):
    t=str(v or "").strip();return "" if _text(t) in {"","UNKNOWN","NONE","NO_SETUP","NO SETUP","UNRESOLVED"} else t
def _e6_identity(e):
    f=str(e.get("finding") or "").strip();d=_direction(e.get("direction"),e.get("direction_thesis"),e.get("thesis_direction"),e.get("selected_direction"),f);s=""
    for k in ("setup","setup_family","candidate_setup","candidate_setup_thesis","setup_type","thesis_setup","selected_hypothesis"):
        s=_clean_setup(e.get(k))
        if s:break
    if not s and f:
        h=f.split(" is validating",1)[0].strip()
        if d in DIRECTIONS and _text(h).startswith(d+" "):h=h[len(d):].strip()
        s=_clean_setup(h)
    return d,s or "UNKNOWN",str(e.get("thesis") or e.get("candidate_setup_thesis") or e.get("selected_hypothesis") or f or "UNRESOLVED").strip() or "UNRESOLVED"
def _state(o,keys,default="UNRESOLVED"):
    for k in keys:
        if o.get(k) not in (None,""):return _text(o[k])
    return default
def _walk(v):
    if isinstance(v,dict):
        yield v
        for x in v.values():yield from _walk(x)
    elif isinstance(v,(list,tuple,set)):
        for x in v:yield from _walk(x)
def _e8(e):
    m={};p={}
    for c in _walk(_out(e)):
        if isinstance(c.get("trade_plan"),dict):p.update(c["trade_plan"])
        for k in ("risk_gate","risk_state","economic_state","decision_state","plan_status","direction","risk_quality","verified","trade_plan_verified"):
            if k in c:m[k]=c[k]
    return m,p
def _trigger(e):
    if any(e.get(k) is True for k in ("trigger_observed","valid_trigger","closed_candle_trigger")):return True
    return _state(e,("trigger_state","trigger","entry_trigger")) in {"VALID","VALIDATED","CONFIRMED","PROVEN","TRADE_READY"} or bool(set(_codes(e))&{"VALID_CLOSED_CANDLE_TRIGGER","TRIGGER_CONFIRMED","CONFIRMATION_PROVEN"})
def _confirmation(e):
    c=set(_codes(e))
    if c&{"E7_CONFIRMATION_INVALIDATED","CONFIRMATION_INVALIDATED"}:return "INVALIDATED"
    if c&{"CONFIRMATION_PROVEN","CAUSAL_FOLLOW_THROUGH_PROVEN"}:return "PROVEN"
    if c&{"PROOF_GATES_INCOMPLETE","VALID_CLOSED_CANDLE_TRIGGER_MISSING","TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION","LIQUIDITY_RECLAIM_LEVEL_REQUIRED"}:return "PENDING"
    return _state(e,("confirmation_state","confirmation","proof_state","trigger_state"))
def _plan_valid(p,d):
    if d not in DIRECTIONS or not isinstance(p,dict):return False
    try:a=float(p["entry"]);s=float(p["stop_loss"]);t=float(p.get("take_profit_2",p.get("take_profit",p.get("tp2"))))
    except (KeyError,TypeError,ValueError):return False
    if not all(x==x for x in (a,s,t)):return False
    if d=="BUY" and not s<a<t:return False
    if d=="SELL" and not t<a<s:return False
    rr=p.get("rr_tp2",p.get("rr"))
    if rr not in (None,""):
        try:
            if float(rr)<1.50:return False
        except (TypeError,ValueError):return False
    return True
def _hard(up):
    found=[]
    for eid in ("E1","E2","E3","E4","E5","E6","E7","E8"):
        e=up.get(eid);o=_out(e);found.extend(c for c in _engine_codes(e) if c in HARD_CONFLICT_CODES)
        for k in ("state","finding","lifecycle","invalidation","structure_state","thesis_state"):
            v=_text(o.get(k))
            if v in HARD_CONFLICT_CODES or v.endswith("_INVALIDATED") or "THESIS_INVALIDATED" in v:
                if v:found.append(v)
    return _dedupe(found)
def _economic(e):
    found=[]
    for c in _walk(_out(e)):found.extend(x for x in _codes(c) if x in ECONOMIC_BLOCKERS)
    return _dedupe(found)
def _market_control(up,direction,setup):
    e1,e3,e4,e5,e6=(_out(up.get(k)) for k in ("E1","E3","E4","E5","E6"))
    event=e4.get("event") or e4.get("auction_event") or e4.get("event_type") or e4.get("liquidity_event")
    taker=e4.get("liquidity_taker") or e4.get("taker") or e4.get("aggressor")
    actor=e4.get("response_actor") or e4.get("response_side") or e4.get("responder")
    level=e4.get("event_level") or e4.get("liquidity_level") or e4.get("target_liquidity")
    ltype=e4.get("liquidity_type") or e4.get("zone_type")
    auction=e4.get("auction_state") or e4.get("auction_information")
    repricing=e5.get("repricing_state") or e5.get("value_response") or e5.get("value_state")
    if taker and actor and _text(taker)==_text(actor):dominant=_text(taker);state="ALIGNED"
    elif taker and actor:dominant="CONTESTED";state="CONTESTED"
    else:dominant="UNRESOLVED";state="UNRESOLVED"
    evidence=[]
    for label,val in (("E4_EVENT",event),("E4_TAKER",taker),("E4_RESPONSE",actor),("E4_AUCTION",auction),("E5_REPRICING",repricing)):
        if val not in (None,""):evidence.append(f"{label}={val}")
    strength="LOW" if _text(auction) in {"PENDING","LOW_INFORMATION","MEDIUM_INFORMATION"} else "MEDIUM" if dominant!="UNRESOLVED" else "LOW"
    trapped="POTENTIAL_"+_text(taker) if taker and event and "FAILED_BREAK" in _text(event) else "UNRESOLVED"
    return {"market_intent":str(event or e1.get("finding") or "UNRESOLVED"),"dominant_side":dominant,"controlled_side":_text(actor) if actor else "UNRESOLVED","trapped_side":trapped,"liquidity_target":level if level is not None else "UNRESOLVED","liquidity_type":ltype or "UNRESOLVED","repricing_direction":repricing or "UNRESOLVED","control_strength":strength,"control_state":state,"auction_state":auction or "UNRESOLVED","control_evidence":_dedupe(evidence),"evidence_sources":{"E1":e1.get("finding",e1.get("state","UNRESOLVED")),"E3":e3.get("finding",e3.get("state","UNRESOLVED")),"E4":e4.get("finding",e4.get("state","UNRESOLVED")),"E5":e5.get("finding",e5.get("state","UNRESOLVED")),"E6":e6.get("finding",setup or "UNRESOLVED")},"evidence_sufficient":bool(event or taker or actor or repricing),"no_invention":True}
def _resolve(d,s,t,e6,e7,e8,up):
    m=_state(e6,("maturity","setup_maturity","setup_stage","stage","formation_stage","lifecycle"));c=_confirmation(e7);tr=_trigger(e7);b,p=_e8(e8);eco=_economic(e8);conf=_hard(up);dr=d in DIRECTIONS;sk=bool(_clean_setup(s));sr=dr and sk and m in MATURITY_READY;cr=c in CONFIRMATION_PROVEN and tr;rs=_text(b.get("risk_gate") or b.get("risk_state") or b.get("economic_state") or b.get("plan_status") or "");rr=not eco and rs in RISK_READY_STATES and _plan_valid(p,d)
    bl=_dedupe(conf+eco+([] if dr else ["DIRECTION_UNRESOLVED"])+([] if sr else ["SETUP_NOT_MATURE"])+([] if cr else ["ENTRY_CONFIRMATION_NOT_PROVEN"])+([] if rr else ["RISK_NOT_READY"]));primary=next((x for x in BLOCKER_PRIORITY if x in bl),"NONE");lifecycle=_invalidation_lifecycle(conf,c,eco,m);allpass=dr and sr and cr and rr and not conf and not eco
    if allpass:decision,state,master=d,"EXECUTE","EXECUTE";ts,ss="ESTABLISHED","TRADE_READY";cf,rf,ex="PROVEN","READY","READY";nxt="NONE"
    elif conf:decision,state,master="NO_TRADE","REJECT","REJECTED_HARD_CONFLICT";ts="INVALIDATED" if any("INVALIDAT" in x for x in conf) else "CONFLICTED";ss=cf=rf=ex="BLOCKED";nxt=lifecycle["recovery"]
    else:decision,state,master="NO_TRADE","WAIT_FOR_PROOF","WAIT_FOR_PROOF";ts="ESTABLISHED" if dr and sk else "UNRESOLVED";ss="TRADE_READY" if sr else (m if m not in {"","UNKNOWN","UNRESOLVED","NONE"} else "FORMING") if sk else "UNRESOLVED";cf="PROVEN" if cr else c if c=="INVALIDATED" else "PENDING";rf="READY" if rr else "BLOCKED";ex="BLOCKED";nxt={"DIRECTION_UNRESOLVED":"E6_MUST_ESTABLISH_A_DIRECTIONAL_THESIS_AND_SETUP","SETUP_NOT_MATURE":"E6_MUST_REACH_MATURE_OR_TRADE_READY","ENTRY_CONFIRMATION_NOT_PROVEN":"E7_MUST_PROVE_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION","RISK_NOT_READY":"E8_MUST_PROVE_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS"}.get(primary,lifecycle["recovery"])
    return {"decision":decision,"decision_state":state,"master_state":master,"thesis_state":ts,"setup_state":ss,"confirmation_state":cf,"risk_state":rf,"execution_state":ex,"primary_blocker":primary,"secondary_blockers":[x for x in bl if x!=primary],"next_required_event":nxt,"all_gates_pass":allpass,"hard_conflict":bool(conf),"resolved_conflicts":conf,"counter_evidence":[],"direction":d,"setup":s,"thesis":t,"e6_maturity":m,"e6_identity_resolved":dr and sk,"e6_maturity_known":m not in {"","UNKNOWN","UNRESOLVED","NONE"},"e7_confirmation":c,"e7_trigger_observed":tr,"e8_risk_state":rs,"e8_plan_valid":_plan_valid(p,d),"e8_economic_blockers":eco,"trade_plan":p if _plan_valid(p,d) else {},"invalidation_lifecycle":lifecycle,"authority":{"thesis":"E6","confirmation":"E7","economics_risk":"E8","final_decision":"E9"}}
def _invalidation_lifecycle(conflicts,confirmation,economic,maturity):
    if conflicts:return {"state":"INVALIDATED" if any("INVALIDAT" in c for c in conflicts) else "CONFLICTED","event":"HARD_CONFLICT","active":True,"recovery":"NEW_CLOSED_CANDLE_MUST_RESOLVE_THE_DECISIVE_CONFLICT"}
    if confirmation=="INVALIDATED":return {"state":"INVALIDATED","event":"CONFIRMATION_INVALIDATED","active":True,"recovery":"E7_MUST_REBUILD_AND_REPROVE_SETUP_CONFIRMATION"}
    if economic:return {"state":"RISK_BLOCKED","event":"ECONOMIC_VETO_ACTIVE","active":False,"recovery":"E8_MUST_REESTABLISH_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS"}
    if maturity in MATURITY_READY:return {"state":"NONE","event":"THESIS_ACTIVE","active":False,"recovery":"E7_CONFIRMATION_REQUIRED"}
    return {"state":"NONE","event":"SETUP_FORMING","active":False,"recovery":"E6_SETUP_MUST_MATURE"}
def analyze_e9(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    e6,e7,e8=_out(upstream.get("E6")),_out(upstream.get("E7")),upstream.get("E8");d,s,t=_e6_identity(e6);r=_resolve(d,s,t,e6,e7,e8,upstream);score=round(sum((25.0 if d in DIRECTIONS else 0.0,25.0 if r["setup_state"]=="TRADE_READY" else 12.5 if r["setup_state"] in {"FORMING","VALIDATING"} else 0.0,25.0 if r["confirmation_state"]=="PROVEN" else 12.5 if r["confirmation_state"]=="PENDING" else 0.0,25.0 if r["risk_state"]=="READY" else 0.0)),2);mc=_market_control(upstream,d,s)
    ev={}
    for eid in ("E1","E2","E3","E4","E5","E6","E7","E8"):
        e=upstream.get(eid);o=_out(e);ev[eid]={"finding":o.get("finding",o.get("state","UNRESOLVED")),"gate_passed":e.gate_passed if e else None,"reason_codes":_engine_codes(e)}
    reasoning={"primary_thesis":{"direction":d,"setup":s,"state":r["thesis_state"],"text":t},"master":{"state":r["master_state"],"decision_state":r["decision_state"],"readiness_score":score},"setup":{"direction":d,"state":r["setup_state"],"name":s,"maturity":r["e6_maturity"]},"execution":{"state":r["execution_state"],"decision_state":r["decision_state"]},"confirmation":{"state":r["confirmation_state"],"trigger_observed":r["e7_trigger_observed"]},"risk":{"state":r["risk_state"],"economic_blockers":r["e8_economic_blockers"]},"market_control":mc,"conflicts":r["resolved_conflicts"],"primary_blocker":r["primary_blocker"],"next_required_event":r["next_required_event"],"closed_candle_only":True,"no_lookahead":True,"authority":r["authority"]}
    reasons=_dedupe(([r["primary_blocker"]] if r["primary_blocker"]!="NONE" else ["MASTER_GATES_PASSED"])+r["secondary_blockers"]+r["resolved_conflicts"])
    out={**r,"master_resolution":"EXECUTE" if r["all_gates_pass"] else "REJECT" if r["decision_state"]=="REJECT" else "WAIT_FOR_PROOF","readiness_score":score,"evidence_summary":ev,"professional_reasoning":reasoning,"market_control":mc,"decision_contract":{"BUY_SELL_requires_all_gates":True,"NO_TRADE_on_missing_confirmation":True,"NO_EXECUTION_on_invalid_geometry":True,"NO_EXECUTION_on_hard_conflict":True,"E9_preserves_E6_thesis_identity":True,"E9_does_not_create_thesis":True,"E9_does_not_create_entry":True,"E9_does_not_create_target":True,"E9_does_not_override_E8_economics":True,"closed_candle_only":True,"counter_evidence_does_not_equal_hard_conflict":True,"market_control_is_evidence_synthesis_only":True,"market_control_never_overrides_final_gates":True,"no_invention":True}}
    return EngineResult("E9",NAME,bool(r["all_gates_pass"]),score,out,tuple(reasons))
