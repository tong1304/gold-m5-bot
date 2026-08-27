from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Setup Brain"
QUESTION="What setup is forming, in what direction, and at what stage?"
MIN_BARS=40

def _ema(v,p):
    a=2/(p+1); x=v[0]
    for z in v[1:]: x=a*z+(1-a)*x
    return x

def analyze_e6(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or []); base={"question":QUESTION,"reasoning_role":"SETUP_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<MIN_BARS:return EngineResult("E6",NAME,None,0,{**base,"state":"WAIT","setup":"NONE","direction":"NEUTRAL","maturity":"UNRESOLVED","supporting_evidence":[],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"missing_evidence":["sufficient price history"],"invalidation":["new closed candle"]},("INSUFFICIENT_DATA",))
    c=[float(x["close"]) for x in bars]; h=[float(x["high"]) for x in bars]; l=[float(x["low"]) for x in bars]; atr=max(mean(float(x["high"])-float(x["low"]) for x in bars[-14:]),1e-9); price=c[-1]; e20=_ema(c,20); e50=_ema(c,50)
    e1=(upstream.get("E1").output if upstream.get("E1") else {}); e2=(upstream.get("E2").output if upstream.get("E2") else {}); e3=(upstream.get("E3").output if upstream.get("E3") else {}); e5=(upstream.get("E5").output if upstream.get("E5") else {})
    state=str(e1.get("market_state","UNCLEAR")).upper(); pressure=str(e1.get("directional_pressure","NONE")).upper(); opp=str(e2.get("thesis",e2.get("finding",""))).upper(); struct=str(e3.get("finding","" )).upper(); loc=str(e5.get("finding",e5.get("location_state",""))).upper()
    buy=max(0,(state=="TREND_UP"),(pressure=="UP"),(price>e20>e50),("UP" in struct)); sell=max(0,(state=="TREND_DOWN"),(pressure=="DOWN"),(price<e20<e50),("DOWN" in struct))
    direction="BUY" if buy>sell else "SELL" if sell>buy else "NEUTRAL"
    body=abs(c[-1]-float(bars[-1]["open"])); impulse=body>=.65*atr; prior_hi=max(h[-11:-1]); prior_lo=min(l[-11:-1]); breakout=(direction=="BUY" and price>prior_hi) or (direction=="SELL" and price<prior_lo); pullback=abs(price-e20)<=.75*atr
    setup="BREAKOUT" if breakout else "TREND_PULLBACK" if direction in {"BUY","SELL"} and pullback else "IMPULSE_CONTINUATION" if impulse else "NONE"
    counter=[]; missing=[]
    if direction=="NEUTRAL": counter.append("DIRECTIONAL_THESIS_CONFLICT")
    if "MIXED" in struct: counter.append("STRUCTURE_MIXED")
    if loc in {"SPACE_CONSTRAINED","ADVERSE"}: counter.append("LOCATION_CONSTRAINED")
    if setup=="NONE": missing.append("clear_setup_pattern")
    if setup in {"TREND_PULLBACK","IMPULSE_CONTINUATION"} and not impulse: missing.append("continuation_impulse")
    maturity="MATURE" if setup!="NONE" and direction!="NEUTRAL" and not counter else "DEVELOPING" if setup!="NONE" and direction!="NEUTRAL" else "UNRESOLVED"
    gate=maturity=="MATURE"; score=min(100,30+20*(buy+sell)+20*(setup!="NONE")+10*(maturity=="MATURE"))
    return EngineResult("E6",NAME,gate,score,{**base,"state":maturity,"setup":setup,"direction":direction,"maturity":maturity,"supporting_evidence":[f"E1_state={state}",f"E1_pressure={pressure}",f"E2_thesis={opp}",f"E3_structure={struct}",f"impulse={impulse}",f"breakout={breakout}",f"pullback={pullback}"],"counter_evidence":counter,"missing_evidence":missing,"invalidation":["directional evidence reverses","setup structure breaks","location becomes materially constrained","closed candle invalidates setup"]},() if gate else tuple(counter or missing or ["SETUP_NOT_MATURE"]))
