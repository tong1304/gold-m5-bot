from __future__ import annotations
from typing import Any
from .contracts import EngineResult
from .e6_brain_legacy import analyze_e6 as _legacy_analyze_e6

ARCHITECTURE="E6_OPPORTUNITY_THESIS_ENGINE_V55.1"
VERSION="55.1"


def _text(v:Any)->str:return str(v or "").upper().strip()

def _direction_value(v:Any)->str:
    t=_text(v)
    if t in {"BUY","BULLISH","UP","LONG","BUYERS","TREND_UP"} or t.startswith("BUY "):return "BUY"
    if t in {"SELL","BEARISH","DOWN","SHORT","SELLERS","TREND_DOWN"} or t.startswith("SELL "):return "SELL"
    return "NEUTRAL"


def _direction(v:Any, e2:dict[str,Any]|None=None, e3:dict[str,Any]|None=None, e4:dict[str,Any]|None=None):
    """Return scalar direction for internal use; preserve the legacy 4-input contract for tests/callers."""
    if e2 is None and e3 is None and e4 is None:
        return _direction_value(v)

    e1 = dict(v or {})
    e2 = dict(e2 or {})
    e3 = dict(e3 or {})
    e4 = dict(e4 or {})
    e1d = _direction_value(e1.get("directional_pressure", e1.get("pressure", e1.get("direction"))))
    e2d = _direction_value(e2.get("direction", e2.get("opportunity_direction")))
    e3_external = _direction_value(e3.get("external_state", e3.get("direction", e3.get("finding"))))
    e3_internal = _direction_value(e3.get("internal_state"))
    e4d = _direction_value(e4.get("direction"))
    event = _text(e4.get("event", e4.get("finding")))
    actor = _direction_value(e4.get("response_actor"))
    taker = _direction_value(e4.get("liquidity_taker"))
    if e4d == "NEUTRAL":
        if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
            e4d = "SELL"
        elif "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
            e4d = "BUY"
        elif "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:
            e4d = "BUY"
        elif "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:
            e4d = "SELL"
        elif "FAILED_BREAK_RECLAIM" in event and actor != "NEUTRAL":
            e4d = actor
        elif taker != "NEUTRAL" and "LIQUIDITY_INTERACTION" in event:
            e4d = taker
    conflicts=[]
    support=[]
    if e1d in {"BUY","SELL"} and e3_external in {"BUY","SELL"} and e1d == e3_external:
        direction=e1d
        support.append("E1_E3_DIRECTIONAL_CORE")
    elif e3_external in {"BUY","SELL"}:
        direction=e3_external
        support.append("E3_STRUCTURE_CONVERGENCE")
    elif e1d in {"BUY","SELL"}:
        direction=e1d
        support.append("E1_DIRECTIONAL_CORE")
    elif e2d in {"BUY","SELL"}:
        direction=e2d
        support.append("E2_DIRECTIONAL_ANCHOR")
    elif e4d in {"BUY","SELL"}:
        direction=e4d
        support.append("E4_TERMINAL_AUCTION" if _text(e4.get("auction_state")) in {"CONFIRMED","TERMINALLY_CONFIRMED","ACCEPTED","RECLAIMED"} else "E4_AUCTION")
    else:
        direction="NEUTRAL"
        support.append("NO_DIRECTIONAL_CORE")
    if e4d in {"BUY","SELL"} and direction in {"BUY","SELL"} and e4d != direction:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if e2d in {"BUY","SELL"} and direction in {"BUY","SELL"} and e2d != direction:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if e3_internal in {"BUY","SELL"} and direction in {"BUY","SELL"} and e3_internal != direction:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    return direction, list(dict.fromkeys(support)), list(dict.fromkeys(conflicts)), support[0]


def _out(r:Any)->dict[str,Any]:return dict(getattr(r,"output",{}) or {})
def _payload(upstream:dict[str,Any],key:str)->dict[str,Any]:
    r=upstream.get(key);return _out(r) if r else {}
