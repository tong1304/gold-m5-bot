from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Trade Economics Brain"

def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars=list(snapshot.get("bars") or [])
    e6=upstream.get("E6"); e7=upstream.get("E7")
    if len(bars)<20 or not e6 or not e7:
        return EngineResult("E8",NAME,False,0.0,{"question":"Is the trade economically attractive?","risk_gate":"NOT_READY","trade_plan":{}},("INSUFFICIENT_UPSTREAM_EVIDENCE",))
    closes=[float(x["close"]) for x in bars]; highs=[float(x["high"]) for x in bars]; lows=[float(x["low"]) for x in bars]
    atr=mean([float(x["high"])-float(x["low"]) for x in bars[-14:]])
    price=closes[-1]; direction=str(e6.output.get("direction","NEUTRAL"))
    if direction not in {"BUY","SELL"} or not bool(e6.gate_passed) or not bool(e7.gate_passed):
        return EngineResult("E8",NAME,False,20.0,{"question":"Is the trade economically attractive?","risk_gate":"NOT_READY","trade_plan":{},"direction":direction,"atr":atr},("UPSTREAM_NOT_READY",))
    recent_high=max(highs[-20:]); recent_low=min(lows[-20:]); risk=max(atr,1e-9)
    if direction=="BUY": stop=min(recent_low,price-1.2*risk); target1=price+1.5*risk; target2=price+2.4*risk
    else: stop=max(recent_high,price+1.2*risk); target1=price-1.5*risk; target2=price-2.4*risk
    rr=abs(target2-price)/max(abs(price-stop),1e-9); ready=rr>=1.5
    plan={"valid":ready,"entry":price,"stop_loss":stop,"take_profit_1":target1,"take_profit_2":target2,"rr_tp2":rr}
    return EngineResult("E8",NAME,ready,min(100.0,70.0+20.0*min(rr/2.0,1.0)),{
        "question":"Is the trade economically attractive?","risk_gate":"RISK_READY" if ready else "RISK_NOT_READY","direction":direction,
        "atr":atr,"trade_plan":plan,"risk_basis":"ATR_STRUCTURE","reasoning_role":"TRADE_ECONOMICS_ANALYST","decision_authority":"E9"
    },() if ready else ("RR_BELOW_MINIMUM",))
