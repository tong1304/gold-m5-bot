from __future__ import annotations

from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Trade Economics & Risk Brain"
QUESTION="Is the trade economically attractive?"
MIN_BARS=30
MIN_RR=1.50


def _atr(bars, period=14):
    if len(bars)<2:return 0.0
    return mean(max(float(b["high"])-float(b["low"]),abs(float(b["high"])-float(bars[i-1]["close"])),abs(float(b["low"])-float(bars[i-1]["close"]))) for i,b in enumerate(bars[1:],1)[-period:])


def _price_levels(bars,direction,atr):
    price=float(bars[-1]["close"]); recent_high=max(float(b["high"]) for b in bars[-20:]); recent_low=min(float(b["low"]) for b in bars[-20:])
    if direction=="BUY":
        stop=min(recent_low,price-1.2*atr); risk=price-stop
        target1=price+1.5*risk; target2=price+2.0*risk
    else:
        stop=max(recent_high,price+1.2*atr); risk=stop-price
        target1=price-1.5*risk; target2=price-2.0*risk
    return price,stop,target1,target2,max(risk,1e-9)


def analyze_e8(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or []); e5=upstream.get("E5"); e6=upstream.get("E6"); e7=upstream.get("E7")
    base={"question":QUESTION,"reasoning_role":"TRADE_ECONOMICS_RISK_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<MIN_BARS:
        return EngineResult("E8",NAME,False,0.0,{**base,"risk_gate":"NOT_READY","trade_plan":{},"evidence":[],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"invalidation":["new risk data"]},("INSUFFICIENT_DATA",))
    direction=str((e6.output if e6 else {}).get("direction","NEUTRAL")).upper()
    evidence=[]; counter=[]
    if direction not in {"BUY","SELL"}: counter.append("NO_VALID_DIRECTION_FROM_SETUP")
    if not e6 or not e6.gate_passed or not e7 or not e7.gate_passed:
        counter.append("SETUP_OR_TRIGGER_NOT_CONFIRMED")
    if e5 and e5.output.get("location_state") in {"SPACE_CONSTRAINED","ADVERSE"}: counter.append("LOCATION_LIMITS_EXPECTED_PRICE_SPACE")
    if direction not in {"BUY","SELL"} or counter:
        return EngineResult("E8",NAME,False,20.0,{**base,"risk_gate":"NOT_READY","trade_plan":{},"direction":direction,"evidence":evidence,"counter_evidence":counter,"invalidation":["setup/trigger changes","structure changes","volatility regime changes"]},tuple(counter) or ("UPSTREAM_NOT_READY",))
    atr=_atr(bars); price,stop,t1,t2,risk=_price_levels(bars,direction,atr); rr=abs(t2-price)/risk
    plan={"valid":rr>=MIN_RR,"entry":price,"stop_loss":stop,"take_profit_1":t1,"take_profit_2":t2,"risk_distance":risk,"rr_tp2":rr,"rr_minimum":MIN_RR}
    evidence=[f"direction={direction}",f"atr14={atr:.6f}",f"risk_distance={risk:.6f}",f"rr_tp2={rr:.3f}"]
    if rr<MIN_RR: counter.append("RR_BELOW_MINIMUM")
    ready=not counter and plan["valid"]
    return EngineResult("E8",NAME,ready,min(100.0,50.0+50.0*min(rr/2.0,1.0)),{**base,"risk_gate":"RISK_READY" if ready else "RISK_NOT_READY","direction":direction,"atr":atr,"trade_plan":plan,"evidence":evidence,"counter_evidence":counter,"invalidation":["stop becomes structurally invalid","RR falls below minimum","volatility materially changes"]},() if ready else tuple(counter))
