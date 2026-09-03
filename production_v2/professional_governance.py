from __future__ import annotations

"""Read-only governance for the nine professional brains.

Only explicit present-tense hard vetoes block execution. Pending or mixed
supporting evidence is recorded for E9 and is not a universal veto.
"""

from typing import Any

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
HARD_BLOCKER_KEYS = ("active_invalidations", "hard_vetoes", "blocking_reasons")
PENDING_STATES = {"PENDING", "UNRESOLVED", "VALIDATING", "FORMING", "BLOCKED", "WAIT_FOR_PROOF", "INSUFFICIENT_PROOF", "NOT_READY", "UNKNOWN"}


def _output(results: dict[str, Any], engine: str) -> dict[str, Any]:
    value = results.get(engine)
    if value is None: return {}
    if isinstance(value, dict): return value
    value = getattr(value, "output", None)
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    if value is None: return []
    if isinstance(value, str): return [value] if value else []
    if isinstance(value, dict): return [str(k) for k, v in value.items() if v]
    if isinstance(value, (list, tuple, set)): return [str(x) for x in value if x]
    return [str(value)]


def _first(output: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in output and output[key] not in (None, "", [], {}, ()): return output[key]
    return None


def _engine_blockers(engine: str, output: dict[str, Any]) -> list[str]:
    blockers=[]
    for key in HARD_BLOCKER_KEYS: blockers.extend(_items(output.get(key)))
    status=str(_first(output,"status","analysis_status","state") or "").upper()
    if status in {"UNAVAILABLE","INCOMPLETE","INSUFFICIENT_DATA","ERROR","INVALIDATED"}: blockers.append(f"{engine}_{status}")
    if output.get("hard_veto") is True: blockers.append(f"{engine}_HARD_VETO")
    return list(dict.fromkeys(blockers))


def _pending_gate(engine: str, output: dict[str, Any], blockers: list[str]) -> bool:
    if not output or blockers: return False
    if output.get("gate_passed") is False: return True
    status=str(_first(output,"analysis_status","state","confirmation_state","risk_state") or "").upper()
    return status in PENDING_STATES and engine in {"E2","E4","E6","E7","E8"}


def _missing(output: dict[str, Any]) -> list[str]:
    values=[]
    for key in ("missing_evidence","confirmation_required","next_required_event"): values.extend(_items(output.get(key)))
    return list(dict.fromkeys(values))


def _direction(output: dict[str, Any]) -> str:
    raw=str(_first(output,"direction","opportunity_direction","trend_state") or "NEUTRAL").upper().strip()
    if raw in {"UP","BUY","BULLISH","LONG","BUYERS","TREND_UP"}: return "UP"
    if raw in {"DOWN","SELL","BEARISH","SHORT","SELLERS","TREND_DOWN"}: return "DOWN"
    return "NEUTRAL"


def _maturity(output: dict[str, Any]) -> str:
    return str(_first(output,"opportunity_maturity","maturity","setup_stage","opportunity_stage","state") or "UNRESOLVED").upper()


def _auction_state(output: dict[str, Any]) -> str:
    return str(_first(output,"auction_state","auction_phase","liquidity_state") or "UNKNOWN").upper()


def _confirmation(output: dict[str, Any]) -> bool:
    for key in ("confirmation_passed","confirmed","closed_candle_confirmed","trigger_confirmed"):
        if output.get(key) is True: return True
    value=str(_first(output,"confirmation_state","confirmation","state") or "").upper()
    return value in {"CONFIRMED","VALID","PASSED","PROVEN","TRADE_READY"}


def _economics_valid(output: dict[str, Any]) -> bool:
    for key in ("trade_economics_valid","economics_valid","trade_ready","risk_ready"):
        if key in output and output[key] is False: return False
    plan=output.get("trade_plan")
    return not (isinstance(plan,dict) and plan.get("valid") is False)


def audit_engines(results: dict[str, Any]) -> dict[str, Any]:
    per_engine={}; all_missing=[]; all_blockers=[]; pending_gates=[]; directions={}
    for engine in ENGINE_ORDER:
        output=_output(results,engine); blockers=_engine_blockers(engine,output); missing=_missing(output); direction=_direction(output); maturity=_maturity(output); pending=_pending_gate(engine,output,blockers)
        directions[engine]=direction; all_blockers.extend(f"{engine}:{x}" for x in blockers); all_missing.extend(f"{engine}:{x}" for x in missing)
        if pending: pending_gates.append(engine)
        per_engine[engine]={"present":bool(output),"direction":direction,"maturity":maturity,"auction_state":_auction_state(output),"confirmation_passed":_confirmation(output),"economics_valid":_economics_valid(output),"hard_blockers":list(dict.fromkeys(blockers)),"pending_gate":pending,"missing_evidence":list(dict.fromkeys(missing))}

    # Directional disagreement between evidence brains is a reconciliation input,
    # not a hard veto. E9 may veto only when an upstream brain explicitly emits a
    # fatal conflict/invalidation.
    directional_conflict=False
    e3_output=_output(results,"E3"); lifecycle=str(_first(e3_output,"structure_lifecycle","lifecycle") or "").upper()
    if lifecycle == "INVALIDATED": all_blockers.append("STRUCTURE_INVALIDATED")
    elif "TRANSITION" in lifecycle: pending_gates.append("E3")
    if per_engine["E4"]["auction_state"] in {"PENDING","UNKNOWN","INITIATIVE","UNRESOLVED"}: pending_gates.append("E4")
    if not per_engine["E7"]["confirmation_passed"]: pending_gates.append("E7")
    # E8 can be non-ready because the trade trigger/plan is still forming.
    # That is a pending proof state, not a fatal governance veto. Explicit E8
    # hard blockers have already been captured above and remain veto-capable.
    if not per_engine["E8"]["economics_valid"] and not per_engine["E8"]["hard_blockers"]: pending_gates.append("E8")

    all_blockers=list(dict.fromkeys(all_blockers)); all_missing=list(dict.fromkeys(all_missing)); pending_gates=list(dict.fromkeys(pending_gates)); hard_veto=bool(all_blockers)
    next_event=[]
    for engine in ("E2","E3","E4","E6","E7","E8"): next_event.extend(per_engine[engine]["missing_evidence"])
    if not next_event and pending_gates: next_event.append("next closed candle must resolve the pending proof gates")
    if not next_event and hard_veto: next_event.append("resolve all hard blockers on a future closed candle")
    maturity="HARD_BLOCKED" if hard_veto else "PENDING_PROOF" if pending_gates else "READY_FOR_E9_AUTHORITY_CHECK"
    return {"architecture":"NINE_BRAIN_PROFESSIONAL_GOVERNANCE_V4","engine_order":list(ENGINE_ORDER),"hard_veto":hard_veto,"hard_vetoes":all_blockers,"pending_gates":pending_gates,"missing_evidence":all_missing,"next_required_event":list(dict.fromkeys(next_event)),"maturity":maturity,"directional_conflict":directional_conflict,"per_engine":per_engine,"read_only":True,"e9_only_trade_authority":True,"pending_is_not_hard_conflict":True,"future_invalidation_catalog_is_not_active_veto":True}


def enforce_final_authority(e9_output: dict[str, Any], audit: dict[str, Any]) -> tuple[str, bool, list[str]]:
    """Authorize only an E9 EXECUTE decision with all three mandatory proofs.

    E1-E5 pending/mixed evidence does not veto an otherwise valid E6/E7/E8
    decision. Fatal audit vetoes always win.
    """
    reasons=list(audit.get("hard_vetoes") or [])
    requested=str(e9_output.get("decision") or "NO_TRADE").upper()
    if audit.get("hard_veto"):
        reasons.append("NINE_BRAIN_FATAL_VETO")
        return "NO_TRADE",False,list(dict.fromkeys(reasons))
    if requested not in {"BUY","SELL"}:
        return "NO_TRADE",False,list(dict.fromkeys(reasons))
    mandatory=e9_output.get("mandatory_gates")
    if not isinstance(mandatory,dict):
        reasons.append("E9_MANDATORY_GATE_CONTRACT_MISSING")
        return "NO_TRADE",False,list(dict.fromkeys(reasons))
    required=("core_thesis","closed_candle_trigger","survivable_economics","fatal_veto_clear")
    if any(mandatory.get(key) is not True for key in required):
        reasons.append("E9_MANDATORY_PROOF_INCOMPLETE")
        return "NO_TRADE",False,list(dict.fromkeys(reasons))
    if e9_output.get("all_gates_pass") is not True:
        reasons.append("E9_ALL_MANDATORY_GATES_NOT_PASSED")
        return "NO_TRADE",False,list(dict.fromkeys(reasons))
    return requested,True,list(dict.fromkeys(reasons))
