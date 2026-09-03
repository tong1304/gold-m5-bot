from __future__ import annotations

import re
from typing import Any
from .contracts import EngineResult

NAME="Master Decision Brain"
QUESTION="Does the E6 core thesis survive, is there a valid closed-candle E7 trigger, are E8 economics survivable, and is there any fatal veto?"
ARCHITECTURE="E9_FINAL_GOVERNANCE_THESIS_TRIGGER_ECONOMICS"
VERSION="70.1"
DIRECTIONS={"BUY","SELL"}
PROVEN={"PROVEN","CONFIRMED","VALIDATED","TRADE_READY"}
READY={"READY","RISK_READY","ECONOMICALLY_ACCEPTABLE","TRADE_READY","VALIDATED","PASS","PASSED","COMPLETE"}
ECONOMIC_FATAL={"INVALID_TRADE_GEOMETRY","INVALID_RISK_GEOMETRY","RISK_GEOMETRY_INVALID","REAL_RR_BELOW_MINIMUM","EXECUTION_COST_TOO_HIGH","STRUCTURAL_SURVIVAL_NOT_PROVEN","EFFECTIVE_SPACE_UNRELIABLE","EFFECTIVE_SPACE_BELOW_MINIMUM","STRESSED_PROBABILITY_BELOW_MINIMUM","TARGET_REALISM_TOO_LOW","STOP_QUALITY_TOO_LOW","NO_USABLE_STRUCTURAL_TARGET","RISK_QUALITY_BELOW_DECISION_THRESHOLD"}
ECONOMIC_PENDING={"HISTORICAL_SAMPLE_INSUFFICIENT","PROFIT_EDGE_NOT_PROVEN","PROFIT_EXPECTANCY_UNQUANTIFIED","PROBABILITY_EDGE_NOT_TRUSTWORTHY"}
HARD_CONFLICTS={"THESIS_INVALIDATED","E6_THESIS_INVALIDATED","E7_CONFIRMATION_INVALIDATED","E8_RISK_INVALIDATED","STRUCTURE_INVALIDATED","BULLISH_STRUCTURE_INVALIDATED","BEARISH_STRUCTURE_INVALIDATED","E3_STRUCTURE_INVALIDATED","E3_THESIS_INVALIDATED","STRUCTURE_INTEGRITY_INVALID","PROTECTED_LEVEL_GEOMETRY_INVALID","EXECUTION_IMPOSSIBLE","DATA_INTEGRITY_INVALID","SHARED_MARKET_PICTURE_CONTRACT_BLOCKED"}
NO_THESIS_SETUP={"","NONE","UNKNOWN","NO_SETUP","NO_PLAUSIBLE_SETUP","UNRESOLVED"}


def _out(engine:EngineResult|None)->dict[str,Any]: return dict(engine.output or {}) if engine else {}
def _text(value:Any)->str:
    if isinstance(value,dict): return " ".join(f"{k}={_text(v)}" for k,v in sorted(value.items(),key=lambda x:str(x[0])))
    if isinstance(value,(list,tuple,set)): return " ".join(_text(v) for v in value)
    return str(value or "").upper().strip()
def _dedupe(values:list[Any])->list[str]:
    out=[]; seen=set()
    for value in values:
        token=_text(value)
        if token and token not in seen: seen.add(token); out.append(token)
    return out
def _codes(output:dict[str,Any])->list[str]:
    values=[]
    for key in ("reason_codes","reasons","counter_evidence","blockers","risk_blockers","economic_blockers","conflicts","invalidations","active_invalidations","hard_vetoes","blocking_reasons"):
        value=output.get(key)
        if isinstance(value,str): values.append(value)
        elif isinstance(value,(list,tuple,set)): values.extend(value)
        elif isinstance(value,dict):
            for name,flag in value.items():
                if flag is True: values.append(name)
                elif flag not in (None,"",False): values.append(flag)
    return _dedupe(values)
def _engine_codes(engine:EngineResult|None)->list[str]: return _dedupe(_codes(_out(engine))+list(engine.reason_codes or ())) if engine else []
def _walk(value:Any):
    if isinstance(value,dict):
        yield value
        for child in value.values(): yield from _walk(child)
    elif isinstance(value,(list,tuple,set)):
        for child in value: yield from _walk(child)
