from __future__ import annotations
from typing import Any
from .contracts import EngineResult

NAME="Master Decision Brain"

def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    reasons=[]
    e1,e2,e3,e4,e5,e6,e7,e8=[upstream.get(f"E{i}") for i in range(1,9)]
    directions=[]
    for e in (e1,e2,e3,e4,e5,e6,e7,e8):
        d=str((e.output if e else {}).get("direction","")).upper()
        if d in {"BUY","UP","BULLISH"}: directions.append("BUY")
        elif d in {"SELL","DOWN","BEARISH"}: directions.append("SELL")
    buy=directions.count("BUY"); sell=directions.count("SELL")
    direction="BUY" if buy>sell else "SELL" if sell>buy else "NEUTRAL"
    setup_ready=bool(e6 and e6.gate_passed and e6.output.get("maturity")=="MATURE")
    confirmation=bool(e7 and e7.gate_passed)
    economics=bool(e8 and e8.gate_passed and e8.output.get("risk_gate")=="RISK_READY")
    plan=(e8.output.get("trade_plan") if e8 else {}) or {}
    decision=direction if direction in {"BUY","SELL"} and setup_ready and confirmation and economics else "NO_TRADE"
    if direction=="NEUTRAL": reasons.append("DIRECTION_UNRESOLVED")
    if not setup_ready: reasons.append("SETUP_NOT_MATURE")
    if not confirmation: reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics: reasons.append("RISK_NOT_READY")
    score=round((buy+sell)/8*100,2)
    return EngineResult("E9",NAME,decision in {"BUY","SELL"},score,{
        "question":"Should this trade be taken?","decision":decision,"direction":direction,"vote_buy":buy,"vote_sell":sell,
        "setup_ready":setup_ready,"confirmation_ready":confirmation,"economics_ready":economics,"trade_plan":plan,
        "reasoning_role":"MASTER_DECISION_ANALYST","decision_authority":"E9","architecture":"SINGLE_AXIS_E1_TO_E9"
    },tuple(reasons))
