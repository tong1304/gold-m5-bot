from __future__ import annotations

import re
from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Who controls the market, does E6 thesis survive, are E7/E8 proof gates complete, and what is the final governance state?"
ARCHITECTURE = "E9_FOUR_LAYER_GOVERNANCE"
VERSION = "64.0"

DIRECTIONS = {"BUY", "SELL"}
CONFIRMATION_PROVEN = {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"}
RISK_READY_STATES = {"READY", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY", "VALIDATED", "PASS", "PASSED", "COMPLETE"}
ECONOMIC_BLOCKERS = {
    "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID",
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM",
    "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    "NO_USABLE_STRUCTURAL_TARGET", "RISK_QUALITY_BELOW_DECISION_THRESHOLD",
    "HISTORICAL_SAMPLE_INSUFFICIENT", "PROFIT_EDGE_NOT_PROVEN", "PROFIT_EXPECTANCY_UNQUANTIFIED",
}
HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
    "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED",
    "E3_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED",
}


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
                    values.append(flag)
    return _dedupe(values)


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if not x:
            continue
        if x in DIRECTIONS:
            return x
        if x in {"UP", "BULLISH", "BUYERS", "BUYER", "BUY_CONTROLLED", "BUY-CONTROLLED"}:
            return "BUY"
        if x in {"DOWN", "BEARISH", "SELLERS", "SELLER", "SELL_CONTROLLED", "SELL-CONTROLLED"}:
            return "SELL"
        if x.startswith(("BUY ", "BUY_", "BUY:", "BUY-")):
            return "BUY"
        if x.startswith(("SELL ", "SELL_", "SELL:", "SELL-")):
            return "SELL"
        if re.search(r"(?:^|[ =:;,|])(?:UP|BULLISH|BUYERS|BUYER)(?:$|[ =:;,|])", x):
            return "BUY"
        if re.search(r"(?:^|[ =:;,|])(?:DOWN|BEARISH|SELLERS|SELLER)(?:$|[ =:;,|])", x):
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
    if codes & {"NO_SURVIVING_SETUP", "NO_ELIGIBLE_SETUP", "SETUP_REJECTED", "SETUP_INVALIDATED"}:
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
    setup = ""
    for key in ("setup", "setup_family", "candidate_setup", "candidate_setup_thesis", "setup_type", "thesis_setup", "selected_hypothesis"):
        setup = _clean_setup(e6.get(key))
        if setup:
            break
    direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"), e6.get("selected_direction"))
    if not setup:
        match = re.match(r"^(BUY|SELL)\s+([A-Z][A-Z0-9_]+)\s+IS\s+A\s+CANDIDATE\s+HYPOTHESIS\s+ONLY\b", finding)
        if match:
            direction, setup = match.groups()
    if not setup:
        match = re.match(r"^(BUY|SELL)\s+([A-Z][A-Z0-9_]+)\s+IS\s+(?:VALIDATING|FORMING|A\s+CANDIDATE|READY)", finding)
        if match:
            direction, setup = match.groups()
    if not setup:
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
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
    if not engine:
        return []
    return _dedupe(_codes(_out(engine)) + list(engine.reason_codes or ()))


def _hard_conflicts(upstream: dict[str, EngineResult]) -> list[str]:
    """Only direct upstream invalidation is hard conflict; propagated E6 labels do not rewrite E3 facts."""
    found: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id)
        output = _out(engine)
        codes = _engine_codes(engine)
        if engine_id == "E3":
            for code in codes:
                if code in HARD_CONFLICT_CODES:
                    found.append(code)
            for key in ("invalidation", "thesis_state"):
                value = _text(output.get(key))
                if value.endswith("_INVALIDATED"):
                    found.append(value)
        elif engine_id in {"E6", "E7", "E8"}:
            for code in codes:
                if code in {"THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED"}:
                    found.append(code)
            for key in ("invalidation",):
                value = _text(output.get(key))
                if value.endswith("_INVALIDATED"):
                    found.append(value)
        else:
            for code in codes:
                if code in HARD_CONFLICT_CODES:
                    found.append(code)
    return _dedupe(found)


def _economic_blockers(e8: EngineResult | None) -> list[str]:
    found: list[str] = []
    for candidate in _walk(_out(e8)):
        found.extend(c for c in _codes(candidate) if c in ECONOMIC_BLOCKERS)
    return _dedupe(found)


