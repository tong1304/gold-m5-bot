from __future__ import annotations

from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Setup Brain"
QUESTION="What setup is forming?"
MIN_BARS=40


def _ema(values,period):
    if not values:return 0.0
    a=2/(period+1); x=values[0]
    for v in values[1:]:x=a*v+(1-a)*x
    return x


def analyze_e6(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or []); e1=upstream.get("E1"); e2=upstream.get("E2"); e3=upstream.get("E3"); e4=upstream.get("E4"); e5=upstream.get("E5")
    base={"question":QUESTION,"reasoning_role":"SETUP_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<MIN_BARS:return EngineResult("E6",NAME,False,0.0,{**base,"state":"UNRESOLVED","setup":"NONE","maturity":"UNRESOLVED","evidence":[],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"invalidation":["new closed candle"]},("INSUFFICIENT_DATA",))
    closes=[float(b["close"]) for b in bars]; highs=[float(b["high"]) for b in bars]; lows=[float(b["low"]) for b in bars]
    atr=mean(float(b["high"])-float(b["low"]) for b in bars[-14:]); price=closes[-1]; ema20=_ema(closes,20); ema50=_ema(closes,50)
    state=str((e1.output if e1 else {}).get("market_state","UNCLEAR")); opportunity=str((e2.output if e2 else {}).get("finding","")).upper(); structure=str((e3.output if e3 else {}).get("finding","")).upper()
    direction="BUY" if state=="TREND_UP" else "SELL" if state=="TREND_DOWN" else "NEUTRAL"
    if direction=="NEUTRAL" and price>ema20>ema50:direction="BUY"
    elif direction=="NEUTRAL" and price<ema20<ema50:direction="SELL"
    body=abs(closes[-1]-float(bars[-1]["open"])); impulse=body>=max(.65*atr,1e-9)
    prior_hi=max(highs[-11:-1]); prior_lo=min(lows[-11:-1]); breakout=(direction=="BUY" and price>prior_hi) or (direction=="SELL" and price<prior_lo)
    pullback=(direction=="BUY" and abs(price-ema20)<=.60*atr) or (direction=="SELL" and abs(price-ema20)<=.60*atr)
    location_ok=True
    if e5: location_ok=str(e5.output.get("finding",e5.output.get("location_state",""))).upper() not in {"SPACE_CONSTRAINED","ADVERSE"}
    setup_type="TREND_PULLBACK" if direction in {"BUY","SELL"} and pullback and location_ok else "BREAKOUT" if direction in {"BUY","SELL"} and breakout else "IMPULSE" if direction in {"BUY","SELL"} and impulse and location_ok else "NONE"
    evidence=[f"direction={direction}",f"state={state}",f"impulse={impulse}",f"pullback={pullback}",f"breakout={breakout}",f"location_ok={location_ok}"]
    counter=[]
    if state in {"UNCLEAR","TRANSITION","RANGE","COMPRESSION"}:counter.append("REGIME_NOT_DIRECTIONALLY_CLEAR")
    if not location_ok:counter.append("LOCATION_NOT_ADVANTAGEOUS")
    if structure and "MIXED" in structure:counter.append("STRUCTURE_MIXED")
    mature=setup_type!="NONE" and not counter
    return EngineResult("E6",NAME,mature,80.0 if mature else 30.0,{**base,"state":"MATURE" if mature else "UNRESOLVED","setup":setup_type,"maturity":"MATURE" if mature else "UNRESOLVED","direction":direction,"atr":atr,"evidence":evidence,"counter_evidence":counter,"invalidation":["setup loses directional structure","location becomes constrained","new closed candle invalidates pattern"]},() if mature else tuple(counter or ["NO_CLEAR_SETUP"]))
