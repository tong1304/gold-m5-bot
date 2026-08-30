from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Should this trade be taken after reconciling all relevant evidence?"
ARCHITECTURE = "E9_MASTER_DECISION_RESOLUTION_V30"
VERSION = "30.0"
DIRECTIONS = {"BUY", "SELL"}

# E9 is the final authority, but it does not create a thesis.  E6 owns thesis
# identity, E7 owns confirmation, and E8 owns economic/risk survivability.
# Only explicit contradiction/invalidations become thesis-level conflicts.
HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED",
    "MARKET_STATE_CONFLICT",
    "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS",
    "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED",
    "E7_CONFIRMATION_INVALIDATED",
    "E8_RISK_INVALIDATED",
}

ECONOMIC_BLOCKERS = {
    "INVALID_TRADE_GEOMETRY",
    "INVALID_RISK_GEOMETRY",
    "RISK_GEOMETRY_INVALID",
    "REAL_RR_BELOW_MINIMUM",
    "EXECUTION_COST_TOO_HIGH",
    "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE",
    "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM",
    "TARGET_REALISM_TOO_LOW",
    "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    "NO_USABLE_STRUCTURAL_TARGET",
    "RISK_QUALITY_BELOW_DECISION_THRESHOLD",
}

# Lower number = higher authority for selecting the single primary blocker.
BLOCKER_PRIORITY = (
    "THESIS_INVALIDATED",
    "MARKET_STATE_CONFLICT",
    "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS",
    "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED",
    "E7_CONFIRMATION_INVALIDATED",
    "E8_RISK_INVALIDATED",
    "INVALID_TRADE_GEOMETRY",
    "INVALID_RISK_GEOMETRY",
    "RISK_GEOMETRY_INVALID",
    "REAL_RR_BELOW_MINIMUM",
    "EXECUTION_COST_TOO_HIGH",
    "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE",
    "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM",
    "TARGET_REALISM_TOO_LOW",
    "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    "NO_USABLE_STRUCTURAL_TARGET",
    "ENTRY_CONFIRMATION_NOT_PROVEN",
    "SETUP_NOT_MATURE",
    "RISK_NOT_READY",
    "RISK_QUALITY_BELOW_DECISION_THRESHOLD",
    "DIRECTION_UNRESOLVED",
)


def _out(engine: EngineResult | None) -> dict[str, Any]:
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _codes(engine: EngineResult | None) -> list[str]:
    if not engine:
        return []
    output = _out(engine)
    values = output.get("reason_codes") or output.get("reasons") or output.get("counter_evidence") or []
    if isinstance(values, str):
        values = [values]
    values = [_text(v) for v in values if v]
    values.extend(_text(v) for v in (engine.reason_codes or ()) if v)
    return _dedupe(values)


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS:
            return x
        if any(k in x for k in ("BULLISH", "LONG", "BUYERS", "TREND_UP")):
            return "BUY"
        if any(k in x for k in ("BEARISH", "SHORT", "SELLERS", "TREND_DOWN")):
            return "SELL"
        # UP/DOWN are intentionally checked after the explicit words above.
        if x == "UP":
            return "BUY"
        if x == "DOWN":
            return "SELL"
    return "NEUTRAL"


def _e6_identity(e6: dict[str, Any]) -> tuple[str, str, str]:
    finding = str(e6.get("finding") or "").strip()
    direction = _direction(
        e6.get("direction"),
        e6.get("direction_thesis"),
        e6.get("thesis_direction"),
        finding,
    )
    setup = e6.get("setup") or e6.get("setup_family") or e6.get("setup_type") or e6.get("thesis_setup")
    if not setup and finding:
        head = finding.split(" is validating", 1)[0].split(" is ", 1)[0].strip()
        if direction in DIRECTIONS:
            prefix = direction + " "
            setup = head[len(prefix):].strip() if _text(head).startswith(prefix) else head
    thesis = e6.get("thesis") or e6.get("candidate_setup_thesis") or finding
    return direction, str(setup or "UNKNOWN").strip(), str(thesis or "UNRESOLVED").strip()


def _state(output: dict[str, Any], keys: tuple[str, ...], defaults: tuple[str, ...] = ()) -> str:
    for key in keys:
        value = output.get(key)
        if value not in (None, ""):
            return _text(value)
    return defaults[0] if defaults else "UNRESOLVED"


