from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Should this trade be taken after reconciling all relevant evidence?"
ARCHITECTURE = "E9_MASTER_DECISION_RESOLUTION_V30"
VERSION = "30.1"
DIRECTIONS = {"BUY", "SELL"}

HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
}

ECONOMIC_BLOCKERS = {
    "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID",
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET",
    "RISK_QUALITY_BELOW_DECISION_THRESHOLD",
}

BLOCKER_PRIORITY = (
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
    "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID",
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET",
    "ENTRY_CONFIRMATION_NOT_PROVEN", "SETUP_NOT_MATURE", "RISK_NOT_READY",
    "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "DIRECTION_UNRESOLVED",
)


def _out(engine: EngineResult | None) -> dict[str, Any]:
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _engine_codes(engine: EngineResult | None) -> list[str]:
    if not engine:
        return []
    output = _out(engine)
    values: list[Any] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "risk_blockers", "economic_blockers"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(value)
    values.extend(engine.reason_codes or ())
    return _dedupe([_text(v) for v in values if v])


def _output_codes(output: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "risk_blockers", "economic_blockers"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(value)
    return _dedupe([_text(v) for v in values if v])


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS:
            return x
        if any(k in x for k in ("BULLISH", "LONG", "BUYERS", "TREND_UP")) or x == "UP":
            return "BUY"
        if any(k in x for k in ("BEARISH", "SHORT", "SELLERS", "TREND_DOWN")) or x == "DOWN":
            return "SELL"
    return "NEUTRAL"


def _e6_identity(e6: dict[str, Any]) -> tuple[str, str, str]:
    finding = str(e6.get("finding") or "").strip()
    direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"), finding)
    setup = e6.get("setup") or e6.get("setup_family") or e6.get("setup_type") or e6.get("thesis_setup")
    if not setup and finding:
        head = finding.split(" is validating", 1)[0].split(" is ", 1)[0].strip()
        if direction in DIRECTIONS:
            prefix = direction + " "
            setup = head[len(prefix):].strip() if _text(head).startswith(prefix) else head
    thesis = e6.get("thesis") or e6.get("candidate_setup_thesis") or finding
    return direction, str(setup or "UNKNOWN").strip(), str(thesis or "UNRESOLVED").strip()


def _state(output: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = output.get(key)
        if value not in (None, ""):
            return _text(value)
    return "UNRESOLVED"


def _trigger_observed(e7: dict[str, Any]) -> bool:
    for key in ("trigger_observed", "valid_trigger", "closed_candle_trigger"):
        if e7.get(key) is True:
            return True
    state = _state(e7, ("trigger_state", "trigger", "entry_trigger"))
    if state in {"VALID", "VALIDATED", "CONFIRMED", "PROVEN", "TRADE_READY"}:
        return True
    return bool(set(_output_codes(e7)).intersection({"VALID_CLOSED_CANDLE_TRIGGER", "TRIGGER_CONFIRMED", "CONFIRMATION_PROVEN"}))


def _confirmation_state(e7: dict[str, Any]) -> str:
    codes = set(_output_codes(e7))
    if codes.intersection({"E7_CONFIRMATION_INVALIDATED", "CONFIRMATION_INVALIDATED"}):
        return "INVALIDATED"
    if codes.intersection({"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"}):
        return "PROVEN"
    if codes.intersection({"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"}):
        return "PENDING"
    return _state(e7, ("confirmation_state", "confirmation", "proof_state", "trigger_state"))


def _risk_state(e8: dict[str, Any]) -> str:
    codes = set(_output_codes(e8))
    if codes.intersection({"E8_RISK_INVALIDATED", "RISK_INVALIDATED"}):
        return "INVALIDATED"
    if codes.intersection(ECONOMIC_BLOCKERS):
        return "BLOCKED"
    return _state(e8, ("risk_gate", "risk_state", "economic_state", "decision_state"))


def _plan_valid(e8: dict[str, Any], direction: str) -> bool:
    plan = e8.get("trade_plan") or e8.get("plan") or e8.get("execution_plan") or {}
    if not isinstance(plan, dict) or direction not in DIRECTIONS:
        return False
    try:
        entry = float(plan["entry"])
        stop = float(plan["stop_loss"])
        target = float(plan.get("take_profit_2", plan.get("take_profit", plan.get("tp2"))))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(x == x for x in (entry, stop, target)):
        return False
    if direction == "BUY" and not stop < entry < target:
        return False
    if direction == "SELL" and not target < entry < stop:
        return False
    rr = plan.get("rr_tp2", plan.get("rr"))
    if rr not in (None, ""):
        try:
            if float(rr) < 1.50:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _collect_conflicts(upstream: dict[str, EngineResult]) -> list[str]:
    found: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        found.extend(code for code in _engine_codes(upstream.get(engine_id)) if code in HARD_CONFLICT_CODES)
    return _dedupe(found)


def _resolution(direction: str, setup: str, thesis: str, e6: dict[str, Any], e7: dict[str, Any], e8: dict[str, Any], conflicts: list[str]) -> dict[str, Any]:
    maturity = _state(e6, ("maturity", "setup_stage", "stage", "lifecycle"))
    confirmation = _confirmation_state(e7)
    trigger = _trigger_observed(e7)
    risk_state = _risk_state(e8)
    plan_valid = _plan_valid(e8, direction)
    e8_codes = [code for code in _output_codes(e8) if code in ECONOMIC_BLOCKERS]

    direction_ready = direction in DIRECTIONS
    setup_known = setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
    setup_ready = direction_ready and setup_known and maturity in {"MATURE", "TRADE_READY", "VALIDATED", "CONFIRMED"}
    confirmation_ready = confirmation in {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"} and trigger
    risk_ready = not e8_codes and risk_state in {"READY", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY", "VALIDATED", "PASS", "PASSED"} and plan_valid

    blockers = _dedupe(conflicts + e8_codes)
    if not direction_ready:
        blockers.append("DIRECTION_UNRESOLVED")
    if not setup_ready:
        blockers.append("SETUP_NOT_MATURE")
    if not confirmation_ready:
        blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not risk_ready:
        blockers.append("RISK_NOT_READY")
    blockers = _dedupe(blockers)

    primary = next((code for code in BLOCKER_PRIORITY if code in blockers), "NONE")
    hard_conflict = bool(conflicts)
    all_pass = direction_ready and setup_ready and confirmation_ready and risk_ready and not conflicts and not e8_codes

    if all_pass:
        decision, decision_state = direction, "EXECUTE"
        thesis_state, setup_state = "ESTABLISHED", "TRADE_READY"
        confirmation_state, final_risk_state, execution_state = "PROVEN", "READY", "READY"
        next_event = "NONE"
    elif hard_conflict:
        decision, decision_state = "NO_TRADE", "REJECT"
        thesis_state = "INVALIDATED" if any("INVALIDAT" in x for x in conflicts) else "CONFLICTED"
        setup_state = confirmation_state = final_risk_state = execution_state = "BLOCKED"
        next_event = "NEW_CLOSED_CANDLE_MUST_RESOLVE_THE_DECISIVE_CONFLICT"
    else:
        decision, decision_state = "NO_TRADE", "WAIT_FOR_PROOF"
        thesis_state = "ESTABLISHED" if direction_ready else "UNRESOLVED"
        setup_state = "FORMING" if setup_known else "UNRESOLVED"
        confirmation_state = "PROVEN" if confirmation_ready else "PENDING"
        final_risk_state = "READY" if risk_ready else "BLOCKED"
        execution_state = "BLOCKED"
        if primary == "DIRECTION_UNRESOLVED":
            next_event = "E6_MUST_ESTABLISH_A_DIRECTIONAL_THESIS_AND_SETUP"
        elif primary == "SETUP_NOT_MATURE":
            next_event = "E6_SETUP_MUST_REACH_MATURE_OR_TRADE_READY"
        elif primary == "ENTRY_CONFIRMATION_NOT_PROVEN":
            next_event = "E7_MUST_PROVE_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"
        elif primary == "RISK_NOT_READY":
            next_event = "E8_MUST_PROVE_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS"
        else:
            next_event = "NEW_CLOSED_CANDLE_MUST_REMOVE_THE_PRIMARY_BLOCKER"

    secondary = [code for code in blockers if code != primary]
    rationale = (
        f"{direction} executable: E6 thesis, E7 confirmation and E8 economics/risk all pass."
        if all_pass else
        f"NO_TRADE because {primary}; E9 will not promote the thesis to execution until the decisive gate is resolved."
    )
    return {
        "decision": decision,
        "decision_state": decision_state,
        "thesis_state": thesis_state,
        "setup_state": setup_state,
        "confirmation_state": confirmation_state,
        "risk_state": final_risk_state,
        "execution_state": execution_state,
        "primary_blocker": primary,
        "secondary_blockers": secondary,
        "next_required_event": next_event,
        "all_gates_pass": all_pass,
        "hard_conflict": hard_conflict,
        "direction": direction,
        "setup": setup,
        "thesis": thesis,
        "e6_maturity": maturity,
        "e7_confirmation": confirmation,
        "e7_trigger_observed": trigger,
        "e8_risk_state": risk_state,
        "e8_plan_valid": plan_valid,
        "e8_economic_blockers": e8_codes,
        "rationale": rationale,
        "authority": {"thesis": "E6", "confirmation": "E7", "economics_risk": "E8", "final_decision": "E9"},
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E9 master resolution: reconcile E1-E8 without inventing a thesis or lookahead."""
    del snapshot
    e6, e7, e8 = _out(upstream.get("E6")), _out(upstream.get("E7")), _out(upstream.get("E8"))
    direction, setup, thesis = _e6_identity(e6)
    conflicts = _collect_conflicts(upstream)
    resolved = _resolution(direction, setup, thesis, e6, e7, e8, conflicts)

    evidence_summary: dict[str, Any] = {}
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id)
        output = _out(engine)
        evidence_summary[engine_id] = {
            "finding": output.get("finding", output.get("state", "UNRESOLVED")),
            "gate_passed": engine.gate_passed if engine else None,
            "reason_codes": _engine_codes(engine),
        }

    readiness_score = round(sum((
        25.0 if direction in DIRECTIONS else 0.0,
        25.0 if resolved["setup_state"] == "TRADE_READY" else 12.5 if resolved["setup_state"] == "FORMING" else 0.0,
        25.0 if resolved["confirmation_state"] == "PROVEN" else 12.5 if resolved["confirmation_state"] == "PENDING" else 0.0,
        25.0 if resolved["risk_state"] == "READY" else 0.0,
    )), 2)

    reason_codes = _dedupe(
        [resolved["primary_blocker"] if resolved["primary_blocker"] != "NONE" else "MASTER_GATES_PASSED"]
        + resolved["secondary_blockers"]
        + (["E9_HARD_CONFLICT"] if resolved["hard_conflict"] else [])
    )

    output = {
        **resolved,
        "master_resolution": "EXECUTE" if resolved["all_gates_pass"] else "REJECT" if resolved["decision_state"] == "REJECT" else "WAIT_FOR_PROOF",
        "readiness_score": readiness_score,
        "evidence_summary": evidence_summary,
        "decision_contract": {
            "BUY_SELL_requires_all_gates": True,
            "NO_TRADE_on_missing_confirmation": True,
            "NO_TRADE_on_economic_failure": True,
            "E9_does_not_create_thesis": True,
            "E9_does_not_override_E8": True,
            "closed_candle_only": True,
            "lookahead": False,
        },
    }
    return EngineResult(
        engine_id="E9", name=NAME, gate_passed=bool(resolved["all_gates_pass"]),
        score=readiness_score, output=output, reason_codes=tuple(reason_codes),
    )
