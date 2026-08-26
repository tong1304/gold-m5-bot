from __future__ import annotations

import re
from statistics import mean
from typing import Any

from .contracts import EngineResult
from .e9_learning import build_advisory
from .engines import ENGINE_NAMES, run_engine as _engine_analyzer

SPECIALIST_QUESTIONS={"E1":"What market state is present right now?","E2":"What opportunity/regime is the market offering?","E3":"What does market structure say?","E4":"Where is liquidity and what did price do with it?","E5":"Is current price in an advantageous location?","E6":"What setup, if any, is forming?","E7":"Is the setup thesis confirmed by price action?","E8":"What are the trade economics, invalidation and asymmetry?"}
EVIDENCE_WEIGHTS={"E1":1.0,"E2":1.0,"E3":1.2,"E4":1.15,"E5":1.1,"E6":1.2,"E7":1.3,"E8":1.25}; DIRECTIONS={"BUY","SELL"}

def run_professional_engine(engine_id:str,context:dict[str,Any])->EngineResult:
    raw=_engine_analyzer(engine_id,dict(context));o=dict(raw.output);o.update({"analysis_status":"COMPLETE","analysis_complete":True,"specialist_question":SPECIALIST_QUESTIONS.get(engine_id),"trade_decision_authority":False,"specialist_gate":"NONE","gate":None,"reasoning_role":"SPECIALIST_EVIDENCE"});return EngineResult(raw.engine_id,raw.name,None,raw.score,o,raw.reason_codes)

def _clamp(v:float,lo=0.0,hi=100.0)->float:return max(lo,min(hi,float(v)))
def _text(v:Any)->str:return str(v).upper()
def _has(blob:str,*terms:str)->bool:return any(t in blob for t in terms)
def _walk(v:Any):
    if isinstance(v,dict):
        for k,x in v.items():yield str(k);yield from _walk(x)
    elif isinstance(v,(list,tuple,set)):
        for x in v:yield from _walk(x)
    else:yield str(v)
def _blob(e:EngineResult|None)->str:return " | ".join(_text(x) for x in _walk(e.output)) if e else ""
def _exact(e:EngineResult|None,token:str)->bool:return bool(re.search(rf"(?<![A-Z0-9_]){re.escape(token)}(?![A-Z0-9_])",_blob(e)))

def _find_key(v:Any,keys:set[str]):
    if isinstance(v,dict):
        for k,x in v.items():
            if str(k).lower() in keys:return x
            found=_find_key(x,keys)
            if found is not None:return found
    elif isinstance(v,(list,tuple,set)):
        for x in v:
            found=_find_key(x,keys)
            if found is not None:return found
    return None

