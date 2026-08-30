from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Should this trade be taken after reconciling all relevant evidence?"
DIRECTIONS = {"BUY", "SELL"}

# These are the only evidence codes that can become E9 hard conflicts.
# Lifecycle observations such as INVALIDATION_EVALUATED are deliberately not
# hard conflicts, and E6 DIRECTIONAL_EVIDENCE_CONFLICT remains visible evidence.
HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
}
ECONOMIC_HARD_CODES = {
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW",
    "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID", "NO_USABLE_STRUCTURAL_TARGET",
}

# Master-decision priority is deliberately ordered: an explicit contradiction
# or execution/economic failure outranks a generic lifecycle observation.
MASTER_BLOCKER_PRIORITY = (
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
    "INVALID_TRADE_GEOMETRY", "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH",
    "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE",
    "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM",
    "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET",
    "ENTRY_CONFIRMATION_NOT_PROVEN", "SETUP_NOT_MATURE", "RISK_NOT_READY",
    "ECONOMIC_EDGE_TOO_THIN", "ECONOMIC_MARGIN_TOO_THIN",
    "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "DIRECTION_UNRESOLVED",
)


def _out(e: EngineResult | None) -> dict[str, Any]:
    return dict(e.output) if e else {}


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _num(v: Any, default: float | None = None) -> float | None:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _codes(o: dict[str, Any]) -> list[str]:
    vals = o.get("reason_codes") or o.get("reasons") or o.get("counter_evidence") or []
    if isinstance(vals, str): vals = [vals]
    return [_text(v) for v in vals if v]


def _engine_codes(e: EngineResult | None) -> list[str]:
    if not e: return []
    return list(dict.fromkeys(_codes(_out(e)) + [_text(v) for v in (e.reason_codes or ()) if v]))


def _finding(o: dict[str, Any]) -> str:
    return _text(o.get("finding", o.get("state", o.get("market_state", "UNRESOLVED"))))


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS: return x
        if any(k in x for k in ("BULLISH", "UP", "LONG", "BUYERS", "TREND_UP")): return "BUY"
        if any(k in x for k in ("BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN")): return "SELL"
    return "NEUTRAL"


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _e6_identity(e6: dict[str, Any]) -> tuple[str, str, str]:
    raw = str(e6.get("finding", "")).strip()
    setup = str(e6.get("setup", e6.get("setup_family", ""))).strip()
    thesis = str(e6.get("thesis", e6.get("candidate_setup_thesis", ""))).strip()
    direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"), raw)
    if (not setup or _text(setup) in {"UNKNOWN", "NONE", "NO_SETUP"}) and raw:
        head = raw.split(" is ", 1)[0].strip()
        if _direction(head) in DIRECTIONS:
            prefix = f"{_direction(head)} "
            setup = head[len(prefix):].strip() if _text(head).startswith(prefix) else head
    if not thesis: thesis = raw or "UNRESOLVED"
    return direction if direction in DIRECTIONS else "NEUTRAL", setup or "UNKNOWN", thesis


def _plan_is_structurally_valid(plan: dict[str, Any], direction: str) -> bool:
    if not isinstance(plan, dict) or direction not in DIRECTIONS: return False
    try:
        entry = float(plan["entry"]); stop = float(plan["stop_loss"]); tp2 = float(plan["take_profit_2"])
    except (KeyError, TypeError, ValueError): return False
    if not all(x == x for x in (entry, stop, tp2)): return False
    if direction == "BUY" and not (stop < entry < tp2): return False
    if direction == "SELL" and not (tp2 < entry < stop): return False
    rr = _num(plan.get("rr_tp2"))
    return rr is None or rr >= 1.50