def _direction(*values:Any)->str:
    for value in values:
        x=_text(value)
        if x in DIRECTIONS:return x
        if x in {"UP","BULLISH","BUYERS","BUYER","BUY_CONTROLLED","BUY-CONTROLLED","TREND_UP"}:return "BUY"
        if x in {"DOWN","BEARISH","SELLERS","SELLER","SELL_CONTROLLED","SELL-CONTROLLED","TREND_DOWN"}:return "SELL"
        if re.search(r"(?:^|[ =:;,|])(BUY|UP|BULLISH|BUYERS|BUYER)(?:$|[ =:;,|])",x):return "BUY"
        if re.search(r"(?:^|[ =:;,|])(SELL|DOWN|BEARISH|SELLERS|SELLER)(?:$|[ =:;,|])",x):return "SELL"
    return "NEUTRAL"
def _state(output:dict[str,Any],keys:tuple[str,...],default="UNRESOLVED")->str:
    for key in keys:
        value=output.get(key)
        if value not in (None,""):return _text(value)
    return default

def _e6_identity(e6:dict[str,Any]):
    finding=_text(e6.get("finding")); codes=set(_codes(e6))
    if codes & {"NO_SURVIVING_SETUP","NO_ELIGIBLE_SETUP","SETUP_REJECTED","SETUP_INVALIDATED","E6_THESIS_INVALIDATED"} or "NO SURVIVING SETUP" in finding or "NO PLAUSIBLE SETUP" in finding:return "NEUTRAL","UNKNOWN","UNRESOLVED"
    setup=""
    for key in ("setup","setup_family","candidate_setup","setup_type","thesis_setup","selected_hypothesis"):
        value=e6.get(key)
        if value not in (None,"") and _text(value) not in NO_THESIS_SETUP:setup=_text(value);break
    direction=_direction(e6.get("direction"),e6.get("direction_thesis"),e6.get("thesis_direction"),e6.get("selected_direction"))
    if not setup:
        match=re.match(r"^(BUY|SELL)\s+([A-Z][A-Z0-9_]+)\s+IS\s+(?:A\s+CANDIDATE\s+HYPOTHESIS\s+ONLY|VALIDATING|FORMING|A\s+CANDIDATE|READY)",finding)
        if match:direction,setup=match.groups()
    if not setup:return "NEUTRAL","UNKNOWN","UNRESOLVED"
    thesis=str(e6.get("thesis") or e6.get("candidate_setup_thesis") or e6.get("selected_hypothesis") or finding or "UNRESOLVED").strip()
    return direction,setup,thesis or "UNRESOLVED"
def _thesis_state(e6:dict[str,Any])->str:
    codes=set(_codes(e6))
    if codes & {"THESIS_INVALIDATED","E6_THESIS_INVALIDATED","SETUP_INVALIDATED","SETUP_REJECTED"}:return "INVALIDATED"
    explicit=_state(e6,("thesis_state","thesis_lifecycle"))
    if explicit in {"INVALIDATED","REJECTED"}:return "INVALIDATED"
    if explicit in {"MATURE","CONFIRMED","VALIDATED","TRADE_READY","ESTABLISHED"}:return "MATURE"
    if explicit in {"VALIDATING","VALIDATING_SETUP","DEVELOPING"}:return "VALIDATING"
    if explicit in {"HYPOTHESIS","CANDIDATE","FORMING"}:return "HYPOTHESIS"
    maturity=_state(e6,("maturity","setup_state","opportunity_stage"))
    if maturity in {"MATURE","CONFIRMED","VALIDATED","TRADE_READY","ESTABLISHED"}:return "MATURE"
    if maturity in {"VALIDATING","VALIDATING_SETUP","DEVELOPING"}:return "VALIDATING"
    if maturity in {"HYPOTHESIS","CANDIDATE","FORMING"}:return "HYPOTHESIS"
    finding=_text(e6.get("finding"))
    if "CANDIDATE HYPOTHESIS ONLY" in finding or "REMAINS A HYPOTHESIS" in finding:return "HYPOTHESIS"
    if "VALIDATING" in finding or "FORMING" in finding:return "VALIDATING"
    return "UNRESOLVED"
def _has_surviving_thesis(e6,identity):
    direction,setup,_=identity
    return direction in DIRECTIONS and setup not in NO_THESIS_SETUP and _thesis_state(e6) in {"HYPOTHESIS","VALIDATING","MATURE"}
