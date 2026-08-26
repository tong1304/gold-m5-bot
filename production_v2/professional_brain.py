from __future__ import annotations

import re
from typing import Any

from .contracts import EngineResult
from .e9_learning import build_advisory
from .engines import ENGINE_NAMES, run_engine as _engine_analyzer

SPECIALIST_QUESTIONS = {"E1":"What market state is present right now?","E2":"What opportunity/regime is the market offering?","E3":"What does market structure say?","E4":"Where is liquidity and what did price do with it?","E5":"Is current price in an advantageous location?","E6":"What setup, if any, is forming?","E7":"Is the setup thesis confirmed by price action?","E8":"What are the trade economics, invalidation and asymmetry?"}
EVIDENCE_WEIGHTS={"E1":1.0,"E2":1.0,"E3":1.2,"E4":1.15,"E5":1.1,"E6":1.2,"E7":1.3,"E8":1.25}
DIRECTIONS={"BUY","SELL"}

def run_professional_engine(engine_id:str,context:dict[str,Any])->EngineResult:
    raw=_engine_analyzer(engine_id,dict(context)); o=dict(raw.output); o.update({"analysis_status":"COMPLETE","analysis_complete":True,"specialist_question":SPECIALIST_QUESTIONS.get(engine_id),"trade_decision_authority":False,"specialist_gate":"NONE","gate":None,"reasoning_role":"SPECIALIST_EVIDENCE"}); return EngineResult(raw.engine_id,raw.name,None,raw.score,o,raw.reason_codes)

def _clamp(v:float,lo=0.0,hi=100.0)->float:return max(lo,min(hi,float(v)))
def _text(v:Any)->str:return str(v).upper()
def _has(blob:str,*terms:str)->bool:return any(t in blob for t in terms)
def _nested(v:Any)->list[Any]:
    if isinstance(v,dict):
        r=[]
        for x in v.values():r+=_nested(x)
        return r
    if isinstance(v,(list,tuple,set)):
        r=[]
        for x in v:r+=_nested(x)
        return r
    return [v]
def _blob(e:EngineResult|None)->str:return _text(_nested(e.output)) if e else ""
def _exact(e:EngineResult|None,token:str)->bool:return bool(re.search(rf"(?<![A-Z0-9_]){re.escape(token)}(?![A-Z0-9_])",_blob(e)))

def _structured_direction(e:EngineResult|None)->str|None:
    if not e:return None
    o=e.output or {}
    for c in (o.get("direction"),o.get("bias"),o.get("orientation"),o.get("market_direction")):
        v=_text(c).strip()
        if v in DIRECTIONS:return v
        if v in {"BULLISH","UP","LONG","TREND_UP"}:return "BUY"
        if v in {"BEARISH","DOWN","SHORT","TREND_DOWN"}:return "SELL"
    return None

def _directional_evidence(e:EngineResult|None)->tuple[float,float]:
    if not e:return 0.0,0.0
    w=EVIDENCE_WEIGHTS.get(e.engine_id,1.0); d=_structured_direction(e)
    if d=="BUY":return w,0.0
    if d=="SELL":return 0.0,w
    c=_text((e.output or {}).get("professional_reasoning",{}).get("conclusion")) if isinstance((e.output or {}).get("professional_reasoning"),dict) else ""
    b=_has(c,"BUY","BULLISH","TREND_UP","LONG");s=_has(c,"SELL","BEARISH","TREND_DOWN","SHORT")
    return (w*.75,0.0) if b and not s else (0.0,w*.75) if s and not b else (0.0,0.0)

def _direction(evidence:dict[str,EngineResult])->str:
    b=sum(_directional_evidence(e)[0] for e in evidence.values());s=sum(_directional_evidence(e)[1] for e in evidence.values());return "BUY" if b>s else "SELL" if s>b else "NEUTRAL"

def _weighted_alignment(upstream:list[EngineResult])->float:
    w=[EVIDENCE_WEIGHTS.get(e.engine_id,1.0) for e in upstream];return round(sum(_clamp(e.score)*x for e,x in zip(upstream,w))/sum(w),2) if w else 0.0

def _dimension_state(by:dict[str,EngineResult])->dict[str,bool]:
    b={k:_blob(by.get(k)) for k in SPECIALIST_QUESTIONS}
    return {"market_context":bool(b["E1"] or b["E2"]),"structure_support":_has(b["E3"],"BOS","BREAK_OF_STRUCTURE","HIGHER_HIGH","LOWER_LOW","STRUCTURE"),"liquidity_event":_has(b["E4"],"SWEEP","RECLAIM","REJECTION","LIQUIDITY"),"location_quality":_has(b["E5"],"ADVANTAGEOUS","FAVORABLE","DISCOUNT","PREMIUM","GOOD_LOCATION"),"setup_mature":_has(b["E6"],"MATURE","FORMED","VALID_SETUP","CONTINUATION_SETUP","REVERSAL_SETUP"),"confirmation":_has(b["E7"],"CONFIRMED","CONFIRMATION_PASS","TRIGGER_OBSERVED","FOLLOW_THROUGH"),"economics":_has(b["E8"],"ATTRACTIVE","RISK_GATE_READY","RR_OK","POSITIVE_EXPECTANCY")}

