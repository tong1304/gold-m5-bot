from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Confirmation / Trigger Brain"
QUESTION="Is the setup thesis confirmed by a closed-candle trigger?"


def analyze_e7(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or []); e6=upstream.get("E6"); e4=upstream.get("E4")
    base={"question":QUESTION,"reasoning_role":"CONFIRMATION_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<5 or not e6:return EngineResult("E7",NAME,False,0.0,{**base,"state":"WAIT","confirmation":"NOT_CONFIRMED","evidence":[],"counter_evidence":["MISSING_SETUP"],"invalidation":["new closed candle"]},("MISSING_SETUP",))
    o=e6.output; direction=str(o.get("direction","NEUTRAL")).upper(); b=bars[-1]; p=bars[-2]
    op,hi,lo,cl=[float(b[k]) for k in ("open","high","low","close")]; prev=float(p["close"]); rng=max(hi-lo,1e-9); body=abs(cl-op); close_pos=(cl-lo)/rng
    atr=mean(float(x["high"])-float(x["low"]) for x in bars[-14:]); impulse=body>=.55*max(atr,1e-9)
    bullish=cl>op and cl>prev and close_pos>=.65; bearish=cl<op and cl<prev and close_pos<=.35
    trigger=(direction=="BUY" and bullish) or (direction=="SELL" and bearish)
    liquidity_conflict=False
    if e4:
        e4dir=str(e4.output.get("direction","NEUTRAL")).upper()
        liquidity_conflict=e4dir in {"UP","DOWN"} and ((direction=="BUY" and e4dir=="DOWN") or (direction=="SELL" and e4dir=="UP"))
    evidence=[f"direction={direction}",f"closed_candle_trigger={trigger}",f"impulse={impulse}",f"close_position={close_pos:.3f}"]
    counter=[]
    if direction not in {"BUY","SELL"}:counter.append("SETUP_DIRECTION_UNRESOLVED")
    if not trigger:counter.append("TRIGGER_NOT_CONFIRMED")
    if liquidity_conflict:counter.append("LIQUIDITY_DIRECTION_CONFLICT")
    confirmed=bool(e6.gate_passed and trigger and not liquidity_conflict)
    return EngineResult("E7",NAME,confirmed,85.0 if confirmed else 35.0,{**base,"state":"CONFIRMED" if confirmed else "WAIT","confirmation":"CONFIRMED" if confirmed else "NOT_CONFIRMED","trigger_observed":trigger,"direction":direction,"atr":atr,"candle_body":body,"close_position":close_pos,"evidence":evidence,"counter_evidence":counter,"invalidation":["trigger candle is invalidated by subsequent closed-candle evidence","liquidity/structure evidence materially contradicts trigger"]},() if confirmed else tuple(counter or ["TRIGGER_NOT_CONFIRMED"]))