def _market_control(e4: dict[str, Any], e5: dict[str, Any], direction: str, setup: str, thesis: str) -> dict[str, Any]:
    taker = _text(e4.get("liquidity_taker")); responder = _text(e4.get("response_actor"))
    auction_state = _text(e4.get("auction_state")); finding = _finding(e4)
    level = e4.get("event_level", e4.get("level", e4.get("liquidity_level")))
    blob = f"{finding} {_codes(e4)}"
    rejection = any(k in blob for k in ("REJECTION", "REJECTED", "FAILED_BREAK", "RECLAIM", "SWEEP"))
    pending = auction_state in {"PENDING", "UNRESOLVED", "DEVELOPING", "WATCH"} or any(k in blob for k in ("NOT_TERMINALLY_CONFIRMED", "TRUE_AUCTION_CONFIRMATION_NOT_PROVEN", "LOW_INFORMATION"))
    controller = "UNPROVEN"; side = "NONE"
    if taker in {"BUYERS", "SELLERS"} and responder in {"BUYERS", "SELLERS"} and taker != responder and rejection:
        controller = responder; side = "BUY" if responder == "BUYERS" else "SELL"
    elif responder in {"BUYERS", "SELLERS"} and rejection:
        controller = responder; side = "BUY" if responder == "BUYERS" else "SELL"
    ef = _finding(e5)
    acceptance = _text(e5.get("value_response_direction", e5.get("repricing_direction")))
    if "ACCEPTED_BELOW_VALUE" in ef or "ACCEPTANCE_BELOW" in ef: acceptance = "SELL"
    elif "ACCEPTED_ABOVE_VALUE" in ef or "ACCEPTANCE_ABOVE" in ef: acceptance = "BUY"
    aligned = side in DIRECTIONS and side == acceptance
    terminal = bool(responder in {"BUYERS", "SELLERS"} and rejection and not pending)
    chain_complete = bool(taker in {"BUYERS", "SELLERS"} and responder in {"BUYERS", "SELLERS"} and taker != responder and rejection and level is not None and terminal and aligned)
    strength = 0.0
    strength += 15 if taker in {"BUYERS", "SELLERS"} else 0
    strength += 20 if responder in {"BUYERS", "SELLERS"} else 0
    strength += 20 if rejection else 0
    strength += 15 if taker in {"BUYERS", "SELLERS"} and responder in {"BUYERS", "SELLERS"} and taker != responder else 0
    strength += 15 if terminal else 0
    strength += 10 if aligned else 0
    strength -= 20 if pending else 0
    if not chain_complete: strength = min(strength, 74.0)
    strength = max(0.0, min(100.0, strength))
    return {
        "state": "CONTROL_ESTABLISHED" if chain_complete else "CONTROL_FORMING" if controller != "UNPROVEN" else "CONTROL_UNPROVEN",
        "strength": round(strength, 2), "dominant_actor": controller, "controlled_side": side,
        "trapped_side": "SELL" if side == "BUY" and terminal else "BUY" if side == "SELL" and terminal else "NONE",
        "liquidity_target": level if level is not None else "UNPROVEN",
        "market_intent": f"REPRICING_{side}" if side in DIRECTIONS else "DIRECTIONAL_CONTROL_UNPROVEN",
        "repricing_direction": side if side in DIRECTIONS else "NEUTRAL",
        "auction_phase": "TERMINAL_RESPONSE" if terminal else "LIQUIDITY_INTERACTION" if finding else "UNRESOLVED",
        "directional_evidence": {"direction_from_e6": direction},
        "participant_chain": {"liquidity_taker": taker or "UNPROVEN", "response_actor": responder or "UNPROVEN", "controller_role": controller, "event_level": level, "chain_complete": chain_complete, "causal_order": ["LIQUIDITY", "PARTICIPANT_BEHAVIOR", "TRAP", "REPRICING", "TARGET"]},
        "evidence": ["LIQUIDITY_EVENT_OBSERVED"] if finding else [],
        "warnings": [] if chain_complete else ["MARKET_CONTROL_CHAIN_INCOMPLETE"],
        "conflicts": [], "thesis": thesis, "setup": setup, "reporting_only": True, "cannot_override_execution_gates": True,
    }