def _conflicts(by):
    r=[]
    for a,b,n in (("E1","E3","E1_E3_DIRECTION_CONFLICT"),("E6","E7","E6_E7_DIRECTION_CONFLICT")):
        da,db=_structured_direction(by.get(a)),_structured_direction(by.get(b))
        if da and db and da!=db:r.append(n)
    return r

def _hard_invalidations(by):
    r=[]
    for eid in ("E3","E6","E7","E8"):
        if any(_exact(by.get(eid),t) for t in ("INVALIDATED","HARD_INVALIDATION","STRUCTURE_INVALIDATED","SETUP_INVALIDATED")):r.append(f"{eid}_THESIS_INVALIDATED")
    if any(_exact(by.get("E8"),t) for t in ("INVALID_RISK","INVALID_RISK_GEOMETRY","NEGATIVE_RR","RR_BELOW_MINIMUM")):r.append("E8_RISK_GEOMETRY_INVALID")
    return sorted(set(r))

def _execution_readiness(by:dict[str,EngineResult],direction:str)->dict[str,Any]:
    if direction not in DIRECTIONS:return {"ready":False,"reasons":["NO_ACTIONABLE_DIRECTION"]}
    e8=by.get("E8")
    if e8 is None:return {"ready":False,"reasons":["E8_MISSING"]}
    o=e8.output or {};p=o.get("trade_plan")
    if not isinstance(p,dict):return {"ready":False,"reasons":["E8_TRADE_PLAN_INCOMPLETE"]}
    # Accept the canonical plan fields used by execution/Telegram.
    required=("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2")
    if any(p.get(k) is None for k in required):return {"ready":False,"reasons":["E8_TRADE_PLAN_INCOMPLETE"]}
    if _text(o.get("risk_gate")) not in {"RISK_READY","PASS","READY","TRUE"}:return {"ready":False,"reasons":["E8_RISK_NOT_READY"]}
    try:
        if float(p["rr_tp2"])<=0:return {"ready":False,"reasons":["E8_INVALID_RR"]}
    except (TypeError,ValueError):return {"ready":False,"reasons":["E8_INVALID_RR"]}
    return {"ready":True,"reasons":[]}

def run_professional_e9(context:dict[str,Any],upstream:list[EngineResult],historical_calibration=None)->EngineResult:
    by={e.engine_id:e for e in upstream};d=_direction(by);dims=_dimension_state(by);conf=_conflicts(by);inv=_hard_invalidations(by);alignment=_weighted_alignment(upstream)
    thesis=round(_clamp(alignment+sum(3.5 for k in ("structure_support","liquidity_event","location_quality","setup_mature","confirmation","economics") if dims[k])-min(24.0,len(conf)*8.0)),2) if d!="NEUTRAL" else 0.0
    execution=_execution_readiness(by,d);reasons=list(inv)+list(conf)
    if d=="NEUTRAL":reasons.append("DIRECTIONAL_THESIS_UNRESOLVED")
    if not dims["setup_mature"]:reasons.append("SETUP_NOT_MATURE")
    if not dims["confirmation"]:reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not dims["economics"]:reasons.append("TRADE_ECONOMICS_NOT_READY")
    reasons+=execution["reasons"]
    ready=(d in DIRECTIONS and execution["ready"] and dims["setup_mature"] and dims["confirmation"] and dims["economics"] and thesis>=70 and not conf and not inv)
    decision=d if ready else "NO_TRADE"
    plan=by["E8"].output.get("trade_plan") if by.get("E8") else None
    out={"decision":decision,"decision_authority":"E9","trade_decision_authority":True,"architecture":"PROFESSIONAL_THESIS_REASONING","analysis_complete":True,"direction":d,"evidence_alignment":alignment,"thesis_quality":thesis,"professional_reasoning":{"question":"Is there a clear, asymmetric, confirmed opportunity worth risking capital on now?","primary_thesis":d,"alternative_thesis":"Opposite direction only if primary structure/setup thesis fails","invalidation":"; ".join(inv) if inv else "Structural/setup/confirmation premise failure","dimensions":dims,"conflicts":conf,"hard_invalidations":inv,"execution_ready":ready},"decision_reasons":sorted(set(reasons)),"evidence_conflicts":conf,"hard_invalidations":inv,"trade_plan":plan if isinstance(plan,dict) else {},"gate":ready,"upstream_gates_ignored":True,"gate_semantics":"E9_MASTER_ONLY","learning_policy":"ADVISORY_ONLY_NO_OVERRIDE","professional_decision":"APPROVE_TRADE" if ready else "NO_TRADE"}
    advisory=build_advisory(context,historical_calibration) if historical_calibration is not None else None
    out["historical_calibration"]=advisory
    return EngineResult("E9",ENGINE_NAMES.get("E9","Master Decision Brain"),ready,thesis,out,tuple(sorted(set(reasons))))