def _e2_unresolved(e2:dict[str,Any])->bool:
    finding=_text(e2.get("finding",e2.get("state")));state=_text(e2.get("opportunity_state",e2.get("opportunity_decision")));maturity=_text(e2.get("opportunity_maturity"))
    return finding in {"UNRESOLVED","UNPROVEN","AMBIGUOUS","WAIT","EMERGING","PENDING","DEVELOPING"} or state in {"UNRESOLVED","UNPROVEN","AMBIGUOUS","WAIT","EMERGING","PENDING","DEVELOPING"} or maturity in {"UNPROVEN","EMERGING","DEVELOPING"} or "OPPORTUNITY IS DEVELOPING" in finding or "OPPORTUNITY IS EMERGING" in finding
def _e2_direction(e2:dict[str,Any])->str:
    for key in ("direction","opportunity_direction","auction_direction"):
        d=_direction_value(e2.get(key))
        if d!="NEUTRAL":return d
    finding=_text(e2.get("finding",e2.get("state")))
    if any(x in finding for x in ("UP OPPORTUNITY","BUY OPPORTUNITY")):return "BUY"
    if any(x in finding for x in ("DOWN OPPORTUNITY","SELL OPPORTUNITY")):return "SELL"
    return "NEUTRAL"
def _e3_direction(e3:dict[str,Any],key:str)->str:return _direction_value(e3.get(key))
def _e4_direction(e4:dict[str,Any])->str:
    d=_direction_value(e4.get("direction"))
    if d!="NEUTRAL":return d
    event=_text(e4.get("event",e4.get("finding")));taker=_direction_value(e4.get("liquidity_taker"));actor=_direction_value(e4.get("response_actor"))
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
    e1d=_direction_value(e1.get("directional_pressure",e1.get("pressure")));e2d=_e2_direction(e2);internal=_e3_direction(e3,"internal_state");external=_e3_direction(e3,"external_state");e4d=_e4_direction(e4);event=_e4_event(e4);unresolved=_e2_unresolved(e2);e2neutral=e2d=="NEUTRAL" and not unresolved
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
    out=dict(legacy.output or {})
    direction=o["direction"]
    missing=list(dict.fromkeys(o["missing"]))
    counter=list(dict.fromkeys(o.get("counter_evidence",[])))
    hard=list(dict.fromkeys(o.get("hard_conflicts",[])))
    contested="E1_COUNTER_EVIDENCE" in counter or "STRUCTURAL_SPACE_INSUFFICIENT" in missing
    stage="CONTESTED" if contested else "FORMING"
    state="THESIS_CONTESTED" if contested else "SETUP_THESIS"
    setup=o["family"]
    finding=f"{direction} setup thesis is {stage.lower()}; internal structure is {o['internal_status']} and confirmation/economics are not yet proven."
    thesis=f"{direction} causal setup thesis is established from E1-E5; E2 classification is not a hard veto, and E7/E8 proof remains pending."
    out.update({
        "architecture":ARCHITECTURE,
        "version":VERSION,
        "state":state,
        "setup_state":state,
        "opportunity_stage":"SETUP_THESIS" if not contested else "THESIS_CONTESTED",
        "setup":setup,
        "setup_family":setup,
        "candidate_type":"SETUP_CANDIDATE",
        "direction":direction,
        "direction_thesis":direction,
        "thesis_direction":direction,
        "trade_ready":False,
        "gate_passed":False,
        "thesis_status":stage,
        "finding":finding,
        "thesis":thesis,
        "supporting_evidence":o["support"],
        "counter_evidence":counter,
        "hard_conflicts":hard,
        "missing_proof":missing,
        "next_required_event":"E7_CONFIRMATION,E8_SURVIVABLE_ECONOMICS",
        "wait_for":"E7_CONFIRMATION,E8_SURVIVABLE_ECONOMICS",
        "candidate_identity":f"SETUP_THESIS:{direction}:{setup}",
        "opportunity_id":f"{direction}|SETUP_THESIS",
        "event_id":o["event_id"],
        "available_space_atr":o["space"],
        "watch_only":False,
        "execution_authority":"E9",
        "reason_codes":missing,
        "reasons":missing,
    })
    return EngineResult(legacy.engine_id,legacy.name,False,legacy.score,out,tuple(missing))