def _market_control(upstream: dict[str, EngineResult]) -> dict[str, Any]:
    """Layer 1: market control only. It never becomes the E6 trade thesis."""
    e1, e2, e3, e4, e5 = (_out(upstream.get(k)) for k in ("E1", "E2", "E3", "E4", "E5"))
    votes: list[tuple[str, str, float]] = []

    def add(direction: str, source: str, weight: float) -> None:
        if direction in DIRECTIONS:
            votes.append((direction, source, weight))

    add(_direction(e1.get("pressure"), e1.get("pressure_direction")), "E1_PRESSURE", 3.0)
    add(_direction(e3.get("structure_direction"), e3.get("external_state"), e3.get("structure"), e3.get("finding")), "E3_STRUCTURE", 3.0)
    add(_direction(e2.get("direction"), e2.get("opportunity_direction"), e2.get("finding")), "E2_OPPORTUNITY", 2.0)
    add(_direction(e4.get("response_actor"), e4.get("auction_response"), e4.get("finding")), "E4_AUCTION_RESPONSE", 2.0)
    add(_direction(e5.get("repricing_direction"), e5.get("value_response"), e5.get("repricing_state")), "E5_REPRICING", 2.0)

    totals = {"BUY": 0.0, "SELL": 0.0}
    evidence: list[dict[str, Any]] = []
    for direction, source, weight in votes:
        totals[direction] += weight
        evidence.append({"source": source, "direction": direction, "weight": weight})

    total = totals["BUY"] + totals["SELL"]
    if total == 0:
        state, direction, confidence = "UNRESOLVED", "NEUTRAL", 0.0
    elif totals["BUY"] == totals["SELL"]:
        state, direction, confidence = "MIXED", "NEUTRAL", 50.0
    else:
        direction = "BUY" if totals["BUY"] > totals["SELL"] else "SELL"
        confidence = round(max(totals.values()) / total * 100.0, 2)
        state = f"{direction}-CONTROLLED" if confidence >= 60.0 else "MIXED"
        if state == "MIXED":
            direction = "NEUTRAL"
    evidence.sort(key=lambda x: (-x["weight"], x["source"]))
    dominant = [x for x in evidence if x["weight"] >= 3.0]
    if not dominant:
        dominant = evidence[:3]
    return {
        "market_control_state": state,
        "control_direction": direction,
        "control_confidence": confidence,
        "control_scores": {"BUY": round(totals["BUY"], 2), "SELL": round(totals["SELL"], 2)},
        "dominant_control_evidence": dominant,
        "control_evidence": evidence,
    }