def _trigger_observed(e7: dict[str, Any]) -> bool:
    for key in ("trigger_observed", "valid_trigger", "closed_candle_trigger"):
        value = e7.get(key)
        if value is True:
            return True
    state = _state(e7, ("trigger_state", "trigger", "entry_trigger"))
    if state in {"VALID", "VALIDATED", "CONFIRMED", "PROVEN", "TRADE_READY"}:
        return True
    codes = set(_codes_from_output(e7))
    return bool(codes.intersection({"VALID_CLOSED_CANDLE_TRIGGER", "TRIGGER_CONFIRMED", "CONFIRMATION_PROVEN"}))


def _codes_from_output(output: dict[str, Any]) -> list[str]:
    values = output.get("reason_codes") or output.get("reasons") or output.get("counter_evidence") or []
    if isinstance(values, str):
        values = [values]
    return [_text(v) for v in values if v]


def _confirmation_state(e7: dict[str, Any]) -> str:
    codes = set(_codes_from_output(e7))
    if codes.intersection({"E7_CONFIRMATION_INVALIDATED", "CONFIRMATION_INVALIDATED"}):
        return "INVALIDATED"
    if codes.intersection({"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"}):
        return "PROVEN"
    if codes.intersection({
        "PROOF_GATES_INCOMPLETE",
        "VALID_CLOSED_CANDLE_TRIGGER_MISSING",
        "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION",
        "LIQUIDITY_RECLAIM_LEVEL_REQUIRED",
    }):
        return "PENDING"
    return _state(e7, ("confirmation_state", "confirmation", "proof_state", "trigger_state"))


def _risk_state(e8: dict[str, Any]) -> str:
    codes = set(_codes_from_output(e8))
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


