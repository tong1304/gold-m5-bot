from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Trade Economics & Risk Brain"
QUESTION="Is the proposed trade economically attractive and structurally survivable?"
MIN_BARS=30
MIN_RR=1.50

def _atr(bars,p=14):
    if len(bars)<2:return 0.0
    return mean(max(float(bars[i]["high"])-float(bars[i]["low"]),abs(float(bars[i]["high"])-float(bars[i-1]["close"])),abs(float(bars[i]["low"])-float(bars[i-1]["close"]))) for i in range(max(1,len(bars)-p),len(bars)))

def analyze_e8(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or []); e5=upstream.get("E5"); e6=upstream.get("E6"); e7=upstream.get("E7"); base={"question":QUESTION,"reasoning_role":"TRADE_ECONOMICS_RISK_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<MIN_BARS:return EngineResult("E8",NAME,None,0,{**base,"state":"WAIT","economic_state":"UNRESOLVED","trade_plan":{},"supporting_evidence":[],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"missing_evidence":["sufficient risk sample"],"invalidation":["new closed candle"]},("INSUFFICIENT_DATA",))
    d=str((e6.output if e6 else {}).get("direction","NEUTRAL")).upper(); setup=str((e6.output if e6 else {}).get("setup","NONE")); conf=str((e7.output if e7 else {}).get("confirmation","UNRESOLVED")).upper(); atr=max(_atr(bars),1e-9); price=float(bars[-1]["close"]); hi=max(float(x["high"]) for x in bars[-20:]); lo=min(float(x["low"]) for x in bars[-20:])
    counter=[]; missing=[]
    if d not in {"BUY","SELL"}:counter.append("NO_VALID_DIRECTION")
    if conf!="CONFIRMED":missing.append("ENTRY_CONFIRMATION")
    if d=="BUY": stop=min(lo,price-1.2*atr); risk=price-stop; t1=price+1.5*risk; t2=price+2*risk
    elif d=="SELL": stop=max(hi,price+1.2*atr); risk=stop-price; t1=price-1.5*risk; t2=price-2*risk
    else: stop=risk=t1=t2=None
    plan={}
    if risk:
        rr=abs(t2-price)/risk; space_to_structure=abs((hi if d=="BUY" else lo)-price); asym=space_to_structure/risk
        plan={"valid":rr>=MIN_RR and asym>=1.0,"entry":price,"stop_loss":stop,"take_profit_1":t1,"take_profit_2":t2,"risk_distance":risk,"rr_tp2":rr,"structural_space_r":asym,"rr_minimum":MIN_RR}
        if rr<MIN_RR:counter.append("RR_BELOW_MINIMUM")
        if asym<1.0:counter.append("STRUCTURAL_SPACE_INSUFFICIENT")
    if e5 and "SPACE_CONSTRAINED" in str(e5.output.get("finding","")).upper():counter.append("LOCATION_SPACE_CONSTRAINED")
    economic="ATTRACTIVE" if plan.get("valid") and not counter else "CONDITIONAL" if plan and not any(x in counter for x in ("RR_BELOW_MINIMUM","STRUCTURAL_SPACE_INSUFFICIENT")) else "UNATTRACTIVE" if plan else "UNRESOLVED"
    gate=economic=="ATTRACTIVE" and conf=="CONFIRMED" and d in {"BUY","SELL"}; score=90 if gate else 60 if economic=="CONDITIONAL" else 30
    return EngineResult("E8",NAME,gate,score,{**base,"state":economic,"economic_state":economic,"direction":d,"setup":setup,"confirmation":conf,"trade_plan":plan,"supporting_evidence":[f"atr={atr:.6f}",f"rr_tp2={plan.get('rr_tp2','NA')}",f"structural_space_r={plan.get('structural_space_r','NA')}"],"counter_evidence":counter,"missing_evidence":missing,"invalidation":["RR falls below minimum","structural space collapses","stop becomes invalid","volatility changes materially"]},() if gate else tuple(counter+missing or ["ECONOMICS_NOT_READY"]))
