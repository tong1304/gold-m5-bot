from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Who controls the auction, where is liquidity, and should this trade be taken after reconciling all evidence?"
ARCHITECTURE = "E9_MASTER_DECISION_MARKET_CONTROL_V59"
VERSION = "59.0"

DIRECTIONS = {"BUY", "SELL"}
CONFIRMATION_PROVEN = {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"}
MATURITY_READY = {"MATURE", "TRADE_READY", "VALIDATED", "CONFIRMED"}
RISK_READY_STATES = {"READY", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY", "VALIDATED", "PASS", "PASSED", "COMPLETE"}
ECONOMIC_BLOCKERS = {
    "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID",
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET",
    "RISK_QUALITY_BELOW_DECISION_THRESHOLD",
}
HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
    "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED",
    "E3_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED",
}
BLOCKER_PRIORITY = (
    "THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED",
    "E8_RISK_INVALIDATED", "E3_STRUCTURE_INVALIDATED", "STRUCTURE_INVALIDATED",
    "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED",
    "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT", "OPPOSING_LIQUIDITY_THESIS",
    "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT", "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY",
    "RISK_GEOMETRY_INVALID", "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH",
    "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET", "ENTRY_CONFIRMATION_NOT_PROVEN",
    "SETUP_NOT_MATURE", "RISK_NOT_READY", "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "DIRECTION_UNRESOLVED",
)


def _out(engine: EngineResult | None) -> dict[str, Any]:
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _text(value)
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _codes(output: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "risk_blockers", "economic_blockers", "conflicts", "invalidations"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif isinstance(value, dict):
            for name, flag in value.items():
                if flag is True:
                    values.append(name)
                elif flag not in (None, "", False):
                    values.append(name if isinstance(flag, bool) else flag)
    return _dedupe(values)


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS:
            return x
        if x.startswith(("BUY ", "BUY_", "BUY:")) or x in {"UP", "BULLISH"}:
            return "BUY"
        if x.startswith(("SELL ", "SELL_", "SELL:")) or x in {"DOWN", "BEARISH"}:
            return "SELL"
    return "NEUTRAL"


def _clean_setup(value: Any) -> str:
    text = _text(value)
    return "" if text in {"", "UNKNOWN", "NONE", "NO_SETUP", "NO SETUP", "UNRESOLVED"} else text


def _e6_identity(e6: dict[str, Any]) -> tuple[str, str, str]:
    finding = _text(e6.get("finding"))
    codes = set(_codes(e6))
    if "NO PLAUSIBLE SETUP SURVIVES" in finding or "NO SURVIVING SETUP" in finding:
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
    if {"DIRECTIONAL_EVIDENCE_CONFLICT", "SPACE_CONFLICT"}.issubset(codes):
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
    if any(c in codes for c in {"NO_SURVIVING_SETUP", "NO_ELIGIBLE_SETUP", "SETUP_REJECTED", "SETUP_INVALIDATED"}):
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
    setup = ""
    for key in ("setup", "setup_family", "candidate_setup", "candidate_setup_thesis", "setup_type", "thesis_setup", "selected_hypothesis"):
        setup = _clean_setup(e6.get(key))
        if setup:
            break
    if not setup:
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
    direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"), e6.get("selected_direction"), finding)
    thesis = str(e6.get("thesis") or e6.get("candidate_setup_thesis") or e6.get("selected_hypothesis") or finding or "UNRESOLVED").strip()
    return direction, setup, thesis or "UNRESOLVED"


def _state(output: dict[str, Any], keys: tuple[str, ...], default: str = "UNRESOLVED") -> str:
    for key in keys:
        if output.get(key) not in (None, ""):
            return _text(output[key])
    return default


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _walk(child)


def _engine_codes(engine: EngineResult | None) -> list[str]:
    return _dedupe(_codes(_out(engine)) + list(engine.reason_codes or ()) if engine else [])


def _e8_boundary(e8: EngineResult | None) -> tuple[dict[str, Any], dict[str, Any]]:
    boundary: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    for candidate in _walk(_out(e8)):
        nested = candidate.get("trade_plan")
        if isinstance(nested, dict):
            plan.update(nested)
        for key in ("risk_gate", "risk_state", "economic_state", "decision_state", "plan_status", "risk_quality", "verified", "trade_plan_verified"):
            if key in candidate:
                boundary[key] = candidate[key]
    return boundary, plan


def _confirmation(e7: dict[str, Any]) -> tuple[str, bool]:
    codes = set(_codes(e7))
    if codes & {"E7_CONFIRMATION_INVALIDATED", "CONFIRMATION_INVALIDATED"}:
        return "INVALIDATED", False
    if codes & {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"}:
        return "PENDING", False
    proven = bool(codes & {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN", "VALID_CLOSED_CANDLE_TRIGGER", "TRIGGER_CONFIRMED"})
    proven = proven or _state(e7, ("confirmation_state", "confirmation", "proof_state")) in CONFIRMATION_PROVEN
    trigger = any(e7.get(k) is True for k in ("trigger_observed", "valid_trigger", "closed_candle_trigger"))
    trigger = trigger or _state(e7, ("trigger_state", "trigger", "entry_trigger")) in CONFIRMATION_PROVEN
    return ("PROVEN" if proven and trigger else "PENDING"), bool(proven and trigger)


def _plan_valid(plan: dict[str, Any], direction: str) -> bool:
    if direction not in DIRECTIONS:
        return False
    try:
        entry = float(plan["entry"])
        stop = float(plan["stop_loss"])
        target = float(plan.get("take_profit_2", plan.get("take_profit", plan.get("tp2"))))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(v == v for v in (entry, stop, target)):
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


def _hard_conflicts(upstream: dict[str, EngineResult]) -> list[str]:
    found: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id)
        for code in _engine_codes(engine):
            if code in HARD_CONFLICT_CODES:
                found.append(code)
        for key in ("state", "finding", "lifecycle", "invalidation", "structure_state", "thesis_state"):
            value = _text(_out(engine).get(key))
            if value in HARD_CONFLICT_CODES or value.endswith("_INVALIDATED") or "THESIS_INVALIDATED" in value:
                found.append(value)
    return _dedupe(found)


def _economic_blockers(e8: EngineResult | None) -> list[str]:
    found: list[str] = []
    for candidate in _walk(_out(e8)):
        found.extend(c for c in _codes(candidate) if c in ECONOMIC_BLOCKERS)
    return _dedupe(found)


def _auction_fields(e4: dict[str, Any]) -> dict[str, Any]:
    event = e4.get("event") or e4.get("auction_event") or e4.get("liquidity_event") or ""
    return {
        "auction_event": _text(event),
        "auction_event_detail": event if isinstance(event, (dict, list, tuple)) else None,
        "auction_state": _text(e4.get("auction_state") or "UNRESOLVED"),
        "liquidity_taker": _text(e4.get("liquidity_taker") or "UNCLEAR"),
        "response_actor": _text(e4.get("response_actor") or "UNCLEAR"),
        "liquidity_type": _text(e4.get("liquidity_type") or "UNKNOWN"),
        "liquidity_externality": _text(e4.get("liquidity_externality") or "UNKNOWN"),
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> dict[str, Any]:
    """E9 is the final market-control governor; it never invents a setup or confirmation."""
    del snapshot
    e6 = _out(upstream.get("E6")); e7 = _out(upstream.get("E7")); e4 = _out(upstream.get("E4")); e8_engine = upstream.get("E8")
    direction, setup, thesis = _e6_identity(e6)
    maturity = _state(e6, ("maturity", "setup_maturity", "setup_stage", "stage", "formation_stage", "lifecycle"))
    confirmation, confirmation_ready = _confirmation(e7)
    boundary, plan = _e8_boundary(e8_engine)
    economic = _economic_blockers(e8_engine)
    conflicts = _hard_conflicts(upstream)
    direction_ready = direction in DIRECTIONS
    setup_ready = direction_ready and setup != "UNKNOWN" and maturity in MATURITY_READY
    risk_state = _text(boundary.get("risk_gate") or boundary.get("risk_state") or boundary.get("economic_state") or boundary.get("plan_status") or "UNRESOLVED")
    risk_ready = not economic and risk_state in RISK_READY_STATES and _plan_valid(plan, direction)

    blockers = _dedupe(conflicts + economic)
    if not direction_ready: blockers.append("DIRECTION_UNRESOLVED")
    if not setup_ready: blockers.append("SETUP_NOT_MATURE")
    if not confirmation_ready: blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not risk_ready: blockers.append("RISK_NOT_READY")
    blockers = _dedupe(blockers)
    primary = next((code for code in BLOCKER_PRIORITY if code in blockers), "NONE")
    all_pass = direction_ready and setup_ready and confirmation_ready and risk_ready and not conflicts and not economic

    if all_pass:
        decision = direction
        decision_state = master_state = "EXECUTE"
        thesis_state, setup_state, risk_final, execution_state = "ESTABLISHED", "TRADE_READY", "READY", "READY"
    elif conflicts:
        decision = "NO_TRADE"
        decision_state = "REJECT"
        master_state = "REJECTED_HARD_CONFLICT"
        thesis_state = "INVALIDATED" if any("INVALIDAT" in x for x in conflicts) else "CONFLICTED"
        setup_state = risk_final = execution_state = "BLOCKED"
    else:
        decision = "NO_TRADE"
        decision_state = master_state = "WAIT_FOR_PROOF"
        thesis_state = "ESTABLISHED" if direction_ready and setup != "UNKNOWN" else "UNRESOLVED"
        setup_state = maturity if setup != "UNKNOWN" and maturity not in {"", "UNKNOWN", "UNRESOLVED", "NONE"} else "FORMING"
        risk_final = "READY" if risk_ready else "BLOCKED"
        execution_state = "BLOCKED"

    next_required = {
        "DIRECTION_UNRESOLVED": "E6_MUST_ESTABLISH_A_DIRECTIONAL_THESIS_AND_SETUP",
        "SETUP_NOT_MATURE": "E6_SETUP_MUST_REACH_MATURE_OR_TRADE_READY",
        "ENTRY_CONFIRMATION_NOT_PROVEN": "E7_MUST_PROVE_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION",
        "RISK_NOT_READY": "E8_MUST_PROVE_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS",
    }.get(primary, "NONE" if all_pass else "NEW_CLOSED_CANDLE_MUST_RESOLVE_THE_DECISIVE_CONFLICT")
    auction = _auction_fields(e4)

    return {
        "decision": decision,
        "decision_state": decision_state,
        "master_state": master_state,
        "thesis_state": thesis_state,
        "setup_state": setup_state,
        "confirmation_state": "PROVEN" if confirmation_ready else confirmation,
        "risk_state": risk_final,
        "execution_state": execution_state,
        "primary_blocker": primary,
        "primary_blocker_class": (
            "CONFLICT" if primary in conflicts else
            "ECONOMICS" if primary in economic else
            "DIRECTION" if primary == "DIRECTION_UNRESOLVED" else
            "SETUP" if primary == "SETUP_NOT_MATURE" else
            "CONFIRMATION" if primary == "ENTRY_CONFIRMATION_NOT_PROVEN" else
            "RISK" if primary == "RISK_NOT_READY" else "NONE"
        ),
        "secondary_blockers": [x for x in blockers if x != primary],
        "blocker_count": len(blockers),
        "next_required_event": next_required,
        "all_gates_pass": all_pass,
        "hard_conflict": bool(conflicts),
        "resolved_conflicts": conflicts,
        "counter_evidence": [],
        "direction": direction,
        "setup": setup,
        "thesis": thesis,
        "e6_maturity": maturity,
        "e6_identity_resolved": direction_ready and setup != "UNKNOWN",
        "e6_maturity_known": maturity not in {"", "UNKNOWN", "UNRESOLVED", "NONE"},
        "e7_confirmation": confirmation,
        "e7_trigger_observed": confirmation_ready,
        "e8_risk_state": risk_state,
        "e8_plan_valid": _plan_valid(plan, direction),
        "e8_economic_blockers": economic,
        "trade_plan": plan if _plan_valid(plan, direction) else {},
        **auction,
        "invalidation_lifecycle": {
            "state": "NONE" if setup != "UNKNOWN" else "NO_SETUP",
            "event": "THESIS_ACTIVE" if setup_ready else "NO_SURVIVING_SETUP" if setup == "UNKNOWN" else "SETUP_FORMING",
            "active": False,
            "recovery": next_required,
        },
        "authority": {
            "thesis": "E6",
            "confirmation": "E7",
            "economics_risk": "E8",
            "market_control": "E9",
            "final_decision": "E9",
        },
        "resolution_order": ["THESIS_IDENTITY", "MARKET_CONTROL", "HARD_CONFLICT", "SETUP_MATURITY", "CONFIRMATION", "RISK_ECONOMICS", "EXECUTION"],
        "governance_invariants": {
            "e9_cannot_invent_setup": True,
            "e9_cannot_invent_confirmation": True,
            "e9_cannot_promote_market_bias_to_thesis": True,
            "e9_requires_closed_candle_evidence": True,
            "e9_requires_valid_trade_geometry": True,
        },
    }
