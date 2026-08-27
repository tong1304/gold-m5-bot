from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Confirmation / Trigger Brain"
QUESTION="Does the setup have a valid closed-candle confirmation, or what is still missing?"


def _atr(bars, p=14):
    if len(bars) < 2:
        return 0.0
    return mean(max(float(bars[i]["high"])-float(bars[i]["low"]), abs(float(bars[i]["high"])-float(bars[i-1]["close"])), abs(float(bars[i]["low"])-float(bars[i-1]["close"]))) for i in range(max(1, len(bars)-p), len(bars)))


def analyze_e7(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or []); e6=upstream.get("E6"); e4=upstream.get("E4")
    base={"question":QUESTION,"reasoning_role":"CONFIRMATION_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<5 or not e6:
        return EngineResult("E7",NAME,None,0,{**base,"state":"WAIT","confirmation":"UNRESOLVED","trigger_status":"NOT_EVALUATED","direction":"NEUTRAL","trigger_observed":False,"supporting_evidence":[],"counter_evidence":["MISSING_SETUP_CONTEXT"],"missing_evidence":["closed-candle confirmation"],"invalidation":["new closed candle"]},("INSUFFICIENT_CONTEXT",))

    o=e6.output; direction=str(o.get("direction","NEUTRAL")).upper(); setup=str(o.get("setup","NONE")).upper(); b=bars[-1]; p=bars[-2]
    op,hi,lo,cl=[float(b[k]) for k in ("open","high","low","close")]
    prev_open,prev_high,prev_low,prev_close=[float(p[k]) for k in ("open","high","low","close")]
    prev=float(p["close"]); rng=max(hi-lo,1e-9); body=abs(cl-op); atr=max(_atr(bars),1e-9); pos=(cl-lo)/rng

    bullish=cl>op and cl>prev and pos>=.65
    bearish=cl<op and cl<prev and pos<=.35
    impulse=body>=.55*atr
    engulf_bull=op<=prev_close and cl>=prev_open and cl>op
    engulf_bear=op>=prev_close and cl<=prev_open and cl<op
    trigger=(direction=="BUY" and (bullish or engulf_bull)) or (direction=="SELL" and (bearish or engulf_bear))

    e4o=e4.output if e4 else {}
    e4dir=str(e4o.get("direction","NEUTRAL")).upper()
    liquidity_conflict=e4dir in {"UP","DOWN"} and ((direction=="BUY" and e4dir=="DOWN") or (direction=="SELL" and e4dir=="UP"))

    counter=[]; missing=[]
    if direction not in {"BUY","SELL"}: counter.append("SETUP_DIRECTION_UNRESOLVED")
    if liquidity_conflict: counter.append("LIQUIDITY_DIRECTION_CONFLICT")
    if direction in {"BUY","SELL"} and not trigger: missing.append("VALID_CLOSED_CANDLE_TRIGGER")

    if direction not in {"BUY","SELL"}:
        confirmation="UNRESOLVED"; trigger_status="NOT_EVALUATED"
    elif liquidity_conflict:
        confirmation="INVALIDATED"; trigger_status="CONFLICTED"
    elif trigger:
        confirmation="CONFIRMED"; trigger_status="CONFIRMED"
    else:
        confirmation="DEVELOPING"; trigger_status="NOT_CONFIRMED"

    gate=confirmation=="CONFIRMED" and trigger_status=="CONFIRMED"
    score=85 if gate else 50 if confirmation=="DEVELOPING" else 25
    reasons=() if gate else tuple(counter+missing or ["CONFIRMATION_NOT_PROVEN"])
    return EngineResult("E7",NAME,gate,score,{**base,"state":confirmation,"confirmation":confirmation,"trigger_status":trigger_status,"direction":direction,"setup":setup,"trigger_observed":trigger,"trigger_type":"BULLISH_CLOSE" if direction=="BUY" and trigger else "BEARISH_CLOSE" if direction=="SELL" and trigger else "NONE","impulse":impulse,"close_position":pos,"candle_body":body,"candle_range":rng,"supporting_evidence":[f"setup={setup}",f"direction={direction}",f"closed_candle_trigger={trigger}",f"impulse={impulse}",f"bullish_close={bullish}",f"bearish_close={bearish}",f"engulf_bull={engulf_bull}",f"engulf_bear={engulf_bear}"],"counter_evidence":list(dict.fromkeys(counter)),"missing_evidence":missing,"invalidation":["closed candle invalidates trigger","liquidity or structure materially contradicts confirmation"]},reasons)
