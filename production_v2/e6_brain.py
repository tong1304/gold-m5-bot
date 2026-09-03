from __future__ import annotations
from typing import Any
from .contracts import EngineResult
from .e6_brain_legacy import analyze_e6 as _legacy_analyze_e6
ARCHITECTURE="E6_OPPORTUNITY_THESIS_ENGINE_V55"
VERSION="55.0"

def _text(v:Any)->str:return str(v or "").upper().strip()
def _direction(v:Any)->str:
    t=_text(v)
    if t in {"BUY","BULLISH","UP","LONG","BUYERS","TREND_UP"} or t.startswith("BUY "):return "BUY"
    if t in {"SELL","BEARISH","DOWN","SHORT","SELLERS","TREND_DOWN"} or t.startswith("SELL "):return "SELL"
    return "NEUTRAL"
def _out(r:Any)->dict[str,Any]:return dict(getattr(r,"output",{}) or {})
def _payload(upstream:dict[str,Any],key:str)->dict[str,Any]:
    r=upstream.get(key);return _out(r) if r else {}
def _e2_unresolved(e2:dict[str,Any])->bool:
    finding=_text(e2.get("finding",e2.get("state")));state=_text(e2.get("opportunity_state",e2.get("opportunity_decision")));maturity=_text(e2.get("opportunity_maturity"))
    return finding in {"UNRESOLVED","UNPROVEN","AMBIGUOUS","WAIT","EMERGING","PENDING","DEVELOPING"} or state in {"UNRESOLVED","UNPROVEN","AMBIGUOUS","WAIT","EMERGING","PENDING","DEVELOPING"} or maturity in {"UNPROVEN","EMERGING","DEVELOPING"} or "OPPORTUNITY IS DEVELOPING" in finding or "OPPORTUNITY IS EMERGING" in finding
def _e2_direction(e2:dict[str,Any])->str:
    for key in ("direction","opportunity_direction","auction_direction"):
        d=_direction(e2.get(key))
        if d!="NEUTRAL":return d
    finding=_text(e2.get("finding",e2.get("state")))
    if any(x in finding for x in ("UP OPPORTUNITY","BUY OPPORTUNITY")):return "BUY"
    if any(x in finding for x in ("DOWN OPPORTUNITY","SELL OPPORTUNITY")):return "SELL"
    return "NEUTRAL"
def _e3_direction(e3:dict[str,Any],key:str)->str:return _direction(e3.get(key))
def _e4_direction(e4:dict[str,Any])->str:
    d=_direction(e4.get("direction"))
    if d!="NEUTRAL":return d
    event=_text(e4.get("event",e4.get("finding")));taker=_direction(e4.get("liquidity_taker"));actor=_direction(e4.get("response_actor"))
    if "HIGH_LIQUIDITY_INTERACTION" in event and taker!="NEUTRAL":return taker
    if "LOW_LIQUIDITY_INTERACTION" in event and taker!="NEUTRAL":return taker
    if "LOW_FAILED_BREAK_RECLAIM" in event or "HIGH_FAILED_BREAK_RECLAIM" in event:
        if actor!="NEUTRAL":return actor
        if "UP" in event:return "BUY"
        if "DOWN" in event:return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:return "BUY"
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:return "SELL"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:return "SELL"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:return "BUY"
    return actor if actor!="NEUTRAL" else "NEUTRAL"
def _e4_event(e4:dict[str,Any])->str:return _text(e4.get("event",e4.get("finding")))
def _e5_space(e5:dict[str,Any],direction:str)->float:
    key="available_space_atr_long" if direction=="BUY" else "available_space_atr_short"
    try:
        x=float(e5.get(key,0.0) or 0.0);return x if x==x else 0.0
    except (TypeError,ValueError):return 0.0