def _state_values(e:EngineResult|None)->set[str]:
    if not e:return set()
    vals=set()
    def rec(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if str(k).lower() in {"state","direction","bias","orientation","market_direction","classification","regime","setup","confirmation","risk_gate","phase"} and isinstance(x,(str,int,float,bool)):vals.add(_text(x).strip())
                rec(x)
        elif isinstance(v,(list,tuple,set)):
            for x in v:rec(x)
    rec(e.output);return vals

def _direction_hints(e:EngineResult|None)->set[str]:
    states=_state_values(e);hints=set();blob=_blob(e)
    for s in states:
        if s in {"UP","BULLISH","LONG","BUY","TREND_UP","BULLISH_BOS","STRUCTURAL_DISCOUNT","LIQUIDITY_ABOVE"}:hints.add("BUY")
        if s in {"DOWN","BEARISH","SHORT","SELL","TREND_DOWN","BEARISH_BOS","STRUCTURAL_PREMIUM","LIQUIDITY_BELOW"}:hints.add("SELL")
    if re.search(r"TREND[_ ]?UP|DIRECTION\s*[=:]\s*UP|STRUCTURE\s*[=:]\s*UP|BULLISH",blob):hints.add("BUY")
    if re.search(r"TREND[_ ]?DOWN|DIRECTION\s*[=:]\s*DOWN|STRUCTURE\s*[=:]\s*DOWN|BEARISH",blob):hints.add("SELL")
    return hints

def _structured_direction(e:EngineResult|None)->str|None:
    if not e:return None
    v=_find_key(e.output,{"direction","bias","orientation","market_direction"})
    if isinstance(v,str):
        x=_text(v).strip()
        if x in DIRECTIONS:return x
        if x in {"BULLISH","UP","LONG","TREND_UP"}:return "BUY"
        if x in {"BEARISH","DOWN","SHORT","TREND_DOWN"}:return "SELL"
    hints=_direction_hints(e);return next(iter(hints)) if len(hints)==1 else None

def _direction(evidence:dict[str,EngineResult])->str:
    buy=sell=0.0
    for e in evidence.values():
        hints=_direction_hints(e);w=EVIDENCE_WEIGHTS.get(e.engine_id,1.0)
        if len(hints)==1:
            if "BUY" in hints:buy+=w
            else:sell+=w
        else:
            d=_structured_direction(e)
            if d=="BUY":buy+=w
            elif d=="SELL":sell+=w
    return "BUY" if buy>sell else "SELL" if sell>buy else "NEUTRAL"

def _weighted_alignment(upstream:list[EngineResult])->float:
    w=[EVIDENCE_WEIGHTS.get(e.engine_id,1.0) for e in upstream];return round(sum(_clamp(e.score)*x for e,x in zip(upstream,w))/sum(w),2) if w else 0.0

def _dimension_state(by):
    b={k:_blob(by.get(k)) for k in SPECIALIST_QUESTIONS};s={k:_state_values(by.get(k)) for k in SPECIALIST_QUESTIONS}
    return {"market_context":bool(b["E1"] or b["E2"]),"structure_support":bool(s["E3"]&{"BULLISH","BEARISH","ALIGNED","STRONG","MODERATE"}) or _has(b["E3"],"BOS","BREAK_OF_STRUCTURE","HIGHER_HIGH","LOWER_LOW"),"liquidity_event":bool(s["E4"]&{"SWEEP_HIGH","SWEEP_LOW","REJECTION","ACCEPTANCE","RECLAIM","HIGH_QUALITY"}) or _has(b["E4"],"SWEEP","RECLAIM","REJECTION","LIQUIDITY"),"location_quality":bool(s["E5"]&{"LOCATION_QUALITY_PASS","DISCOUNT","PREMIUM","EQUILIBRIUM","SPACE_AVAILABLE"}) or _has(b["E5"],"ADVANTAGEOUS","FAVORABLE","DISCOUNT","PREMIUM","GOOD_LOCATION"),"setup_mature":bool(s["E6"]&{"MATURE"}) or _has(b["E6"],"MATURE","VALID_SETUP","CONTINUATION_SETUP","REVERSAL_SETUP"),"confirmation":bool(s["E7"]&{"CONFIRMATION_PASS","CONFIRMED","FOLLOW_THROUGH_OBSERVED","TRIGGER_OBSERVED"}) or _has(b["E7"],"CONFIRMED","CONFIRMATION_PASS","TRIGGER_OBSERVED","FOLLOW_THROUGH"),"economics":bool(s["E8"]&{"RISK_READY","RR_OK","POSITIVE_EXPECTANCY","ATTRACTIVE"}) or _has(b["E8"],"ATTRACTIVE","RISK_GATE_READY","RR_OK","POSITIVE_EXPECTANCY")}

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

def _atr_from_context(context:dict[str,Any])->float:
    bars=[b for b in (context.get("bars") or []) if isinstance(b,dict) and all(k in b for k in ("high","low","close"))][-14:]
    if not bars:return 0.0
    trs=[];prev=None
    for b in bars:
        h,l,c=map(float,(b["high"],b["low"],b["close"]));trs.append(h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev)));prev=c
    return mean(trs) if trs else 0.0

def _derive_trade_plan(context:dict[str,Any],direction:str)->dict[str,Any]|None:
    bars=[b for b in (context.get("bars") or []) if isinstance(b,dict) and all(k in b for k in ("high","low","close"))]
    if len(bars)<20 or direction not in DIRECTIONS:return None
    atr=_atr_from_context(context)
    if atr<=0:return None
    price=float(bars[-1]["close"]);recent=bars[-20:]
    swing_low=min(float(b["low"]) for b in recent);swing_high=max(float(b["high"]) for b in recent)
    buffer=.15*atr
    if direction=="BUY":
        stop=min(swing_low,price-atr)-buffer
        risk=price-stop
        if risk<=0:return None
        tp1=price+1.0*risk;tp2=price+1.5*risk
    else:
        stop=max(swing_high,price+atr)+buffer
        risk=stop-price
        if risk<=0:return None
        tp1=price-1.0*risk;tp2=price-1.5*risk
    return {"valid":True,"direction":direction,"entry":price,"stop_loss":stop,"take_profit_1":tp1,"take_profit_2":tp2,"rr_tp2":1.5,"risk_distance":risk,"source":"E9_DERIVED_FROM_CLOSED_M5_EVIDENCE","calculated_at_closed_candle":True}