def _confirmation(e7):
    codes=set(_codes(e7))
    if codes & {"E7_CONFIRMATION_INVALIDATED","CONFIRMATION_INVALIDATED"}:return "INVALIDATED",False
    confirmation=_state(e7,("confirmation_state","confirmation","proof_state"))
    trigger=any(e7.get(k) is True for k in ("trigger_observed","valid_trigger","closed_candle_trigger")) or _state(e7,("trigger_state","trigger","entry_trigger")) in PROVEN
    proven=confirmation in PROVEN or bool(codes & {"CONFIRMATION_PROVEN","CAUSAL_FOLLOW_THROUGH_PROVEN","VALID_CLOSED_CANDLE_TRIGGER","TRIGGER_CONFIRMED"})
    return ("PROVEN" if proven and trigger else "PENDING"),bool(proven and trigger)
def _economic(e8):
    fatal=[]; pending=[]
    for node in _walk(e8):
        codes=set(_codes(node)); fatal.extend(c for c in codes if c in ECONOMIC_FATAL); pending.extend(c for c in codes if c in ECONOMIC_PENDING)
    fatal=_dedupe(fatal); pending=_dedupe(pending)
    state=_state(e8,("risk_state","economic_state","decision_state","plan_status")); verified=e8.get("verified") is True or e8.get("trade_plan_verified") is True
    ready=(state in READY or verified) and not fatal and not pending
    if fatal:return "BLOCKED",False,fatal,pending
    if ready:return "READY",True,[],pending
    return "PENDING",False,[],pending
def _plan_valid(e8,direction):
    plan=e8.get("trade_plan") if isinstance(e8.get("trade_plan"),dict) else e8
    if direction not in DIRECTIONS:return False
    try:entry=float(plan["entry"]);stop=float(plan["stop_loss"]);target=float(plan.get("take_profit_2",plan.get("take_profit",plan.get("tp2"))))
    except (KeyError,TypeError,ValueError):return False
    if direction=="BUY" and not stop<entry<target:return False
    if direction=="SELL" and not target<entry<stop:return False
    rr=plan.get("rr_tp2",plan.get("rr"))
    if rr not in (None,""):
        try:
            if float(rr)<1.50:return False
        except (TypeError,ValueError):return False
    return True
def _hard_conflicts(upstream):
    found=[]
    for engine_id in ("E1","E2","E3","E4","E5","E6","E7","E8"):
        engine=upstream.get(engine_id);output=_out(engine)
        for code in _engine_codes(engine):
            if code in HARD_CONFLICTS:found.append(code)
        if engine_id=="E3" and _text(output.get("structure_integrity",output.get("protected_structure",{}).get("integrity","VALID")))=="INVALID":found.append("STRUCTURE_INTEGRITY_INVALID")
        if engine_id in {"E3","E6","E7","E8"}:
            value=_text(output.get("invalidation"))
            if value.endswith("_INVALIDATED"):found.append(value)
    return _dedupe(found)