def _no_surviving_causal_thesis(legacy:EngineResult)->EngineResult:
    out=dict(legacy.output or {});out.update({"architecture":ARCHITECTURE,"version":VERSION,"state":"NO_SETUP","setup_state":"NO_SETUP","opportunity_stage":"ABSENT","setup":"NO_SETUP","setup_family":"","candidate_type":"NONE","direction":"NEUTRAL","direction_thesis":"NEUTRAL","thesis_direction":"NEUTRAL","trade_ready":False,"gate_passed":False,"thesis_status":"ABSENT","finding":"No surviving causal opportunity thesis from E1-E5; legacy pattern output is suppressed.","thesis":"E6 cannot create an independent setup when upstream causal evidence does not support an opportunity.","supporting_evidence":[],"counter_evidence":[],"hard_conflicts":[],"missing_proof":["E1_E2_E3_E4_E5_CAUSAL_OPPORTUNITY"],"next_required_event":"NEW_CAUSAL_OPPORTUNITY_FROM_E1_E5","wait_for":"NEW_CAUSAL_OPPORTUNITY_FROM_E1_E5","candidate_identity":"","opportunity_id":"","event_id":"","available_space_atr":0.0,"watch_only":False,"execution_authority":"E9","reason_codes":["NO_CAUSAL_OPPORTUNITY"],"reasons":["NO_CAUSAL_OPPORTUNITY"]});return EngineResult(legacy.engine_id,legacy.name,False,legacy.score,out,("NO_CAUSAL_OPPORTUNITY",))

def analyze_e6(market_data:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    legacy=_legacy_analyze_e6(market_data,upstream)
    e3=_payload(upstream,"E3")
    if e3 and (e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True or _text(e3.get("lifecycle")) == "INVALIDATED" or "STRUCTURE_INVALIDATED" in _text(e3.get("finding")) or "STRUCTURE_INVALIDATED" in _text(e3.get("invalidation"))):
        out=dict(legacy.output or {})
        out.update({"state":"INVALIDATED","setup_state":"INVALIDATED","opportunity_stage":"INVALIDATED","setup":"NO_SETUP","setup_family":"","candidate_type":"NONE","direction":"NEUTRAL","direction_thesis":"NEUTRAL","thesis_direction":"NEUTRAL","trade_ready":False,"gate_passed":False,"thesis_status":"INVALIDATED","finding":"E3 structure is invalidated; E6 cannot carry the prior setup direction forward.","supporting_evidence":[],"counter_evidence":["E3_STRUCTURE_INVALIDATED"],"hard_conflicts":["E3_STRUCTURE_INVALIDATED"],"missing_proof":["NEW_VALID_STRUCTURE"],"next_required_event":"NEW_VALID_STRUCTURE","wait_for":"NEW_VALID_STRUCTURE","candidate_identity":"","opportunity_id":"","event_id":"","available_space_atr":0.0,"watch_only":False,"execution_authority":"E9","reason_codes":["E3_STRUCTURE_INVALIDATED"],"reasons":["E3_STRUCTURE_INVALIDATED"]})
        return EngineResult(legacy.engine_id,legacy.name,False,legacy.score,out,("E3_STRUCTURE_INVALIDATED",))
    o=_causal_opportunity(upstream)
    if o is None:return _no_surviving_causal_thesis(legacy)
    cur=_out(legacy);ld=_direction_value(cur.get("direction"));ls=_text(cur.get("setup"));has_setup=_text(cur.get("state")) not in {"ABSENT","NO_SETUP"} and ls not in {"","NONE","NO_SETUP","UNKNOWN"}
    if has_setup and ld==o["direction"]:return legacy
    return _watch_result(legacy,o)