def _causal_opportunity(upstream:dict[str,Any])->dict[str,Any]|None:
    e1,e2,e3,e4,e5=(_payload(upstream,k) for k in ("E1","E2","E3","E4","E5"))
    e1d=_direction(e1.get("directional_pressure",e1.get("pressure")));e2d=_e2_direction(e2);internal=_e3_direction(e3,"internal_state");external=_e3_direction(e3,"external_state");e4d=_e4_direction(e4);event=_e4_event(e4);unresolved=_e2_unresolved(e2);e2neutral=e2d=="NEUTRAL" and not unresolved
    counter=[];hard=[];missing_internal=[]
    if e1d!="NEUTRAL" and external!="NEUTRAL" and e1d!=external:
        if (unresolved or e2neutral) and e4d==external:
            core=external;counter.append("E1_COUNTER_EVIDENCE")
        else:return None
    else:core=e1d if e1d!="NEUTRAL" else external
    if core=="NEUTRAL":core=e2d
    if core=="NEUTRAL":return None
    primary=e1d!="NEUTRAL" or e2d!="NEUTRAL" or (external==core and e4d==core)
    exception=e1d!="NEUTRAL" and external!="NEUTRAL" and e1d!=external and (unresolved or e2neutral) and e4d==external
    if not primary and not exception:return None
    if external!="NEUTRAL" and external!=core:return None
    if internal==core:internal_status="ALIGNED"
    elif internal in {"BUY","SELL","UP","DOWN"} and internal!=core:internal_status="COUNTERFLOW";counter.append("E3_INTERNAL_COUNTER_EVIDENCE");missing_internal.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    elif internal=="MIXED":internal_status="UNRESOLVED_COUNTERFLOW";counter.append("E3_INTERNAL_COUNTER_EVIDENCE");missing_internal.extend(["E3_INTERNAL_EVIDENCE_UNRESOLVED","E3_INTERNAL_STRUCTURE_ALIGNMENT"])
    else:internal_status="UNRESOLVED";counter.append("E3_INTERNAL_EVIDENCE_UNRESOLVED");missing_internal.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    if e2d!="NEUTRAL" and e2d!=core:return None
    if e4d not in {"NEUTRAL",core}:return None
    if not any(x in event for x in ("ACCEPTANCE","REJECTION","SWEEP","FAILED_BREAK","BREAK","RECLAIM","LIQUIDITY_INTERACTION")):return None
    space=_e5_space(e5,core);value=_text(e5.get("value_state"));location=_text(e5.get("structural_location"));favorable="FAVORABLE_LOCATION" in _text(e5.get("finding")) or location in {"AT_SUPPORT","AT_RESISTANCE"} or value in {"DISCOUNT","PREMIUM"}
    if not favorable and space<=0.0:return None
    family="AUCTION_ACCEPTANCE_CONTINUATION" if "ACCEPTANCE" in event else "LIQUIDITY_RESPONSE" if any(x in event for x in ("REJECTION","SWEEP","FAILED_BREAK","RECLAIM","LIQUIDITY_INTERACTION")) else "STRUCTURAL_OPPORTUNITY"
    missing=( ["E2_OPPORTUNITY_CONFIRMATION"] if (unresolved or e2neutral) else [] )+["E7_CONFIRMATION"]
    if "PENDING" in _text(e4.get("auction_state",e4.get("state"))) or "CANDIDATE" in event or "LIQUIDITY_INTERACTION" in event:missing.insert(1 if (unresolved or e2neutral) else 0,"E4_AUCTION_FOLLOW_THROUGH")
    if space<0.75:missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    missing.extend(missing_internal)
    support=["E3_EXTERNAL_STRUCTURE_SUPPORT","E4_DIRECTIONAL_AUCTION_EVIDENCE"]
    if e1d==core:support.insert(0,"E1_DIRECTIONAL_CORE")
    elif e1d!="NEUTRAL":counter.append("E1_COUNTER_EVIDENCE")
    if e2d==core:support.insert(0,"E2_DIRECTIONAL_ANCHOR")
    if e2neutral:support.append("E2_NEUTRAL_NOT_A_VETO")
    if internal_status=="ALIGNED":support.append("E3_INTERNAL_STRUCTURE_SUPPORT")
    if favorable:support.append("E5_LOCATION_VALUE_SUPPORT")
    return {"direction":core,"family":family,"space":round(space,4),"support":list(dict.fromkeys(support)),"missing":list(dict.fromkeys(missing)),"counter_evidence":list(dict.fromkeys(counter)),"hard_conflicts":list(dict.fromkeys(hard)),"event":event,"event_id":str(e4.get("event_id") or e4.get("event_candle_id") or ""),"internal_status":internal_status}