def _market_control(upstream):
    e1,e2,e3,e4,e5=(_out(upstream.get(k)) for k in ("E1","E2","E3","E4","E5"));votes=[];quality=[]
    def add(direction,source,weight,status="AUTHORITATIVE"):
        if direction in DIRECTIONS:votes.append((direction,source,weight));quality.append({"source":source,"status":status,"direction":direction,"weight":weight})
    add(_direction(e1.get("pressure"),e1.get("pressure_direction")),"E1_PRESSURE",3.0)
    if _text(e3.get("structure_integrity","VALID"))=="VALID":add(_direction(e3.get("structure_direction"),e3.get("external_state"),e3.get("structure")),"E3_STRUCTURE",3.0)
    add(_direction(e2.get("direction"),e2.get("opportunity_direction")),"E2_OPPORTUNITY",1.5,"SUPPORTING")
    e4_state=_text(e4.get("auction_state",e4.get("state")));terminal=e4_state in {"CONFIRMED","TERMINALLY_CONFIRMED","ACCEPTED","REJECTED","RECLAIMED"} or "TERMINAL" in e4_state;response=_direction(e4.get("response_actor"),e4.get("auction_response"))
    if terminal and response in DIRECTIONS:add(response,"E4_CONFIRMED_AUCTION_RESPONSE",2.5,"SUPPORTING_CONFIRMED")
    else:quality.append({"source":"E4_AUCTION_RESPONSE","status":"SUPPORTING_PENDING","direction":response,"weight":0.0})
    repricing=_direction(e5.get("repricing_direction"))
    if repricing in DIRECTIONS:add(repricing,"E5_REPRICING",1.5,"SUPPORTING")
    totals={"BUY":0.0,"SELL":0.0};evidence=[]
    for d,s,w in votes:totals[d]+=w;evidence.append({"source":s,"direction":d,"weight":w})
    total=totals["BUY"]+totals["SELL"]
    if not total:state,direction,confidence="UNRESOLVED","NEUTRAL",0.0
    elif totals["BUY"]==totals["SELL"]:state,direction,confidence="MIXED","NEUTRAL",50.0
    else:
        direction="BUY" if totals["BUY"]>totals["SELL"] else "SELL";confidence=round(max(totals.values())/total*100.0,2);state=f"{direction}-CONTROLLED" if confidence>=60 else "MIXED";direction=direction if state!="MIXED" else "NEUTRAL"
    evidence.sort(key=lambda x:(-x["weight"],x["source"]))
    return {"market_control_state":state,"control_direction":direction,"control_confidence":confidence,"control_scores":{"BUY":round(totals["BUY"],2),"SELL":round(totals["SELL"],2)},"dominant_control_evidence":[x for x in evidence if x["weight"]>=3.0] or evidence[:3],"control_evidence":evidence,"control_evidence_quality":quality,"pending_e4_response_excluded":not terminal,"authority_rule":"E4_RESPONSE_REQUIRES_TERMINAL_AUCTION_STATE"}
def _supporting_evidence(upstream):
    e2,e4,e5=(_out(upstream.get(k)) for k in ("E2","E4","E5"));e2_codes=[c for c in _engine_codes(upstream.get("E2")) if c not in HARD_CONFLICTS and c not in ECONOMIC_FATAL];e4_state=_text(e4.get("auction_state",e4.get("state","UNRESOLVED")));e4_codes=[] if e4_state in {"CONFIRMED","ACCEPTED","REJECTED","RECLAIMED"} else ["AUCTION_CONFIRMATION_PENDING"];e5_codes=[c for c in _engine_codes(upstream.get("E5")) if c not in HARD_CONFLICTS and c not in ECONOMIC_FATAL]
    return {"E2":_dedupe(e2_codes),"E4":_dedupe(e4_codes),"E5":_dedupe(e5_codes),"role":"SUPPORTING_EVIDENCE_ONLY","may_reduce_conviction":True,"may_veto":False}
def classify_lifecycle(e6,e7,e8):
    direction,setup,thesis=_e6_identity(e6)
    if not _has_surviving_thesis(e6,(direction,setup,thesis)):return {"stage":"NO_THESIS","e6_state":_thesis_state(e6),"e7_state":"NOT_APPLICABLE","e8_state":"NOT_APPLICABLE","reason":"NO_SURVIVING_E6_THESIS","direction":"NEUTRAL","setup":"UNKNOWN","thesis":"UNRESOLVED"}
    confirmation_state,confirmation_proven=_confirmation(e7);economic_state,economic_ready,_,_= _economic(e8)
    return {"stage":"EXECUTABLE_CANDIDATE" if confirmation_proven and economic_ready else "THESIS_MATURE" if _thesis_state(e6)=="MATURE" else "THESIS_FORMING","e6_state":_thesis_state(e6),"e7_state":confirmation_state,"e8_state":economic_state,"reason":"E6_THESIS_PRESENT","direction":direction,"setup":setup,"thesis":thesis}