def _master_decision_resolution(
    direction: str,
    setup: str,
    thesis: str,
    maturity: str,
    confirmation: str,
    trigger_observed: bool,
    risk_gate: str,
    plan_structural: bool,
    economics_ready: bool,
    reasons: list[str],
    conflicts: list[str],
) -> dict[str, Any]:
    """Resolve E9 into an explicit master state, blocker hierarchy and next event.

    E9 does not invent a thesis. E6 owns thesis identity, E7 owns proof and E8
    owns economic survivability. This helper only reconciles those authorities.
    """
    hard = _dedupe(conflicts + [r for r in reasons if r in MASTER_BLOCKER_PRIORITY])
    direction_ready = direction in DIRECTIONS
    setup_known = setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
    setup_ready = direction_ready and setup_known and maturity in {"MATURE", "TRADE_READY", "VALIDATED"}
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"} and trigger_observed
    risk_ready = risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY"} and plan_structural and economics_ready
    all_pass = direction_ready and setup_ready and confirmation_ready and risk_ready and not hard

    blocker_set = set(hard)
    if not direction_ready: blocker_set.add("DIRECTION_UNRESOLVED")
    if not setup_ready: blocker_set.add("SETUP_NOT_MATURE")
    if not confirmation_ready: blocker_set.add("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not risk_ready: blocker_set.add("RISK_NOT_READY")

    primary = "NONE"
    for code in MASTER_BLOCKER_PRIORITY:
        if code in blocker_set:
            primary = code
            break

    if all_pass:
        decision = direction
        decision_state = "EXECUTE"
        thesis_state = "ESTABLISHED"
        setup_state = "TRADE_READY"
        confirmation_state = "PROVEN"
        risk_state = "READY"
        execution_state = "READY"
        next_event = "NONE"
    elif conflicts or any(c in hard for c in HARD_CONFLICT_CODES):
        decision = "NO_TRADE"
        decision_state = "REJECT"
        thesis_state = "INVALIDATED" if any("INVALIDAT" in c for c in hard) else "CONFLICTED"
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
        execution_state = "READY" if all_pass else "BLOCKED"
        if primary == "DIRECTION_UNRESOLVED":
            next_event = "E6_MUST_ESTABLISH_A_DIRECTIONAL_THESIS_AND_SETUP"
        elif primary == "SETUP_NOT_MATURE":
            next_event = "E6_SETUP_MUST_REACH_MATURE_OR_TRADE_READY"
        elif primary == "ENTRY_CONFIRMATION_NOT_PROVEN":
            next_event = "E7_MUST_PROVE_THE_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"
        elif primary == "RISK_NOT_READY":
            next_event = "E8_MUST_PROVE_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS"
        else:
            next_event = "NEW_CLOSED_CANDLE_MUST_REMOVE_THE_PRIMARY_BLOCKER"

    secondary = [x for x in _dedupe(hard + list(blocker_set)) if x != primary]
    if all_pass:
        rationale = f"{direction} is executable: E6 thesis, E7 confirmation and E8 economics all pass without hard conflict."
    elif primary:
        rationale = f"NO_TRADE because {primary}; E9 will not promote the thesis to execution until that gate is resolved."
    else:
        rationale = "NO_TRADE because the master decision state is unresolved."

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
        "thesis": thesis,
        "setup": setup,
        "direction": direction,
        "rationale": rationale,
        "authority": {"thesis": "E6", "confirmation": "E7", "economics": "E8", "final_decision": "E9"},
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E9 master reconciliation and final decision authority.

    E6 owns thesis identity, E7 owns confirmation, E8 owns economics.
    Lifecycle/evidence labels are not treated as invalidation unless an exact
    hard-conflict code is present. E9 reconciles those authorities and exposes
    one explicit master decision state, primary blocker and next required event.
    """
    e = [_out(upstream.get(f"E{i}")) for i in range(1, 9)]
    e1, e2, e3, e4, e5, e6, e7, e8 = e
    reasons: list[str] = []; conflicts: list[str] = []; supports: list[str] = []; counter: list[str] = []
    direction, setup, thesis = _e6_identity(e6)
    trigger_dir = _direction(e7.get("direction"), e7.get("confirmation_direction"))
    risk_dir = _direction(e8.get("direction"), e8.get("risk_direction"))
    maturity = _text(e6.get("maturity", e6.get("stage", "UNRESOLVED")))
    confirmation = _text(e7.get("confirmation", e7.get("confirmation_state", "UNRESOLVED")))
    risk_gate = _text(e8.get("risk_gate", e8.get("finding", "RISK_NOT_READY")))
    plan = e8.get("trade_plan") or {}

    if direction in DIRECTIONS:
        if trigger_dir in DIRECTIONS and trigger_dir != direction: conflicts.append("E7:DIRECTION_OPPOSES_E6")
        if risk_dir in DIRECTIONS and risk_dir != direction: conflicts.append("E8:DIRECTION_OPPOSES_E6")

    setup_ready = direction in DIRECTIONS and setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"} and maturity in {"MATURE", "TRADE_READY", "VALIDATED"}
    trigger_observed = bool(e7.get("trigger_observed") or e7.get("closed_candle_trigger") or e7.get("confirmation_proven"))
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"} and trigger_observed
    plan_structural = _plan_is_structurally_valid(plan, direction)
    plan_ready = plan_structural and (bool(plan.get("valid") or plan.get("verified")) or not plan)
    economics_ready = risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY"} and plan_ready

    if not setup_ready: reasons.append("SETUP_NOT_MATURE" if direction in DIRECTIONS else "DIRECTION_UNRESOLVED")
    if not confirmation_ready: reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready: reasons.append("RISK_NOT_READY")
    if plan and not plan_structural: reasons.append("INVALID_TRADE_GEOMETRY")

    # Exact-code matching only. Never use substring checks such as 'INVALIDAT'.
    for i, eo in enumerate(e, 1):
        f = _finding(eo)
        if f not in {"", "UNRESOLVED", "UNKNOWN", "NONE", "NO_TRADE", "NO_SETUP"}: supports.append(f"E{i}:{f}")
        for code in _codes(eo):
            if code in HARD_CONFLICT_CODES: conflicts.append(f"E{i}:{code}")
            elif code in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN", "FOLLOW_THROUGH_PROVEN"}: supports.append(f"E{i}:{code}")
            else: counter.append(f"E{i}:{code}")

    # Directional disagreement is evidence, not automatic thesis invalidation.
    for i, eo in enumerate(e[:5], 1):
        d = _direction(eo.get("direction"), eo.get("opportunity_direction"), eo.get("thesis_direction"), eo.get("structure_direction"), eo.get("bias"), eo.get("repricing_direction"))
        if d in DIRECTIONS and direction in DIRECTIONS and d != direction: counter.append(f"E{i}:DIRECTION_COUNTER_EVIDENCE_{d}_VS_{direction}")

    mc = _market_control(e4, e5, direction, setup, thesis)
    counter.extend(f"E9:{x}" for x in mc["warnings"])
    if mc["state"] == "CONTROL_ESTABLISHED": supports.append("E9:MARKET_CONTROL_ESTABLISHED")
    elif mc["state"] == "CONTROL_FORMING": supports.append("E9:MARKET_CONTROL_FORMING")
    else: counter.append("E9:MARKET_CONTROL_UNPROVEN")

    rr = _num(e8.get("real_rr", e8.get("rr_used"))); edge = _num(e8.get("economic_edge_r", e8.get("expected_value_r")))
    margin = _num(e8.get("economic_margin")); probability = _num(e8.get("stress_probability", e8.get("probability")))
    rq = e8.get("risk_quality", {}); risk_quality = _num(rq.get("score")) if isinstance(rq, dict) else _num(rq)
    if rr is not None and rr < 1.50: reasons.append("REAL_RR_BELOW_MINIMUM")
    if edge is not None and edge < 0.10: reasons.append("ECONOMIC_EDGE_TOO_THIN")
    if margin is not None and margin < 0.05: reasons.append("ECONOMIC_MARGIN_TOO_THIN")
    if probability is not None and probability < 0.50: reasons.append("STRESSED_PROBABILITY_BELOW_MINIMUM")
    if risk_quality is not None and risk_quality < 0.68: reasons.append("RISK_QUALITY_BELOW_DECISION_THRESHOLD")
    for code in _engine_codes(upstream.get("E8")):
        if code in ECONOMIC_HARD_CODES: reasons.append(code)

    reasons = _dedupe(reasons); conflicts = _dedupe(conflicts); supports = _dedupe(supports); counter = _dedupe(counter)
    hard_vetoes = _dedupe(reasons + conflicts)
    resolution = _master_decision_resolution(
        direction=direction, setup=setup, thesis=thesis, maturity=maturity,
        confirmation=confirmation, trigger_observed=trigger_observed,
        risk_gate=risk_gate, plan_structural=plan_structural,
        economics_ready=economics_ready, reasons=reasons, conflicts=conflicts,
    )
    decision = resolution["decision"]

    evidence_quality = max(0.0, min(100.0, 50.0 + 7.0 * len(supports) - 5.0 * len(counter) - 15.0 * len(conflicts)))
    gate_quality = 100.0 if resolution["all_gates_pass"] else 50.0
    rr_quality = 100.0 if rr is not None and rr >= 1.50 else 35.0 if rr is not None else 45.0
    edge_quality = 100.0 if edge is not None and edge >= 0.10 else 35.0 if edge is not None else 45.0
    economics_quality = (rr_quality + edge_quality) / 2.0
    score = max(0.0, min(100.0, 0.35 * evidence_quality + 0.30 * gate_quality + 0.20 * economics_quality + 0.15 * mc["strength"]))
    if decision == "NO_TRADE": score = min(score, 64.0)

    ordered_reasons = _dedupe([resolution["primary_blocker"]] + resolution["secondary_blockers"] + reasons + conflicts)
    output = {
        "question": QUESTION, "finding": decision, "decision": decision, "direction": direction, "thesis": thesis,
        "setup": setup, "maturity": maturity, "confirmation": confirmation, "risk_gate": risk_gate,
        "setup_ready": setup_ready, "confirmation_ready": confirmation_ready, "economics_ready": economics_ready,
        "trade_plan": plan, "reasons": ordered_reasons, "conflicts": conflicts,
        "supporting_evidence": supports, "counter_evidence": counter, "counter_thesis": counter,
        "observations": [f"direction={direction}", "direction_authority=E6", f"setup={setup}", f"maturity={maturity or 'UNRESOLVED'}", f"confirmation={confirmation or 'UNRESOLVED'}", f"risk_gate={risk_gate or 'UNRESOLVED'}", f"plan_structurally_valid={plan_structural}", f"market_control={mc['state']}", f"control_strength={mc['strength']}", f"control_chain_complete={mc['participant_chain']['chain_complete']}", f"master_state={resolution['decision_state']}", f"primary_blocker={resolution['primary_blocker']}", f"next_required_event={resolution['next_required_event']}", "invalidation_evaluated_is_not_invalidation=True", "directional_evidence_conflict_is_not_automatic_veto=True"],
        "reasoning_role": "MASTER_DECISION_ANALYST", "decision_authority": "E9", "trade_decision_authority": True,
        "architecture": "SINGLE_AXIS_E1_TO_E9", "reconciliation": "E6_THESIS_AUTHORITY_PLUS_EVIDENCE_HIERARCHY_PLUS_EXPLICIT_GATE_MATRIX",
        "authority_checks": {"E6_thesis": thesis, "E6_setup": setup, "E6_direction": direction, "E6_maturity": maturity, "E7_confirmation": confirmation, "E8_risk_gate": risk_gate, "E8_plan_structurally_valid": plan_structural},
        "evidence_used": "E1_E2_E3_E4_E5_E6_E7_E8",
        "evidence_hierarchy": ["E1_MARKET_CONTEXT", "E2_OPPORTUNITY", "E3_STRUCTURE", "E4_LIQUIDITY", "E5_LOCATION", "E6_SETUP", "E7_CONFIRMATION", "E8_ECONOMICS"],
        "market_control_brain": mc,
        "market_control_model": "LIQUIDITY -> PARTICIPANT_BEHAVIOR -> TRAP -> REPRICING -> TARGET",
        "market_control_reporting": {"state": mc["state"], "intent": mc["market_intent"], "dominant_actor": mc["dominant_actor"], "controlled_side": mc["controlled_side"], "trapped_side": mc["trapped_side"], "liquidity_target": mc["liquidity_target"], "repricing_direction": mc["repricing_direction"], "auction_phase": mc["auction_phase"], "control_strength": mc["strength"], "evidence": mc["evidence"], "warnings": mc["warnings"], "chain_complete": mc["participant_chain"]["chain_complete"], "controller_role": mc["participant_chain"]["controller_role"]},
        "evidence_quality": round(evidence_quality, 2), "edge_quality": round(economics_quality, 2), "decision_confidence": round(score, 2), "decision_score": round(score, 2),
        "quantitative_economics": {"real_rr": rr, "economic_edge_r": edge, "economic_margin": margin, "stress_probability": probability, "risk_quality": risk_quality},
        "uncertainty": {"state": "HIGH" if score < 55 else "MEDIUM" if score < 75 else "LOW", "reasons": counter},
        "counter_evidence_vetoed": bool(conflicts),
        "gates": {"thesis": setup_ready, "confirmation": confirmation_ready, "economics": economics_ready, "hard_conflict": not bool(conflicts), "all_pass": decision in DIRECTIONS},
        "master_decision_resolution": resolution,
        "invalidation": ["new closed-candle evidence changes a decisive prerequisite", "explicit thesis invalidation or domain contradiction", "economics edge falls below the professional decision floor", "market-control thesis loses its required liquidity/participant chain"],
        "professional_reasoning": {"conclusion": thesis, "decision": decision, "why_trade": supports, "why_not_trade": ordered_reasons, "what_can_disprove": _dedupe(counter + conflicts), "edge_assessment": edge, "evidence_quality": evidence_quality, "decision_confidence": score, "market_control_conclusion": mc["state"], "direction_authority": "E6", "economic_authority": "E8", "master_resolution": resolution["rationale"]},
    }
    return EngineResult("E9", NAME, decision in DIRECTIONS, score, output, tuple(ordered_reasons))
