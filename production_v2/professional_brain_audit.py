from __future__ import annotations

"""Non-authoritative professional quality and profit-edge audit for E1-E9."""

from typing import Any

from .shared_market_picture import audit_shared_market_picture_contract

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
REQUIRED_BY_ENGINE = {
    "E1": ("finding", "confidence", "counter_evidence"), "E2": ("finding", "opportunity_state", "missing_evidence"),
    "E3": ("finding", "lifecycle", "protected_high", "protected_low"), "E4": ("finding", "auction_state", "auction_quality"),
    "E5": ("finding", "location_state", "repricing_state"), "E6": ("finding", "setup_state"),
    "E7": ("finding", "confirmation_state"), "E8": ("finding", "risk_state"), "E9": ("decision", "decision_state", "market_control"),
}


def _present(output: dict[str, Any], key: str) -> bool:
    value = output.get(key); return value not in (None, "", [], {}, ())


def _num(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default


def _codes(output: dict[str, Any]) -> list[str]:
    values=[]
    for key in ("active_reason_codes","active_invalidations","blockers","economic_blockers","conflicts"):
        value=output.get(key)
        if isinstance(value,(list,tuple,set)): values.extend(value)
        elif value: values.append(value)
    return [str(v).upper().strip() for v in values if str(v).strip()]


def audit_engine(engine_id: str, output: dict[str, Any]) -> dict[str, Any]:
    output=output or {}; required=REQUIRED_BY_ENGINE[engine_id]
    completeness=sum(_present(output,k) for k in required)/len(required)
    contract=output.get("professional_contract") or {}
    closed_candle=contract.get("closed_candle_only") is True
    authority=contract.get("decision_authority") == "E9_ONLY"
    lifecycle=_present(output,"professional_contract") and _present(output,"next_required_event")
    uncertainty=bool(output.get("missing_evidence")) or bool(output.get("counter_evidence")) or bool(output.get("active_reason_codes"))
    discipline=1.0 if uncertainty or output.get("finding") not in {"","UNRESOLVED",None} else 0.5
    score=55.0*completeness+15.0*float(closed_candle)+15.0*float(authority)+10.0*float(lifecycle)+5.0*discipline
    return {"score":round(max(0.0,min(100.0,score)),2),"grade":"PROFESSIONAL" if score>=90 else "ADVANCED" if score>=80 else "DEVELOPING" if score>=70 else "INCOMPLETE","contract_completeness":round(completeness*100,2),"closed_candle_discipline":closed_candle,"authority_boundary_intact":authority,"lifecycle_explicit":lifecycle,"uncertainty_explicit":uncertainty,"active_blocker_count":len(_codes(output)),"authority":"NON_AUTHORITATIVE_AUDIT_ONLY"}


def opportunity_potential(outputs: dict[str,dict[str,Any]]) -> dict[str,Any]:
    e5=outputs.get("E5",{}); e6=outputs.get("E6",{}); e7=outputs.get("E7",{}); e8=outputs.get("E8",{}); e9=outputs.get("E9",{})
    edge=e8.get("profit_edge") if isinstance(e8.get("profit_edge"),dict) else {}
    direction=str(e6.get("direction") or e9.get("direction") or "NEUTRAL").upper()
    setup=str(e6.get("setup") or e6.get("finding") or "").upper()
    space=_num(e5.get("available_space_atr_long")) if direction=="BUY" else _num(e5.get("available_space_atr_short")) if direction=="SELL" else max(_num(e5.get("available_space_atr_long")),_num(e5.get("available_space_atr_short")))
    plan=e8.get("trade_plan") if isinstance(e8.get("trade_plan"),dict) else {}
    rr=_num(plan.get("rr_tp2",plan.get("rr")),0)
    evidence=20.0 if direction in {"BUY","SELL"} else 0.0
    evidence+=15.0 if setup and "NO PLAUSIBLE" not in setup and "UNRESOLVED" not in setup else 0.0
    evidence+=15.0 if str(e7.get("confirmation_state") or "").upper() in {"PROVEN","CONFIRMED","VALIDATED","TRADE_READY"} else 0.0
    evidence+=min(20.0,max(0.0,space/1.5*20.0)); evidence+=20.0 if rr>=1.5 else min(20.0,max(0.0,rr/1.5*20.0)); evidence+=10.0 if e9.get("all_gates_pass") else 0.0
    return {"direction":direction,"latent_score":round(min(100,evidence),2),"available_space_atr":round(space,4),"real_rr":round(rr,3),"executable":bool(e9.get("all_gates_pass")),"status":"EXECUTABLE" if e9.get("all_gates_pass") else "WATCH" if evidence>=45 else "LOW_EDGE","setup":setup,"do_not_execute":not bool(e9.get("all_gates_pass")),"profit_edge":edge,"profit_measurement":"CONDITIONAL_EXPECTED_R_AFTER_COST_STRESS","no_profit_guarantee":True}


def audit_all(outputs: dict[str,dict[str,Any]]) -> dict[str,Any]:
    per_engine={eid:audit_engine(eid,outputs.get(eid,{})) for eid in ENGINE_ORDER}
    shared_audit = audit_shared_market_picture_contract(outputs)
    for engine_id in ENGINE_ORDER:
        per_engine[engine_id]["shared_market_picture_contract"] = {
            "passed": engine_id in shared_audit["covered_brains"] and engine_id not in shared_audit["mismatched_brains"] and engine_id not in shared_audit["missing_contract_brains"],
            "picture_id": (outputs.get(engine_id, {}).get("market_picture_contract") or {}).get("picture_id"),
            "authority": "NON_AUTHORITATIVE_CONTRACT_AUDIT",
        }
    return {"per_engine":per_engine,"overall_score":round(sum(x["score"] for x in per_engine.values())/len(per_engine),2),"opportunity":opportunity_potential(outputs),"shared_market_picture_contract":shared_audit,"authority":"AUDIT_ONLY_E9_REMAINS_FINAL_AUTHORITY"}
