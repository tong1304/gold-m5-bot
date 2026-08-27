from __future__ import annotations
from typing import Any
from .contracts import EngineResult

NAME="Master Decision Brain"
QUESTION="Should this trade be taken after reconciling all relevant evidence?"

def _out(e): return e.output if e else {}

def analyze_e9(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    engines=[upstream.get(f"E{i}") for i in range(1,9)]; e1,e2,e3,e4,e5,e6,e7,e8=engines
    o6,o7,o8=_out(e6),_out(e7),_out(e8); reasons=[]; conflicts=[]
    setup_dir=str(o6.get("direction","NEUTRAL")).upper(); trigger_dir=str(o7.get("direction",setup_dir)).upper(); risk_dir=str(o8.get("direction",setup_dir)).upper()
    dirs={d for d in (setup_dir,trigger_dir,risk_dir) if d in {"BUY","SELL"}}
    if len(dirs)>1: conflicts.append("SETUP_TRIGGER_RISK_DIRECTION_CONFLICT")
    direction=setup_dir if setup_dir in {"BUY","SELL"} and len(dirs)<=1 else "NEUTRAL"
    setup=str(o6.get("setup","NONE")); thesis=str(o6.get("thesis","UNRESOLVED")); maturity=str(o6.get("maturity","UNRESOLVED")); confirmation=str(o7.get("confirmation","UNRESOLVED")); risk_gate=str(o8.get("risk_gate","RISK_NOT_READY")); plan=o8.get("trade_plan") or {}
    setup_ready=maturity=="MATURE" and setup!="NONE" and direction in {"BUY","SELL"}
    confirmation_ready=confirmation=="CONFIRMED" and bool(o7.get("trigger_observed"))
    economics_ready=risk_gate=="RISK_READY" and bool(plan.get("valid"))
    if direction=="NEUTRAL": reasons.append("DIRECTION_UNRESOLVED")
    if setup=="NONE" or maturity=="UNRESOLVED": reasons.append("SETUP_NOT_ESTABLISHED")
    elif not setup_ready: reasons.append("SETUP_NOT_MATURE")
    if not confirmation_ready: reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready: reasons.append("RISK_NOT_READY")
    reasons.extend(conflicts)
    decision=direction if setup_ready and confirmation_ready and economics_ready and not conflicts else "NO_TRADE"
    authority_checks={f"E{i}_finding":_out(e).get("finding","UNRESOLVED") for i,e in enumerate(engines,1)}
    authority_checks.update({"E6_thesis":thesis,"E6_setup":setup,"E6_maturity":maturity,"E7_confirmation":confirmation,"E8_risk_gate":risk_gate})
    return EngineResult("E9",NAME,decision in {"BUY","SELL"},100.0 if decision in {"BUY","SELL"} else 0.0,{"question":QUESTION,"decision":decision,"direction":direction,"thesis":thesis,"setup":setup,"maturity":maturity,"confirmation":confirmation,"risk_gate":risk_gate,"setup_ready":setup_ready,"confirmation_ready":confirmation_ready,"economics_ready":economics_ready,"trade_plan":plan,"reasoning_role":"MASTER_DECISION_ANALYST","decision_authority":"E9","trade_decision_authority":True,"architecture":"SINGLE_AXIS_E1_TO_E9","reconciliation":"DOMAIN_EVIDENCE_RECONCILIATION_NOT_VOTING","authority_checks":authority_checks,"conflicts":conflicts,"evidence_used":"E1_E2_E3_E4_E5_E6_E7_E8","counter_evidence":reasons,"invalidation":["new closed-candle evidence changes a decisive prerequisite"]},tuple(reasons))
