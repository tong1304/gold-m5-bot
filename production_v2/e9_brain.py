from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Should this trade be taken after reconciling all relevant evidence?"
DIRECTIONS = {"BUY", "SELL"}

# E9 is the final reconciler. These codes can never be softened by scoring.
HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "DIRECTIONAL_EVIDENCE_CONFLICT",
    "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
}
ECONOMIC_HARD_CODES = {
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW",
    "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
}


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
    if isinstance(vals, str):
        vals = [vals]
    return [_text(v) for v in vals if v]


def _finding(o: dict[str, Any]) -> str:
    return _text(o.get("finding", o.get("state", o.get("market_state", "UNRESOLVED"))))


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS:
            return x
        if any(k in x for k in ("BULLISH", "UP", "LONG", "BUYERS", "TREND_UP")):
            return "BUY"
        if any(k in x for k in ("BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN")):
            return "SELL"
    return "NEUTRAL"


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _blob(o: dict[str, Any]) -> str:
    keys = (
        "direction", "pressure", "directional_pressure", "structure_direction", "bias",
        "opportunity_direction", "thesis_direction", "regime", "market_regime",
        "liquidity_state", "liquidity_type", "event", "response_actor", "liquidity_taker",
        "value_response_direction", "repricing_direction", "intent", "market_intent",
        "auction_phase", "auction_state", "finding", "state", "confirmation",
    )
    return " ".join([_finding(o), *_codes(o)] + [_text(o.get(k)) for k in keys if k in o])


def _first(*values: Any) -> Any:
    for v in values:
        if v is not None and str(v).strip():
            return v
    return None