def _no_thesis_output(control,structure_lifecycle,e4):
    reasons=["E9_FINAL_GOVERNANCE","E6_THESIS_OWNER","NO_SURVIVING_E6_THESIS"]
    return {"decision":"NO_TRADE","final_governance":"NO_THESIS","governance_decision":"NO_THESIS","governance_reason":"NO_SURVIVING_E6_THESIS","governance_blockers":["NO_SURVIVING_E6_THESIS"],"next_required_events":["E6_NEW_SURVIVING_SETUP_THESIS"],"execution_state":"BLOCKED","all_gates_pass":False,"direction":"NEUTRAL","thesis_direction":"NEUTRAL","setup":"UNKNOWN","thesis":"UNRESOLVED","thesis_state":"UNRESOLVED","thesis_lifecycle_source":"E6","setup_state":"UNRESOLVED","structure_lifecycle":structure_lifecycle,"confirmation_state":"NOT_APPLICABLE","economic_state":"NOT_APPLICABLE","economic_blockers":[],"economic_pending":[],"hard_conflicts":[],"supporting_evidence":_supporting_evidence({"E2":None,"E4":EngineResult("E4","E4",False,0,e4,()),"E5":None}),"market_control_state":control["market_control_state"],"control_direction":control["control_direction"],"control_confidence":control["control_confidence"],"control_scores":control["control_scores"],"control_evidence":control["control_evidence"],"dominant_control_evidence":control["dominant_control_evidence"],"control_evidence_quality":control["control_evidence_quality"],"proof_summary":{"core_thesis":False,"e7_trigger":"NOT_APPLICABLE","e8_economics":"NOT_APPLICABLE"},"mandatory_gates":{"core_thesis":False,"closed_candle_trigger":False,"survivable_economics":False,"fatal_veto_clear":True},"authority_contract":{"market_evidence_owner":"E1-E5","trade_thesis_owner":"E6","trigger_owner":"E7","trade_economics_owner":"E8","final_decision_owner":"E9","e9_may_rewrite_e6_thesis":False,"e9_may_bypass_e7":False,"e9_may_bypass_e8":False},"opportunity_state":"NO_THESIS","opportunity":{"direction":"NEUTRAL","setup":"UNKNOWN","state":"NO_THESIS","do_not_execute":True},"reason_codes":reasons,"reasons":reasons,"architecture":ARCHITECTURE,"version":VERSION}