def _confirmation_state(e7: dict[str, Any]) -> tuple[str, bool]:
    codes = set(_codes(e7))
    if codes & {"E7_CONFIRMATION_INVALIDATED", "CONFIRMATION_INVALIDATED"}:
        return "INVALIDATED", False
    if codes & {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"}:
        return "PENDING", False
    confirmation = _state(e7, ("confirmation_state", "confirmation", "proof_state"))
    trigger = any(e7.get(k) is True for k in ("trigger_observed", "valid_trigger", "closed_candle_trigger"))
    trigger = trigger or _state(e7, ("trigger_state", "trigger", "entry_trigger")) in CONFIRMATION_PROVEN
    proven = confirmation in CONFIRMATION_PROVEN or bool(codes & {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN", "VALID_CLOSED_CANDLE_TRIGGER", "TRIGGER_CONFIRMED"})
    return ("PROVEN" if proven and trigger else "PENDING"), bool(proven and trigger)


def _risk_state(e8: dict[str, Any]) -> tuple[str, bool, list[str]]:
    blockers = _economic_blockers(EngineResult("E8", "", False, 0.0, e8, tuple()))
    state = _state(e8, ("risk_state", "economic_state", "decision_state", "plan_status"))
    verified = bool(e8.get("verified") is True or e8.get("trade_plan_verified") is True)
    ready = state in RISK_READY_STATES and not blockers
    if blockers:
        return "BLOCKED", False, blockers
    return ("READY" if ready or verified else "UNRESOLVED"), bool(ready or verified), blockers


def _thesis_state(e3: dict[str, Any], e6: dict[str, Any]) -> str:
    lifecycle = _state(e3, ("lifecycle", "structure_lifecycle"), "UNRESOLVED")
    if lifecycle == "INVALIDATED":
        return "INVALIDATED"
    if lifecycle in {"ESTABLISHED", "MATURE", "CONFIRMED"}:
        return "ESTABLISHED"
    if _state(e6, ("thesis_state",)) in {"INVALIDATED", "REJECTED"}:
        return "INVALIDATED"
    return "UNRESOLVED"


def _setup_state(e6: dict[str, Any]) -> str:
    maturity = _state(e6, ("maturity", "setup_state", "opportunity_stage"), "UNRESOLVED")
    if maturity in {"HYPOTHESIS", "CANDIDATE", "FORMING"}:
        return "HYPOTHESIS"
    if maturity in {"VALIDATING", "VALIDATING_SETUP", "DEVELOPING"}:
        return "VALIDATING"
    if maturity in {"MATURE", "TRADE_READY", "VALIDATED", "CONFIRMED"}:
        return "MATURE"
    finding = _text(e6.get("finding"))
    if "CANDIDATE HYPOTHESIS ONLY" in finding:
        return "HYPOTHESIS"
    if "IS VALIDATING" in finding:
        return "VALIDATING"
    return "UNRESOLVED"


def _plan_valid(e8: dict[str, Any], direction: str) -> bool:
    plan = e8.get("trade_plan") if isinstance(e8.get("trade_plan"), dict) else e8
    if direction not in DIRECTIONS:
        return False
    try:
        entry = float(plan["entry"])
        stop = float(plan["stop_loss"])
        target = float(plan.get("take_profit_2", plan.get("take_profit", plan.get("tp2"))))
    except (KeyError, TypeError, ValueError):
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


def _alignment(control: dict[str, Any], thesis_direction: str) -> tuple[str, str]:
    control_direction = control["control_direction"]
    if thesis_direction not in DIRECTIONS or control_direction not in DIRECTIONS:
        return "UNRESOLVED", "NO_DIRECTIONAL_ALIGNMENT_PROVEN"
    if control_direction == thesis_direction:
        return "ALIGNED", "MARKET_CONTROL_SUPPORTS_E6_THESIS"
    return "CONFLICTED", "MARKET_CONTROL_OPPOSES_E6_THESIS"


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Four-layer E9 governance: market control -> E6 thesis ownership -> E7/E8 proof -> final authority."""
    del snapshot
    e1, e3, e4, e5 = (_out(upstream.get(k)) for k in ("E1", "E3", "E4", "E5"))
    e6, e7, e8 = (_out(upstream.get(k)) for k in ("E6", "E7", "E8"))

    control = _market_control(upstream)
    thesis_direction, setup, thesis_text = _e6_identity(e6)
    thesis_state = _thesis_state(e3, e6)
    setup_state = _setup_state(e6)
    confirmation_state, confirmation_proven = _confirmation_state(e7)
    economic_state, economic_ready, economic_blockers = _risk_state(e8)
    hard_conflicts = _hard_conflicts(upstream)
    alignment, alignment_reason = _alignment(control, thesis_direction)

    if hard_conflicts:
        evidence_alignment = "CONFLICTED"
    elif alignment == "ALIGNED":
        evidence_alignment = "ALIGNED"
    elif alignment == "CONFLICTED":
        evidence_alignment = "CONFLICTED"
    elif thesis_direction in DIRECTIONS:
        evidence_alignment = "PARTIALLY_ALIGNED"
    else:
        evidence_alignment = "UNRESOLVED"

    # Proof gates are sequential. E7 cannot be bypassed by E8; E8 cannot be bypassed by market control.
    all_gates_pass = (
        thesis_direction in DIRECTIONS
        and setup not in {"", "UNKNOWN"}
        and setup_state == "MATURE"
        and confirmation_proven
        and economic_ready
        and _plan_valid(e8, thesis_direction)
        and not hard_conflicts
        and not economic_blockers
    )

    if hard_conflicts:
        governance_decision = "REJECTED_HARD_CONFLICT"
        legacy_decision = "NO_TRADE"
        governance_reason = "HARD_CONFLICT_BLOCKS_EXECUTION"
    elif not thesis_direction or thesis_direction not in DIRECTIONS or setup in {"", "UNKNOWN"}:
        governance_decision = "WAIT_FOR_PROOF"
        legacy_decision = "NO_TRADE"
        governance_reason = "E6_THESIS_NOT_ACTIONABLE"
    elif all_gates_pass:
        governance_decision = "EXECUTE"
        legacy_decision = thesis_direction
        governance_reason = "ALL_FOUR_GOVERNANCE_LAYERS_PASSED"
    else:
        governance_decision = "WAIT_FOR_PROOF"
        legacy_decision = "NO_TRADE"
        missing = []
        if setup_state != "MATURE": missing.append("E6_SETUP_NOT_MATURE")
        if not confirmation_proven: missing.append("E7_CONFIRMATION_REQUIRED")
        if not economic_ready: missing.append("E8_TRADE_ECONOMICS_REQUIRED")
        if not _plan_valid(e8, thesis_direction): missing.append("TRADE_PLAN_NOT_VALID")
        if alignment == "CONFLICTED": missing.append("MARKET_CONTROL_THESIS_CONFLICT")
        governance_reason = missing[0] if missing else "PROOF_GATES_INCOMPLETE"

    reason_codes = [
        "E9_FOUR_LAYER_GOVERNANCE",
        "MARKET_CONTROL_SYNTHESIZED",
        "E6_THESIS_OWNER",
        "E7_SETUP_SPECIFIC_PROOF_REQUIRED",
        "E8_TRADE_ECONOMICS_REQUIRED",
        governance_reason,
    ]
    if alignment == "CONFLICTED":
        reason_codes.append("MARKET_CONTROL_THESIS_CONFLICT")
    if economic_blockers:
        reason_codes.extend(economic_blockers)
    reason_codes.extend(hard_conflicts)
    if not confirmation_proven:
        reason_codes.append("WAITING_FOR_E7_PROOF")
    if not economic_ready:
        reason_codes.append("WAITING_FOR_E8_ECONOMICS")

    auction = {
        "event": _text(e4.get("event") or e4.get("auction_event") or e4.get("liquidity_event") or "UNRESOLVED"),
        "auction_state": _text(e4.get("auction_state") or "UNRESOLVED"),
        "liquidity_taker": _text(e4.get("liquidity_taker") or "UNCLEAR"),
        "response_actor": _text(e4.get("response_actor") or "UNCLEAR"),
    }
    output = {
        "decision": legacy_decision,
        "final_governance": governance_decision,
        "governance_decision": governance_decision,
        "governance_reason": governance_reason,
        "execution_state": "APPROVED" if governance_decision == "EXECUTE" else "BLOCKED",
        "all_gates_pass": all_gates_pass,
        "direction": thesis_direction if thesis_direction in DIRECTIONS else "NEUTRAL",
        "thesis_direction": thesis_direction,
        "setup": setup,
        "thesis": thesis_text,
        "thesis_state": thesis_state,
        "setup_state": setup_state,
        "confirmation_state": confirmation_state,
        "economic_state": economic_state,
        "economic_blockers": economic_blockers,
        "hard_conflicts": hard_conflicts,
        "market_control_state": control["market_control_state"],
        "control_direction": control["control_direction"],
        "control_confidence": control["control_confidence"],
        "control_scores": control["control_scores"],
        "control_evidence": control["control_evidence"],
        "dominant_control_evidence": control["dominant_control_evidence"],
        "evidence_alignment": evidence_alignment,
        "evidence_alignment_reason": alignment_reason,
        "auction": auction,
        "governance_layers": {
            "market_control": "MARKET_CONTROL",
            "thesis_control": "E6_OWNER",
            "proof_control": "E7_CONFIRMATION_AND_E8_ECONOMICS",
            "final_governance": "E9_FINAL_AUTHORITY",
        },
        "authority_contract": {
            "market_bias_owner": "E1-E5_MARKET_EVIDENCE",
            "trade_thesis_owner": "E6",
            "setup_proof_owner": "E7",
            "trade_economics_owner": "E8",
            "final_decision_owner": "E9",
            "e9_may_rewrite_e6_thesis": False,
            "e9_may_bypass_e7": False,
            "e9_may_bypass_e8": False,
        },
        "proof_gates": {
            "e6_thesis_present": thesis_direction in DIRECTIONS and setup not in {"", "UNKNOWN"},
            "e7_confirmation_proven": confirmation_proven,
            "e8_economics_ready": economic_ready,
            "hard_conflict_clear": not hard_conflicts,
            "trade_geometry_valid": _plan_valid(e8, thesis_direction),
        },
        "market_control_explanation": {
            "who_controls_market": control["market_control_state"],
            "control_direction": control["control_direction"],
            "confidence": control["control_confidence"],
            "why_not_trade": governance_reason,
            "dominant_evidence": control["dominant_control_evidence"],
        },
        "opportunity_state": "WATCH" if governance_decision == "WAIT_FOR_PROOF" else ("REJECTED" if governance_decision == "REJECTED_HARD_CONFLICT" else "EXECUTE"),
        "opportunity": {
            "direction": thesis_direction,
            "setup": setup,
            "state": governance_decision,
            "do_not_execute": governance_decision != "EXECUTE",
            "economic_blockers": economic_blockers,
        },
        "reason_codes": _dedupe(reason_codes),
        "reasons": _dedupe(reason_codes),
        "architecture": ARCHITECTURE,
        "version": VERSION,
    }
    score = float(control["control_confidence"])
    gate_passed = governance_decision == "EXECUTE"
    return EngineResult("E9", NAME, gate_passed, score, output, tuple(output["reason_codes"]))