def _execution_readiness(context,by,direction):
    if direction not in DIRECTIONS:return {"ready":False,"reasons":["NO_ACTIONABLE_DIRECTION"],"plan":None}
    e8=by.get("E8")
    if not e8:return {"ready":False,"reasons":["E8_MISSING"],"plan":None}
    o=e8.output or {};p=_find_key(o,{"trade_plan"})
    if isinstance(p,dict):
        required=("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2")
        if all(p.get(k) is not None for k in required):
            try:
                if float(p["rr_tp2"])>0:return {"ready":True,"reasons":[],"plan":p}
            except (TypeError,ValueError):pass
    risk_ready=bool(_state_values(e8)&{"RISK_READY"}) or _has(_blob(e8),"RISK_READY")
    if not risk_ready:return {"ready":False,"reasons":["E8_RISK_NOT_READY"],"plan":None}
    plan=_derive_trade_plan(context,direction)
    return {"ready":bool(plan),"reasons":[] if plan else ["E9_CANNOT_DERIVE_EXECUTION_PLAN"],"plan":plan}

def run_professional_e9(context,upstream,historical_calibration=None):
    by={e.engine_id:e for e in upstream};d=_direction(by);dims=_dimension_state(by);conf=_conflicts(by);inv=_hard_invalidations(by);alignment=_weighted_alignment(upstream)
    thesis=round(_clamp(alignment+sum(3.5 for k in ("structure_support","liquidity_event","location_quality","setup_mature","confirmation","economics") if dims[k])-min(24.0,len(conf)*8.0)),2) if d!="NEUTRAL" else 0.0
    execution=_execution_readiness(context,by,d);reasons=list(inv)+list(conf)
    if d=="NEUTRAL":reasons.append("DIRECTIONAL_THESIS_UNRESOLVED")
    if not dims["setup_mature"]:reasons.append("SETUP_NOT_MATURE")
    if not dims["confirmation"]:reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not dims["economics"]:reasons.append("TRADE_ECONOMICS_NOT_READY")
    reasons.extend(execution["reasons"])
    ready=(d in DIRECTIONS and execution["ready"] and dims["setup_mature"] and dims["confirmation"] and dims["economics"] and thesis>=70 and not conf and not inv)
    decision=d if ready else "NO_TRADE";plan=execution["plan"] or {}
    out={"decision":decision,"decision_authority":"E9","trade_decision_authority":True,"architecture":"PROFESSIONAL_THESIS_REASONING","analysis_complete":True,"direction":d,"evidence_alignment":alignment,"thesis_quality":thesis,"professional_reasoning":{"question":"Is there a clear, asymmetric, confirmed opportunity worth risking capital on now?","primary_thesis":d,"alternative_thesis":"Opposite direction only if primary structure/setup thesis fails","invalidation":"; ".join(inv) if inv else "Structural/setup/confirmation premise failure","dimensions":dims,"conflicts":conf,"hard_invalidations":inv,"execution_ready":ready,"directional_evidence":{"BUY":sum(EVIDENCE_WEIGHTS.get(e.engine_id,1.0) for e in by.values() if "BUY" in _direction_hints(e)),"SELL":sum(EVIDENCE_WEIGHTS.get(e.engine_id,1.0) for e in by.values() if "SELL" in _direction_hints(e))}},"decision_reasons":sorted(set(reasons)),"evidence_conflicts":conf,"hard_invalidations":inv,"trade_plan":plan,"gate":ready,"upstream_gates_ignored":True,"gate_semantics":"E9_MASTER_ONLY","learning_policy":"ADVISORY_ONLY_NO_OVERRIDE","professional_decision":"APPROVE_TRADE" if ready else "NO_TRADE"}
    out["historical_calibration"]=build_advisory(context,historical_calibration) if historical_calibration is not None else None
    return EngineResult("E9",ENGINE_NAMES.get("E9","Master Decision Brain"),ready,thesis,out,tuple(sorted(set(reasons))))
