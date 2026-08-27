from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Confirmation Brain"

def analyze_e7(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars=list(snapshot.get("bars") or [])
    e6=upstream.get("E6")
    if len(bars)<5 or not e6:
        return EngineResult("E7",NAME,False,0.0,{"question":"Is the setup thesis confirmed?","state":"WAIT","confirmation":"NOT_CONFIRMED"},("MISSING_SETUP",))
    b=bars[-1]; o=float(b["open"]); h=float(b["high"]); l=float(b["low"]); c=float(b["close"]); prev=float(bars[-2]["close"])
    direction=str(e6.output.get("direction","NEUTRAL")); rng=max(h-l,1e-9); body=abs(c-o); close_pos=(c-l)/rng
    bullish=c>o and c>prev and close_pos>=0.65; bearish=c<o and c<prev and close_pos<=0.35
    confirmed=(direction=="BUY" and bullish) or (direction=="SELL" and bearish)
    score=80.0 if confirmed else 35.0
    return EngineResult("E7",NAME,confirmed,score,{
        "question":"Is the setup thesis confirmed?","state":"CONFIRMED" if confirmed else "WAIT","confirmation":"CONFIRMED" if confirmed else "NOT_CONFIRMED",
        "trigger_observed":confirmed,"direction":direction,"candle_body":body,"range":rng,"close_position":close_pos,
        "reasoning_role":"CONFIRMATION_ANALYST","decision_authority":"E9"
    },() if confirmed else ("TRIGGER_NOT_CONFIRMED",))