def _market_control(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any],
                    e4: dict[str, Any], e5: dict[str, Any], e6: dict[str, Any],
                    e7: dict[str, Any], direction: str, setup: str, thesis: str) -> dict[str, Any]:
    """Reporting layer only. It never grants execution permission."""
    b4 = _blob(e4)
    taker = _text(e4.get("liquidity_taker"))
    responder = _text(e4.get("response_actor"))
    auction_state = _text(e4.get("auction_state"))
    information = _text(e4.get("auction_information"))
    event = _text(_first(e4.get("event"), e4.get("finding"), e4.get("liquidity_type")))
    level = _first(e4.get("event_level"), e4.get("level"), e4.get("liquidity_level"), e4.get("swept_level"))
    sweep = any(k in b4 for k in ("SWEEP", "LIQUIDITY_TAKEN", "STOP_RUN"))
    rejection = any(k in b4 for k in ("REJECTION", "REJECTED", "FAILED_BREAK", "RECLAIM"))
    pending = auction_state in {"PENDING", "UNRESOLVED", "DEVELOPING", "WATCH"} or any(
        k in b4 for k in ("NOT_TERMINALLY_CONFIRMED", "TRUE_AUCTION_CONFIRMATION_NOT_PROVEN", "LOW_INFORMATION")
    )
    explicit_taker = taker in {"BUYERS", "SELLERS"}
    explicit_response = responder in {"BUYERS", "SELLERS"}
    terminal = explicit_response and (sweep or rejection) and not pending

    evidence: list[str] = []
    warnings: list[str] = []
    conflicts: list[str] = []
    controller = "UNPROVEN"
    controlled_side = "NONE"
    trapped_side = "NONE"
    repricing = "NEUTRAL"

    if explicit_taker:
        evidence.append("LIQUIDITY_TAKER_OBSERVED")
    if explicit_response:
        evidence.append("RESPONSE_ACTOR_OBSERVED")
    if sweep:
        evidence.append("LIQUIDITY_TAKE_EVENT_OBSERVED")
    if rejection:
        evidence.append("REJECTION_OR_RECLAIM_OBSERVED")

    if explicit_taker and explicit_response and taker != responder and (sweep or rejection):
        controller = responder
        controlled_side = "BUY" if responder == "BUYERS" else "SELL"
        repricing = controlled_side
        evidence.append("RESPONSE_OPPOSES_LIQUIDITY_TAKER")
        if terminal:
            trapped_side = "SELL" if responder == "BUYERS" else "BUY"
            evidence.append("TRAP_CHAIN_SUPPORTED")
    elif explicit_response and (sweep or rejection):
        controller = responder
        controlled_side = "BUY" if responder == "BUYERS" else "SELL"
        repricing = controlled_side
        evidence.append("RESPONSE_AFTER_LIQUIDITY_EVENT")
    elif explicit_taker:
        controller = taker
        evidence.append("LIQUIDITY_TAKER_ONLY_NO_CONTROL_PROOF")

    e1b, e2b, e3b, e5b = map(_blob, (e1, e2, e3, e5))
    buy = sum([
        "PRESSURE=UP" in e1b or "PRESSURE UP" in e1b,
        _direction(e1.get("direction"), e1.get("structure_direction")) == "BUY",
        _direction(e2.get("direction"), e2.get("opportunity_direction"), e2.get("thesis_direction")) == "BUY",
        _direction(e3.get("direction"), e3.get("structure_direction"), e3.get("bias")) == "BUY",
        _direction(e5.get("direction"), e5.get("repricing_direction"), e5.get("value_response_direction")) == "BUY",
        "BUY" in _blob(e6),
    ])
    sell = sum([
        "PRESSURE=DOWN" in e1b or "PRESSURE DOWN" in e1b,
        _direction(e1.get("direction"), e1.get("structure_direction")) == "SELL",
        _direction(e2.get("direction"), e2.get("opportunity_direction"), e2.get("thesis_direction")) == "SELL",
        _direction(e3.get("direction"), e3.get("structure_direction"), e3.get("bias")) == "SELL",
        _direction(e5.get("direction"), e5.get("repricing_direction"), e5.get("value_response_direction")) == "SELL",
        "SELL" in _blob(e6),
    ])
    if controller == "UNPROVEN":
        if buy >= 3 and buy > sell + 1:
            controller, controlled_side, repricing = "BUYERS", "BUY", "BUY"
            evidence.append("CROSS_ENGINE_BUYER_CONVERGENCE")
        elif sell >= 3 and sell > buy + 1:
            controller, controlled_side, repricing = "SELLERS", "SELL", "SELL"
            evidence.append("CROSS_ENGINE_SELLER_CONVERGENCE")
        elif buy >= 2 and sell >= 2:
            controller = "CONTESTED"
            conflicts.append("DIRECTIONAL_CONTROL_EVIDENCE_CONTESTED")

    accepted_above = any(k in e5b for k in ("ACCEPTED_ABOVE_VALUE", "ACCEPTANCE_ABOVE"))
    accepted_below = any(k in e5b for k in ("ACCEPTED_BELOW_VALUE", "ACCEPTANCE_BELOW"))
    accepted = accepted_above or accepted_below or "VALUE_ACCEPTANCE" in e5b
    acceptance_direction = "BUY" if accepted_above else "SELL" if accepted_below else _direction(
        e5.get("value_response_direction"), e5.get("repricing_direction")
    )
    acceptance_aligned = accepted and repricing in DIRECTIONS and acceptance_direction == repricing
    if accepted:
        evidence.append("VALUE_ACCEPTANCE_OBSERVED")
    if acceptance_aligned:
        evidence.append("VALUE_ACCEPTANCE_ALIGNED_WITH_REPRICING")
    elif accepted and acceptance_direction in DIRECTIONS:
        warnings.append("VALUE_ACCEPTANCE_DIRECTION_NOT_ALIGNED")

    chain_complete = bool(
        explicit_taker and explicit_response and taker != responder and (sweep or rejection)
        and level is not None and terminal and acceptance_aligned
    )
    if chain_complete:
        evidence.append("MARKET_CONTROL_CHAIN_COMPLETE")
    else:
        warnings.append("MARKET_CONTROL_CHAIN_INCOMPLETE")

    if controller in {"BUYERS", "SELLERS"}:
        state = "CONTROL_ESTABLISHED" if chain_complete else "CONTROL_FORMING"
    elif controller == "CONTESTED":
        state = "CONTROL_CONTESTED"
    else:
        state = "CONTROL_UNPROVEN"

    strength = 0.0
    strength += 15 if explicit_taker else 0
    strength += 20 if explicit_response else 0
    strength += 20 if (sweep or rejection) else 0
    strength += 15 if explicit_taker and explicit_response and taker != responder else 0
    strength += 15 if terminal else 0
    strength += 10 if acceptance_aligned else 0
    strength -= 20 if pending else 0
    strength -= 10 if information == "LOW_INFORMATION" else 0
    if not chain_complete:
        strength = min(strength, 74.0)
    strength = max(0.0, min(100.0, strength))

    return {
        "state": state,
        "strength": round(strength, 2),
        "dominant_actor": controller,
        "controlled_side": controlled_side,
        "trapped_side": trapped_side,
        "liquidity_target": level if level is not None else "UNPROVEN",
        "market_intent": f"REPRICING_{controlled_side}" if controlled_side in DIRECTIONS else "DIRECTIONAL_CONTROL_UNPROVEN",
        "repricing_direction": repricing,
        "auction_phase": "TERMINAL_RESPONSE" if terminal else "LIQUIDITY_INTERACTION" if event else "UNRESOLVED",
        "directional_evidence": {"buy_signals": buy, "sell_signals": sell, "net": buy - sell, "direction_from_e6": direction},
        "participant_chain": {
            "liquidity_taker": taker or "UNPROVEN",
            "response_actor": responder or "UNPROVEN",
            "controller_role": controller,
            "controller_basis": "TERMINAL_RESPONSE_AFTER_LIQUIDITY_EVENT" if terminal else "CROSS_ENGINE_CONVERGENCE" if controller in {"BUYERS", "SELLERS"} else "UNPROVEN",
            "liquidity_type": _text(e4.get("liquidity_type")) or "UNPROVEN",
            "event_level": level,
            "chain_complete": chain_complete,
            "causal_order": ["LIQUIDITY", "PARTICIPANT_BEHAVIOR", "TRAP", "REPRICING", "TARGET"],
        },
        "evidence": _dedupe(evidence),
        "warnings": _dedupe(warnings),
        "conflicts": _dedupe(conflicts),
        "thesis": thesis,
        "setup": setup,
        "reporting_only": True,
        "cannot_override_execution_gates": True,
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Final E9 reconciliation.

    E9 never invents a setup and never weakens E6/E7/E8 gates. It resolves the
    evidence hierarchy, applies hard vetoes, and emits an auditable decision.
    """
    e = [_out(upstream.get(f"E{i}")) for i in range(1, 9)]
    e1, e2, e3, e4, e5, e6, e7, e8 = e
    reasons: list[str] = []
    conflicts: list[str] = []
    supports: list[str] = []
    counter: list[str] = []

    # E6 owns thesis/direction. E7 owns confirmation. E8 owns economics.
    setup = str(e6.get("setup", e6.get("setup_family", "UNKNOWN")))
    thesis = str(e6.get("thesis", e6.get("candidate_setup_thesis", "UNRESOLVED")))
    setup_dir = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"), e6.get("finding"))
    trigger_dir = _direction(e7.get("direction"), e7.get("confirmation_direction"))
    risk_dir = _direction(e8.get("direction"), e8.get("risk_direction"))
    maturity = _text(e6.get("maturity", e6.get("stage", "UNRESOLVED")))
    confirmation = _text(e7.get("confirmation", e7.get("confirmation_state", "UNRESOLVED")))
    risk_gate = _text(e8.get("risk_gate", e8.get("finding", "RISK_NOT_READY")))
    plan = e8.get("trade_plan") or {}

    # Direction is valid only when E6 owns a clear thesis. E7/E8 may confirm it,
    # but they cannot create a new direction.
    direction = setup_dir if setup_dir in DIRECTIONS else "NEUTRAL"
    if direction in DIRECTIONS:
        if trigger_dir in DIRECTIONS and trigger_dir != direction:
            conflicts.append("E7:DIRECTION_OPPOSES_E6")
        if risk_dir in DIRECTIONS and risk_dir != direction:
            conflicts.append("E8:DIRECTION_OPPOSES_E6")

    setup_ready = (
        direction in DIRECTIONS
        and setup not in {"", "NONE", "UNKNOWN", "NO_SETUP"}
        and maturity in {"MATURE", "TRADE_READY", "VALIDATED"}
    )
    trigger_observed = bool(e7.get("trigger_observed") or e7.get("closed_candle_trigger") or e7.get("confirmation_proven"))
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"} and trigger_observed
    economics_ready = (
        risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY"}
        and bool(plan.get("valid") or plan.get("verified"))
    )

    if not setup_ready:
        reasons.append("SETUP_NOT_MATURE" if direction in DIRECTIONS else "DIRECTION_UNRESOLVED")
    if not confirmation_ready:
        reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready:
        reasons.append("RISK_NOT_READY")

    # Generic findings are evidence, not vetoes. Only explicit hard conflict
    # codes or explicit invalidation are allowed to become E9 conflicts.
    for i, eo in enumerate(e, 1):
        f = _finding(eo)
        if f not in {"", "UNRESOLVED", "UNKNOWN", "NONE", "NO_TRADE", "NO_SETUP"}:
            supports.append(f"E{i}:{f}")
        for code in _codes(eo):
            if code in HARD_CONFLICT_CODES or "INVALIDAT" in code:
                conflicts.append(f"E{i}:{code}")
            elif code in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN", "FOLLOW_THROUGH_PROVEN"}:
                supports.append(f"E{i}:{code}")
            else:
                counter.append(f"E{i}:{code}")

    # E1-E5 provide context and evidence. They do NOT vote against E6 merely
    # because their broad directional state differs. A contradiction is a veto
    # only when the upstream engine explicitly declares a thesis-level conflict
    # or invalidation. This prevents false vetoes such as E1=BEARISH vs
    # E6=SELL LIQUIDITY_REVERSAL being treated as an opposition.
    explicit_context_conflict_codes = {
        "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
        "OPPOSING_LIQUIDITY_THESIS", "DIRECTIONAL_EVIDENCE_CONFLICT",
        "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
    }
    for label, eo in (("E1", e1), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5)):
        codes = set(_codes(eo))
        explicit_conflicts = codes.intersection(explicit_context_conflict_codes)
        for code in sorted(explicit_conflicts):
            conflicts.append(f"{label}:{code}")

    # A directional field is only treated as contradictory when the engine also
    # explicitly marks it as conflicting with the active E6 thesis. Normal
    # structure/bias disagreement remains counter-evidence for reconciliation.
    for label, eo in (("E1", e1), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5)):
        d = _direction(
            eo.get("direction"), eo.get("opportunity_direction"), eo.get("thesis_direction"),
            eo.get("structure_direction"), eo.get("bias"), eo.get("repricing_direction"),
        )
        if d in DIRECTIONS and direction in DIRECTIONS and d != direction:
            counter.append(f"{label}:DIRECTION_COUNTER_EVIDENCE_{d}_VS_{direction}")

    mc = _market_control(e1, e2, e3, e4, e5, e6, e7, direction, setup, thesis)
    for code in mc["conflicts"]:
        conflicts.append(f"E9:{code}")
    if mc["state"] == "CONTROL_ESTABLISHED":
        supports.append("E9:MARKET_CONTROL_ESTABLISHED")
    elif mc["state"] == "CONTROL_FORMING":
        supports.append("E9:MARKET_CONTROL_FORMING")
    else:
        counter.append(f"E9:MARKET_CONTROL_{mc['state'].replace('CONTROL_', '')}")
    counter.extend(f"E9:{x}" for x in mc["warnings"])

    # E8 economics are hard gates. Missing values are NOT treated as zero;
    # absence is reported as not ready, preventing accidental arithmetic vetoes.
    rr = _num(e8.get("real_rr", e8.get("rr_used")))
    edge = _num(e8.get("economic_edge_r", e8.get("expected_value_r")))
    margin = _num(e8.get("economic_margin"))
    probability = _num(e8.get("stress_probability", e8.get("probability")))
    rq = e8.get("risk_quality", {})
    risk_quality = _num(rq.get("score")) if isinstance(rq, dict) else _num(e8.get("risk_quality"))

    if rr is not None and rr < 1.50:
        reasons.append("REAL_RR_BELOW_MINIMUM")
    if edge is not None and edge < 0.10:
        reasons.append("ECONOMIC_EDGE_TOO_THIN")
    if margin is not None and margin < 0.05:
        reasons.append("ECONOMIC_MARGIN_TOO_THIN")
    if probability is not None and probability < 0.50:
        reasons.append("STRESSED_PROBABILITY_BELOW_MINIMUM")
    if risk_quality is not None and risk_quality < 0.68:
        reasons.append("RISK_QUALITY_BELOW_DECISION_THRESHOLD")

    for code in _codes(e8):
        if code in ECONOMIC_HARD_CODES:
            reasons.append(code)

    reasons = _dedupe(reasons)
    conflicts = _dedupe(conflicts)
    supports = _dedupe(supports)
    counter = _dedupe(counter)

    hard_vetoes = _dedupe(reasons + conflicts)
    hard_veto = bool(hard_vetoes)

    # Explicit decision matrix: every executable trade must pass ALL three
    # gates. E9 cannot turn an incomplete gate into a trade by score.
    decision = direction if direction in DIRECTIONS and setup_ready and confirmation_ready and economics_ready and not hard_veto else "NO_TRADE"

    # Transparent scoring is descriptive only; it never overrides the matrix.
    evidence_quality = max(0.0, min(100.0, 50.0 + 7.0 * len(supports) - 5.0 * len(counter) - 15.0 * len(conflicts)))
    gate_quality = 100.0 if setup_ready and confirmation_ready and economics_ready else 50.0
    rr_quality = 100.0 if rr is not None and rr >= 1.50 else 35.0 if rr is not None else 45.0
    edge_quality = 100.0 if edge is not None and edge >= 0.10 else 35.0 if edge is not None else 45.0
    economics_quality = (rr_quality + edge_quality) / 2.0
    score = max(0.0, min(100.0, 0.35 * evidence_quality + 0.30 * gate_quality + 0.20 * economics_quality + 0.15 * mc["strength"]))
    if decision == "NO_TRADE":
        score = min(score, 64.0)

    authority = {f"E{i}_finding": _finding(eo) for i, eo in enumerate(e, 1)}
    authority.update({
        "E6_thesis": thesis,
        "E6_setup": setup,
        "E6_maturity": maturity,
        "E7_confirmation": confirmation,
        "E8_risk_gate": risk_gate,
    })

    output = {
        "question": QUESTION,
        "finding": decision,
        "decision": decision,
        "direction": direction,
        "thesis": thesis,
        "setup": setup,
        "maturity": maturity,
        "confirmation": confirmation,
        "risk_gate": risk_gate,
        "setup_ready": setup_ready,
        "confirmation_ready": confirmation_ready,
        "economics_ready": economics_ready,
        "trade_plan": plan,
        "reasons": _dedupe(reasons + conflicts),
        "conflicts": conflicts,
        "supporting_evidence": supports,
        "counter_evidence": counter,
        "counter_thesis": counter,
        "observations": [
            f"direction={direction}",
            f"setup={setup}",
            f"maturity={maturity or 'UNRESOLVED'}",
            f"confirmation={confirmation or 'UNRESOLVED'}",
            f"risk_gate={risk_gate or 'UNRESOLVED'}",
            f"market_control={mc['state']}",
            f"control_strength={mc['strength']}",
            f"control_chain_complete={mc['participant_chain']['chain_complete']}",
        ],
        "reasoning_role": "MASTER_DECISION_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": True,
        "architecture": "SINGLE_AXIS_E1_TO_E9",
        "reconciliation": "EVIDENCE_HIERARCHY_PLUS_COUNTER_THESIS_PLUS_EXPLICIT_GATE_MATRIX",
        "authority_checks": authority,
        "evidence_used": "E1_E2_E3_E4_E5_E6_E7_E8",
        "evidence_hierarchy": [
            "E1_MARKET_CONTEXT", "E2_OPPORTUNITY", "E3_STRUCTURE", "E4_LIQUIDITY",
            "E5_LOCATION", "E6_SETUP", "E7_CONFIRMATION", "E8_ECONOMICS",
        ],
        "market_control_brain": mc,
        "market_control_model": "LIQUIDITY -> PARTICIPANT_BEHAVIOR -> TRAP -> REPRICING -> TARGET",
        "market_control_reporting": {
            "state": mc["state"], "intent": mc["market_intent"],
            "dominant_actor": mc["dominant_actor"], "controlled_side": mc["controlled_side"],
            "trapped_side": mc["trapped_side"], "liquidity_target": mc["liquidity_target"],
            "repricing_direction": mc["repricing_direction"], "auction_phase": mc["auction_phase"],
            "control_strength": mc["strength"], "evidence": mc["evidence"],
            "warnings": mc["warnings"], "chain_complete": mc["participant_chain"]["chain_complete"],
            "controller_role": mc["participant_chain"]["controller_role"],
            "controller_basis": mc["participant_chain"]["controller_basis"],
        },
        "evidence_quality": round(evidence_quality, 2),
        "edge_quality": round(economics_quality, 2),
        "decision_confidence": round(score, 2),
        "decision_score": round(score, 2),
        "quantitative_economics": {
            "real_rr": rr, "economic_edge_r": edge, "economic_margin": margin,
            "stress_probability": probability, "risk_quality": risk_quality,
        },
        "uncertainty": {
            "state": "HIGH" if score < 55 else "MEDIUM" if score < 75 else "LOW",
            "reasons": counter,
        },
        "counter_evidence_vetoed": bool(conflicts),
        "gates": {
            "thesis": setup_ready,
            "confirmation": confirmation_ready,
            "economics": economics_ready,
            "hard_conflict": not bool(conflicts),
            "all_pass": decision in DIRECTIONS,
        },
        "invalidation": [
            "new closed-candle evidence changes a decisive prerequisite",
            "thesis invalidation or explicit domain contradiction",
            "economics edge falls below the professional decision floor",
            "market-control thesis loses its liquidity/participant-behavior chain",
        ],
        "professional_reasoning": {
            "conclusion": thesis,
            "decision": decision,
            "why_trade": supports,
            "why_not_trade": _dedupe(reasons + conflicts),
            "what_can_disprove": _dedupe(counter + conflicts),
            "edge_assessment": edge,
            "evidence_quality": evidence_quality,
            "decision_confidence": score,
            "market_control_conclusion": mc["state"],
        },
    }
    return EngineResult("E9", NAME, decision in DIRECTIONS, score, output, tuple(_dedupe(reasons + conflicts)))
