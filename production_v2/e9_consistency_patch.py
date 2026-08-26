"""Final E9 evidence-consistency guard for production-v2."""
from __future__ import annotations
import re
from typing import Any
from .contracts import EngineResult
DIRECTIONS={"BUY","SELL"}

def _tokens(value:Any)->set[str]:
    out=set()
    def rec(v):
        if isinstance(v,dict):
            for k,x in v.items(): out.add(str(k).upper()); rec(x)
        elif isinstance(v,(list,tuple,set)):
            for x in v: rec(x)
        elif v is not None:
            out.update(re.findall(r"(?<![A-Z0-9_])[A-Z][A-Z0-9_]*(?![A-Z0-9_])",str(v).upper()))
    rec(value); return out

def _explicit_direction(engine):
    if not engine:return None
    found=[]
    def rec(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if str(k).lower() in {"direction","bias","orientation","market_direction"}:
                    s=str(x).upper().strip()
                    if s in DIRECTIONS: found.append(s)
                    elif s in {"UP","BULLISH","LONG","TREND_UP"}: found.append("BUY")
                    elif s in {"DOWN","BEARISH","SHORT","TREND_DOWN"}: found.append("SELL")
                rec(x)
        elif isinstance(v,(list,tuple,set)):
            for x in v: rec(x)
    rec(engine.output)
    return found[0] if found and len(set(found))==1 else None

def _strict_setup(e6):
    t=_tokens(e6.output if e6 else {})
    if {"QUALITY_WEAK","DEVELOPING"}&t:return "DEVELOPING",False
    if {"INVALIDATED","SETUP_INVALIDATED","HARD_INVALIDATION"}&t:return "INVALIDATED",False
    if "MATURE" in t:return "MATURE",True
    if {"VALID_SETUP","CONTINUATION_SETUP","REVERSAL_SETUP","SETUP_FORMING"}&t:return "FORMING",False
    return "UNRESOLVED",False

def _strict_confirmation(e7):
    t=_tokens(e7.output if e7 else {})
    if {"NO_TRIGGER","NO_FOLLOW_THROUGH","WAIT","CONFIRMATION_WAIT","TRIGGER_NOT_OBSERVED","CONFIRMATION_NOT_PROVEN","QUALITY_NOT_PROVEN"}&t:return "WAIT",False
    if {"CONFIRMATION_PASS","CONFIRMED","FOLLOW_THROUGH_OBSERVED","TRIGGER_OBSERVED"}&t:return "CONFIRMED",True
    return "UNRESOLVED",False

def install():
    from . import professional_brain as brain
    original=brain.run_professional_e9
    if getattr(original,"_consistency_guard",False):return
    def guarded(context,upstream,historical_calibration=None):
        result=original(context,upstream,historical_calibration)
        by={e.engine_id:e for e in upstream}
        ds=[_explicit_direction(by.get(k)) for k in ("E1","E2","E3","E4","E5","E6","E7")]
        ds=[d for d in ds if d in DIRECTIONS]
        direction="BUY" if ds.count("BUY")>ds.count("SELL") else "SELL" if ds.count("SELL")>ds.count("BUY") else "NEUTRAL"
        setup_state,setup_ok=_strict_setup(by.get("E6"))
        confirmation_state,confirmation_ok=_strict_confirmation(by.get("E7"))
        output=dict(result.output or {})
        reasoning=dict(output.get("professional_reasoning") or {})
        reasons=set(result.reason_codes)
        if direction=="NEUTRAL":reasons.add("DIRECTIONAL_THESIS_UNRESOLVED")
        if not setup_ok:reasons.add("SETUP_NOT_MATURE")
        if not confirmation_ok:reasons.add("ENTRY_CONFIRMATION_NOT_PROVEN")
        execution_ready=bool(reasoning.get("execution_ready"))
        ready=bool(direction in DIRECTIONS and setup_ok and confirmation_ok and execution_ready and result.gate_passed)
        decision=direction if ready else "NO_TRADE"
        output.update({"decision":decision,"direction":direction,"gate":ready,"trade_decision_authority":True,"decision_authority":"E9","decision_score":result.score if ready else 0.0,"professional_decision":"APPROVE_TRADE" if ready else "NO_TRADE","decision_reasons":sorted(reasons)})
        reasoning.update({"primary_thesis":direction,"setup_state":setup_state,"setup_mature":setup_ok,"confirmation_state":confirmation_state,"confirmation_ready":confirmation_ok,"execution_ready":execution_ready,"decision_authority":"E9","direction_source":"EXPLICIT_SPECIALIST_DIRECTION_ONLY_E1_TO_E7"})
        output["professional_reasoning"]=reasoning
        return EngineResult("E9",result.name,ready,result.score if ready else 0.0,output,tuple(sorted(reasons)))
    guarded._consistency_guard=True
    brain.run_professional_e9=guarded
install()
