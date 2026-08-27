from __future__ import annotations

from typing import Any
from .contracts import EngineResult

NAME="Master Decision Brain"
QUESTION="Should this trade be taken after reconciling all relevant evidence?"


def _out(e):
    return e.output if e else {}


def analyze_e9(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    e1,e2,e3,e4,e5,e6,e7,e8=[upstream.get(f"E{i}") for i in range(1,9)]
    o6,o7,o8=_out(e6),_out(e7),_out(e8)
    reasons=[]; conflicts=[]
    setup_dir=str(o6.get("direction","NEUTRAL")).upper()
    trigger_dir=str(o7.get("direction",setup_dir)).upper()
    risk_dir=str(o8.get("direction",setup_dir)).upper()
    directions={d for d in (setup_dir,trigger_dir,risk_dir) if d in {"BUY","SELL"}}
    if len(directions)>1:
        conflicts.append("SETUP_TRIGGER_RISK_DIRECTION_CONFLICT")
    direction=setup_dir if setup_dir in {"BUY","SELL"} and len(directions)<=1 else "NEUTRAL"
    setup_ready=bool(e6 and e6.gate_passed and o6.get("maturity")=="MATURE")
    confirmation_ready=bool(e7 and e7.gate_passed)
    economics_ready=bool(e8 and e8.gate_passed and o8.get("risk_gate")=="RISK_READY")
    plan=o8.get("trade_plan") or {}
    # E9 does not vote. It reconciles domain conclusions and veto conditions.
    if direction=="NEUTRAL": reasons.append("DIRECTION_UNRESOLVED")
    if not setup_ready: reasons.append("SETUP_NOT_MATURE")
    if not confirmation_ready: reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready: reasons.append("RISK_NOT_READY")
    if conflicts: reasons.extend(conflicts)
    decision=direction if direction in {"BUY","SELL"} and setup_ready and confirmation_ready and economics_ready and not conflicts else "NO_TRADE"
    authority_checks={
        "E1_state": _out(e1).get("market_state","UNCLEAR"),
        "E2_opportunity": _out(e2).get("finding",_out(e2).get("thesis","UNRESOLVED")),
        "E3_structure": _out(e3).get("finding",_out(e3).get("structure_state","UNRESOLVED")),
        "E4_liquidity": _out(e4).get("finding",_out(e4).get("auction_state","UNRESOLVED")),
        "E5_location": _out(e5).get("finding",_out(e5).get("location_state","UNRESOLVED")),
        "E6_setup_ready": setup_ready,
        "E7_confirmation_ready": confirmation_ready,
        "E8_economics_ready": economics_ready,
    }
    score=100.0 if decision in {"BUY","SELL"} else 0.0
    return EngineResult("E9",NAME,decision in {"BUY","SELL"},score,{
        "question":QUESTION,"decision":decision,"direction":direction,
        "setup_ready":setup_ready,"confirmation_ready":confirmation_ready,"economics_ready":economics_ready,
        "trade_plan":plan,"reasoning_role":"MASTER_DECISION_ANALYST","decision_authority":"E9",
        "trade_decision_authority":True,"architecture":"SINGLE_AXIS_E1_TO_E9",
        "reconciliation":"DOMAIN_EVIDENCE_RECONCILIATION_NOT_VOTING","authority_checks":authority_checks,
        "conflicts":conflicts,"evidence_used":"E1_E2_E3_E4_E5_E6_E7_E8",
        "counter_evidence":reasons,"invalidation":["new closed-candle evidence changes a decisive prerequisite"],
    },tuple(reasons))