def analyze_e9(snapshot,upstream):
    del snapshot
    e4,e6,e7,e8=(_out(upstream.get(k)) for k in ("E4","E6","E7","E8"));control=_market_control(upstream);direction,setup,thesis=_e6_identity(e6);structure_lifecycle=_text(_out(upstream.get("E3")).get("lifecycle") or _out(upstream.get("E3")).get("structure_lifecycle") or "UNRESOLVED")
    if not _has_surviving_thesis(e6,(direction,setup,thesis)):
        output=_no_thesis_output(control,structure_lifecycle,e4);return EngineResult("E9",NAME,False,float(control["control_confidence"]),output,tuple(output["reason_codes"]))
    thesis_state=_thesis_state(e6);confirmation_state,confirmation_proven=_confirmation(e7);economic_state,economic_ready,economic_fatal,economic_pending=_economic(e8);hard_conflicts=_hard_conflicts(upstream);plan_present=isinstance(e8.get("trade_plan"),dict) or all(k in e8 for k in ("entry","stop_loss"));plan_valid=_plan_valid(e8,direction) if plan_present else False;supporting=_supporting_evidence(upstream)
    core_thesis=direction in DIRECTIONS and setup not in NO_THESIS_SETUP and thesis_state in {"HYPOTHESIS","VALIDATING","MATURE"};fatal_veto=bool(hard_conflicts);geometry_fatal=plan_present and not plan_valid;economics_survivable=economic_ready and plan_valid and not economic_fatal and not economic_pending
    mandatory={"core_thesis":core_thesis,"closed_candle_trigger":confirmation_proven,"survivable_economics":economics_survivable,"fatal_veto_clear":not fatal_veto and not geometry_fatal}
    if fatal_veto:governance,decision,reason="REJECTED_FATAL","NO_TRADE","FATAL_GOVERNANCE_VETO"
    elif not core_thesis:governance,decision,reason="NO_THESIS","NO_TRADE","NO_SURVIVING_E6_THESIS"
    elif confirmation_state=="INVALIDATED":governance,decision,reason="REJECTED_FATAL","NO_TRADE","E7_CONFIRMATION_INVALIDATED"
    elif economic_fatal:governance,decision,reason="REJECTED_ECONOMICS","NO_TRADE",economic_fatal[0]
    elif geometry_fatal:governance,decision,reason="REJECTED_ECONOMICS","NO_TRADE","INVALID_TRADE_PLAN"
    elif confirmation_proven and economic_pending:governance,decision,reason="WATCH","NO_TRADE","WAITING_FOR_E8_ECONOMIC_PROOF"
    elif not confirmation_proven:governance,decision,reason="WATCH","NO_TRADE","WAITING_FOR_E7_TRIGGER"
    elif not economic_ready:governance,decision,reason="WATCH","NO_TRADE","WAITING_FOR_E8_SURVIVABLE_ECONOMICS"
    else:governance,decision,reason="EXECUTE",direction,"CORE_THESIS_TRIGGER_AND_ECONOMICS_PASSED"
    missing=[]
    if not confirmation_proven:missing.append("E7_VALID_CLOSED_CANDLE_TRIGGER_REQUIRED")
    if economic_pending:missing.append("E8_ECONOMIC_PROOF_REQUIRED")
    if not economic_ready and not economic_pending:missing.append("E8_SURVIVABLE_ECONOMICS_REQUIRED")
    if economic_ready and not plan_valid:missing.append("VALID_TRADE_PLAN_REQUIRED")
    reasons=_dedupe(["E9_FINAL_GOVERNANCE","E6_THESIS_OWNER","E7_TRIGGER_OWNER","E8_ECONOMICS_OWNER",reason]+missing+economic_fatal+economic_pending+hard_conflicts)
    conviction_flags=_dedupe(supporting["E2"]+supporting["E4"]+supporting["E5"])
    output={"decision":decision,"final_governance":governance,"governance_decision":governance,"governance_reason":reason,"governance_blockers":_dedupe(economic_fatal+hard_conflicts+( ["INVALID_TRADE_PLAN"] if geometry_fatal else [])),"next_required_events":missing,"execution_state":"APPROVED" if governance=="EXECUTE" else "BLOCKED","all_gates_pass":governance=="EXECUTE","direction":direction,"thesis_direction":direction,"setup":setup,"thesis":thesis,"thesis_state":thesis_state,"thesis_lifecycle_source":"E6","setup_state":_state(e6,("setup_state","opportunity_stage","maturity"),thesis_state),"structure_lifecycle":structure_lifecycle,"confirmation_state":confirmation_state,"economic_state":economic_state,"economic_blockers":economic_fatal,"economic_pending":economic_pending,"hard_conflicts":hard_conflicts,"supporting_evidence":supporting,"supporting_conviction_flags":conviction_flags,"supporting_evidence_is_non_veto":True,"market_control_state":control["market_control_state"],"control_direction":control["control_direction"],"control_confidence":control["control_confidence"],"control_scores":control["control_scores"],"control_evidence":control["control_evidence"],"dominant_control_evidence":control["dominant_control_evidence"],"control_evidence_quality":control["control_evidence_quality"],"pending_e4_response_excluded":control["pending_e4_response_excluded"],"control_authority_rule":control["authority_rule"],"evidence_alignment":"ALIGNED" if control["control_direction"]==direction else "UNRESOLVED","evidence_alignment_reason":"SUPPORTING_EVIDENCE_ONLY","proof_summary":{"core_thesis":core_thesis,"e6_thesis":thesis_state,"e7_trigger":confirmation_state,"e8_economics":economic_state,"e8_blockers":economic_fatal,"e8_pending":economic_pending},"mandatory_gates":mandatory,"fatal_vetoes":hard_conflicts+(["INVALID_TRADE_PLAN"] if geometry_fatal else []),"authority_contract":{"market_evidence_owner":"E1-E5","trade_thesis_owner":"E6","trigger_owner":"E7","trade_economics_owner":"E8","final_decision_owner":"E9","e9_may_rewrite_e6_thesis":False,"e9_may_bypass_e7":False,"e9_may_bypass_e8":False},"opportunity_state":governance,"opportunity":{"direction":direction,"setup":setup,"state":governance,"do_not_execute":governance!="EXECUTE","economic_blockers":economic_fatal,"economic_pending":economic_pending,"supporting_evidence":supporting},"reason_scope":"THESIS_TRIGGER_ECONOMICS_WITH_SUPPORTING_EVIDENCE","reason_codes":reasons,"reasons":reasons,"architecture":ARCHITECTURE,"version":VERSION,"lifecycle":classify_lifecycle(e6,e7,e8)}
    return EngineResult("E9",NAME,governance=="EXECUTE",float(control["control_confidence"]),output,tuple(reasons))