def _extract_e8_blockers(e8: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for value in (
        e8.get("reason_codes"),
        e8.get("reasons"),
        e8.get("blockers"),
        e8.get("risk_blockers"),
        e8.get("economic_blockers"),
    ):
        if isinstance(value, str):
            result.append(_text(value))
        elif isinstance(value, (list, tuple, set)):
            result.extend(_text(v) for v in value if v)
    return _dedupe(result)


def _collect_conflicts(upstream: dict[str, EngineResult]) -> list[str]:
    conflicts: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        for code in _codes(upstream.get(engine_id)):
            if code in HARD_CONFLICT_CODES:
                conflicts.append(code)
    return _dedupe(conflicts)


def _resolution(
    direction: str,
    setup: str,
    thesis: str,
    e6: dict[str, Any],
    e7: dict[str, Any],
    e8: dict[str, Any],
    conflicts: list[str],
) -> dict[str, Any]:
    e6_maturity = _state(e6, ("maturity", "setup_stage", "stage", "lifecycle"))
    e7_confirmation = _confirmation_state(e7)
    trigger = _trigger_observed(e7)
    e8_risk = _risk_state(e8)
    plan_valid = _plan_valid(e8, direction)
    e8_codes = _extract_e8_blockers(e8)

    direction_ready = direction in DIRECTIONS
    setup_known = setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
    setup_ready = direction_ready and setup_known and e6_maturity in {
        "MATURE", "TRADE_READY", "VALIDATED", "CONFIRMED"
    }
    confirmation_ready = e7_confirmation in {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"} and trigger
    risk_blocked = bool(set(e8_codes).intersection(ECONOMIC_BLOCKERS)) or e8_risk in {"BLOCKED", "INVALIDATED"}
    risk_ready = not risk_blocked and plan_valid and e8_risk in {
        "READY", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY", "VALIDATED", "PASS", "PASSED"
    }

    blockers: list[str] = list(conflicts)
    blockers.extend(e8_codes)
    if not direction_ready:
        blockers.append("DIRECTION_UNRESOLVED")
    if not setup_ready:
        blockers.append("SETUP_NOT_MATURE")
    if not confirmation_ready:
        blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not risk_ready:
        blockers.append("RISK_NOT_READY")
    blockers = _dedupe(blockers)

    primary = "NONE"
    for code in BLOCKER_PRIORITY:
        if code in blockers:
            primary = code
            break

    hard_conflict = bool(conflicts)
    all_pass = direction_ready and setup_ready and confirmation_ready and risk_ready and not blockers

    if all_pass:
        decision = direction
        decision_state = "EXECUTE"
        thesis_state = "ESTABLISHED"
        setup_state = "TRADE_READY"
        confirmation_state = "PROVEN"
        risk_state = "READY"
        execution_state = "READY"
        next_event = "NONE"
    elif hard_conflict:
        decision = "NO_TRADE"
        decision_state = "REJECT"
        thesis_state = "INVALIDATED" if any("INVALIDAT" in x for x in conflicts) else "CONFLICTED"
        setup_state = "BLOCKED"
        confirmation_state = "BLOCKED"
        risk_state = "BLOCKED"
        execution_state = "BLOCKED"
        next_event = "NEW_CLOSED_CANDLE_MUST_RESOLVE_THE_DECISIVE_CONFLICT"
    else:
        decision = "NO_TRADE"
        decision_state = "WAIT_FOR_PROOF"
        thesis_state = "ESTABLISHED" if direction_ready else "UNRESOLVED"
        setup_state = "FORMING" if setup_known else "UNRESOLVED"
        confirmation_state = "PROVEN" if confirmation_ready else "PENDING"
        risk_state = "READY" if risk_ready else "BLOCKED"
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
    if all_pass:
        rationale = (
            f"{direction} executable: E6 thesis is mature, E7 confirmation is proven, "
            "and E8 economics/risk are survivable with no master conflict."
        )
    elif primary != "NONE":
        rationale = f"NO_TRADE because {primary}; E9 refuses execution until the decisive gate is resolved."
    else:
        rationale = "NO_TRADE because the master state remains unresolved."

    return {
        "decision": decision,
        "decision_state": decision_state,
        "thesis_state": thesis_state,
        "setup_state": setup_state,
        "confirmation_state": confirmation_state,
        "risk_state": risk_state,
        "execution_state": execution_state,
        "primary_blocker": primary,
        "secondary_blockers": secondary,
        "next_required_event": next_event,
        "all_gates_pass": all_pass,
        "hard_conflict": hard_conflict,
        "direction": direction,
        "setup": setup,
        "thesis": thesis,
        "e6_maturity": e6_maturity,
        "e7_confirmation": e7_confirmation,
        "e7_trigger_observed": trigger,
        "e8_risk_state": e8_risk,
        "e8_plan_valid": plan_valid,
        "rationale": rationale,
        "authority": {
            "thesis": "E6",
            "confirmation": "E7",
            "economics_risk": "E8",
            "final_decision": "E9",
        },
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Final master reconciliation.

    E9 never manufactures a setup. It resolves the evidence produced by E1-E8
    into an explicit decision lifecycle. NO_TRADE is split into REJECT versus
    WAIT_FOR_PROOF so the runtime can distinguish invalidated ideas from valid
    hypotheses that simply have not earned execution yet.
    """
    del snapshot  # E9 resolves upstream evidence; no future/raw-candle lookahead.

    e6 = _out(upstream.get("E6"))
    e7 = _out(upstream.get("E7"))
    e8 = _out(upstream.get("E8"))
    direction, setup, thesis = _e6_identity(e6)
    conflicts = _collect_conflicts(upstream)
    resolved = _resolution(direction, setup, thesis, e6, e7, e8, conflicts)

    # Preserve the evidence ledger for observability without allowing it to
    # override the authoritative lifecycle decision above.
    evidence_summary: dict[str, Any] = {}
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id)
        evidence_summary[engine_id] = {
            "finding": _out(engine).get("finding", _out(engine).get("state", "UNRESOLVED")),
            "gate_passed": engine.gate_passed if engine else None,
            "reason_codes": _codes(engine),
        }

    # Score is a decision-readiness score, not a trade-probability claim.
    score_parts = [
        25.0 if resolved["direction"] in DIRECTIONS else 0.0,
        25.0 if resolved["setup_state"] == "TRADE_READY" else 12.5 if resolved["setup_state"] == "FORMING" else 0.0,
        25.0 if resolved["confirmation_state"] == "PROVEN" else 12.5 if resolved["confirmation_state"] == "PENDING" else 0.0,
        25.0 if resolved["risk_state"] == "READY" else 0.0,
    ]
    readiness_score = round(sum(score_parts), 2)

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
        engine_id="E9",
        name=NAME,
        gate_passed=bool(resolved["all_gates_pass"]),
        score=readiness_score,
        output=output,
        reason_codes=tuple(reason_codes),
    )