def _watch_result(legacy:EngineResult,o:dict[str,Any])->EngineResult:
    out=dict(legacy.output or {});direction=o["direction"];missing=list(dict.fromkeys(o["missing"]));counter=list(dict.fromkeys(o.get("counter_evidence",[])));hard=list(dict.fromkeys(o.get("hard_conflicts",[])));contested="E1_COUNTER_EVIDENCE" in counter or "STRUCTURAL_SPACE_INSUFFICIENT" in missing;stage="CONTESTED" if contested else "FORMING";state="THESIS_CONTESTED" if contested else "FORMING";setup="OPPORTUNITY_THESIS" if contested else "OPPORTUNITY_WATCH"
    out.update({"architecture":ARCHITECTURE,"version":VERSION,"state":state,"setup_state":state,"opportunity_stage":stage,"setup":setup,"setup_family":o["family"],"candidate_type":"OPPORTUNITY_CANDIDATE","direction":direction,"direction_thesis":direction,"thesis_direction":direction,"trade_ready":False,"gate_passed":False,"thesis_status":stage,"finding":f"{direction} opportunity thesis is {stage.lower()}; internal structure is {o['internal_status']} and trade setup is not yet proven.","thesis":f"{direction} causal opportunity is trackable; E2 classification is not treated as a veto, while E4/E7 proof remains pending.","supporting_evidence":o["support"],"counter_evidence":counter,"hard_conflicts":hard,"missing_proof":missing,"next_required_event":"E2_OPPORTUNITY_CONFIRMATION,E4_AUCTION_FOLLOW_THROUGH,E7_CONFIRMATION","wait_for":"E2_OPPORTUNITY_CONFIRMATION,E4_AUCTION_FOLLOW_THROUGH,E7_CONFIRMATION","candidate_identity":f"OPPORTUNITY_THESIS:{direction}:{o['family']}" if contested else f"OPPORTUNITY_WATCH:{direction}:{o['family']}","opportunity_id":f"{direction}|OPPORTUNITY_THESIS" if contested else f"{direction}|OPPORTUNITY_WATCH","event_id":o["event_id"],"available_space_atr":o["space"],"watch_only":True,"execution_authority":"E9","reason_codes":missing,"reasons":missing})
    return EngineResult(legacy.engine_id,legacy.name,False,legacy.score,out,tuple(missing))
def _no_surviving_causal_thesis(legacy:EngineResult)->EngineResult:
    out=dict(legacy.output or {});out.update({"architecture":ARCHITECTURE,"version":VERSION,"state":"NO_SETUP","setup_state":"NO_SETUP","opportunity_stage":"ABSENT","setup":"NO_SETUP","setup_family":"","candidate_type":"NONE","direction":"NEUTRAL","direction_thesis":"NEUTRAL","thesis_direction":"NEUTRAL","trade_ready":False,"gate_passed":False,"thesis_status":"ABSENT","finding":"No surviving causal opportunity thesis from E1-E5; legacy pattern output is suppressed.","thesis":"E6 cannot create an independent setup when upstream causal evidence does not support an opportunity.","supporting_evidence":[],"counter_evidence":[],"hard_conflicts":[],"missing_proof":["E1_E2_E3_E4_E5_CAUSAL_OPPORTUNITY"],"next_required_event":"NEW_CAUSAL_OPPORTUNITY_FROM_E1_E5","wait_for":"NEW_CAUSAL_OPPORTUNITY_FROM_E1_E5","candidate_identity":"","opportunity_id":"","event_id":"","available_space_atr":0.0,"watch_only":False,"execution_authority":"E9","reason_codes":["NO_CAUSAL_OPPORTUNITY"],"reasons":["NO_CAUSAL_OPPORTUNITY"]});return EngineResult(legacy.engine_id,legacy.name,False,legacy.score,out,("NO_CAUSAL_OPPORTUNITY",))
def analyze_e6(market_data:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    legacy=_legacy_analyze_e6(market_data,upstream);o=_causal_opportunity(upstream)
    if o is None:return _no_surviving_causal_thesis(legacy)
    cur=_out(legacy);ld=_direction(cur.get("direction"));ls=_text(cur.get("setup"));has_setup=_text(cur.get("state")) not in {"ABSENT","NO_SETUP"} and ls not in {"","NONE","NO_SETUP","UNKNOWN"}
    if has_setup and ld==o["direction"]:return legacy
    return _watch_result(legacy,o)
