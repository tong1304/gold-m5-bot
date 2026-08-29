from __future__ import annotations
from typing import Any
from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Should this trade be taken after reconciling all relevant evidence?"
DIRECTIONS = {"BUY", "SELL"}
HARD_CONFLICT_CODES = {
    "THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT",
    "OPPOSING_LIQUIDITY_THESIS", "DIRECTIONAL_EVIDENCE_CONFLICT",
    "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT",
}
SOFT_CODES = {"LOW_CONFIDENCE", "TRANSITION", "MIXED", "SPACE_CONFLICT",
              "SURVIVAL_FRAGILE", "ECONOMICS_SENSITIVITY_FRAGILE"}


def _out(e):
    return e.output if e else {}


def _text(v):
    return str(v or "").upper().strip()


def _direction(*vals):
    for v in vals:
        x = _text(v)
        if x in DIRECTIONS:
            return x
        if x in {"BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
            return "BUY"
        if x in {"BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
            return "SELL"
    return "NEUTRAL"


def _codes(o):
    vals = o.get("reason_codes") or o.get("reasons") or o.get("counter_evidence") or []
    if isinstance(vals, str):
        vals = [vals]
    return [_text(x) for x in vals if x]


def _finding(o):
    return _text(o.get("finding", o.get("state", o.get("market_state", "UNRESOLVED"))))


def _score_num(v, default=0.0):
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _has_any(o, *needles):
    blob = " ".join([_text(o.get("finding")), *_codes(o)])
    return any(n in blob for n in needles)


def _market_control_brain(e1, e2, e3, e4, e5, e6, e7, e8, direction, setup, thesis):
    """Synthesize E1-E8 as a market-control thesis without inventing facts.

    E9 is the master interpreter, not a ninth independent setup generator.
    Liquidity and participant-response evidence receive the highest weight;
    structure, location, confirmation and economics determine whether control
    is merely forming or sufficiently proven to support execution.
    """
    obs = (e1, e2, e3, e4, e5, e6, e7, e8)
    e1f, e2f, e3f, e4f, e5f, e6f, e7f, e8f = map(_finding, obs)
    blobs = {i: " ".join([_finding(o), *_codes(o)]) for i, o in enumerate(obs, 1)}
    e4blob, e5blob, e6blob, e7blob, e8blob = blobs[4], blobs[5], blobs[6], blobs[7], blobs[8]

    control = {
        "dominant_actor": "UNRESOLVED",
        "controlled_side": "NONE",
        "trapped_side": "NONE",
        "liquidity_target": "UNRESOLVED",
        "market_intent": "UNRESOLVED",
        "auction_phase": "UNRESOLVED",
        "repricing_direction": direction if direction in DIRECTIONS else "NEUTRAL",
    }
    evidence: list[str] = []
    warnings: list[str] = []

    # These are observations/inferences, never claims of privileged knowledge.
    buyers = "BUYERS" in e4blob
    sellers = "SELLERS" in e4blob
    sweep = any(x in e4blob for x in ("SWEEP", "LIQUIDITY_TAKEN", "STOP_RUN"))
    rejection = any(x in e4blob for x in ("RECLAIM", "REJECTION", "FAILED_BREAK"))
    pending = "PENDING" in e4blob or "NOT_TERMINALLY_CONFIRMED" in e4blob
    failed_break = "FAILED_BOS" in e3f or "FAILED_BREAK" in e3f
    range_state = "RANGE" in e1f
    transition = "TRANSITION" in e1f or "TRANSITION" in e3f or "TRANSITION" in e2f
    favorable = "FAVORABLE" in e5f
    discount = "DISCOUNT" in e5blob
    premium = "PREMIUM" in e5blob
    accepted_above = "ACCEPTED_ABOVE_VALUE" in e5blob
    rejected_below = "REJECTED_BELOW_VALUE" in e5blob
    long_space = _score_num(e5.get("available_space_atr_long"), 0.0)
    short_space = _score_num(e5.get("available_space_atr_short"), 0.0)
    trigger_proven = any(x in e7blob for x in ("CONFIRMED", "PROVEN", "VALIDATED"))
    risk_ready = "RISK_READY" in e8blob or "ECONOMICALLY_ACCEPTABLE" in e8blob
    survival = not any(x in e8blob for x in ("SURVIVAL_NOT_PROVEN", "STRUCTURAL_SURVIVAL_NOT_PROVEN"))

    # E4 gives the causal auction sequence: taker -> response -> acceptance/rejection.
    liquidity_type = str(e4.get("liquidity_type") or e4.get("event") or "UNRESOLVED")
    liquidity_level = e4.get("event_level", e4.get("level", e4.get("liquidity_level")))
    response_actor = _text(e4.get("response_actor"))
    taker = _text(e4.get("liquidity_taker"))

    if liquidity_level is not None:
        control["liquidity_target"] = liquidity_level
    elif liquidity_type not in {"", "UNRESOLVED"}:
        control["liquidity_target"] = liquidity_type

    if sweep and rejection:
        control["auction_phase"] = "POST_SWEEP_REJECTION"
        evidence.append("LIQUIDITY_SWEEP_WITH_REJECTION")
        if response_actor in {"BUYERS", "SELLERS"}:
            control["dominant_actor"] = response_actor
        elif taker == "BUYERS" and sellers:
            control["dominant_actor"] = "SELLERS"
        elif taker == "SELLERS" and buyers:
            control["dominant_actor"] = "BUYERS"

        # A trap is inferred only when the liquidity taker and responding side
        # are both explicit; this avoids the previous impossible double-check.
        if taker == "BUYERS" and response_actor == "SELLERS":
            control["trapped_side"] = "BUYERS"
            control["controlled_side"] = "SELLERS"
            control["repricing_direction"] = "SELL"
            evidence.append("BUYERS_TAKEN_LIQUIDITY_SELLER_RESPONSE")
        elif taker == "SELLERS" and response_actor == "BUYERS":
            control["trapped_side"] = "SELLERS"
            control["controlled_side"] = "BUYERS"
            control["repricing_direction"] = "BUY"
            evidence.append("SELLERS_TAKEN_LIQUIDITY_BUYER_RESPONSE")
        else:
            warnings.append("PARTICIPANT_RESPONSE_NOT_EXPLICIT")
    elif failed_break or rejection:
        control["auction_phase"] = "FAILED_AUCTION"
        evidence.append("FAILED_AUCTION_OR_REJECTION")
        if direction in DIRECTIONS:
            control["controlled_side"] = direction + "_THESIS"
    elif range_state:
        control["auction_phase"] = "BALANCED_RANGE"
        warnings.append("RANGE_CONTROL_NOT_ESTABLISHED")
    elif transition:
        control["auction_phase"] = "TRANSITION_AUCTION"

    if pending:
        warnings.append("AUCTION_NOT_TERMINALLY_CONFIRMED")
    if transition:
        warnings.append("MARKET_STATE_TRANSITION")
    if favorable:
        evidence.append("LOCATION_FAVORABLE")
    if discount:
        evidence.append("PRICE_IN_DISCOUNT")
    if premium:
        evidence.append("PRICE_IN_PREMIUM")
    if accepted_above:
        evidence.append("VALUE_ACCEPTANCE_ABOVE")
    if rejected_below:
        evidence.append("VALUE_REJECTION_BELOW")

    if direction == "BUY":
        if 0 < long_space < 0.75:
            warnings.append("BUY_SPACE_CONSTRAINED")
        elif long_space >= 0.75:
            evidence.append("BUY_SPACE_AVAILABLE")
    elif direction == "SELL":
        if 0 < short_space < 0.75:
            warnings.append("SELL_SPACE_CONSTRAINED")
        elif short_space >= 0.75:
            evidence.append("SELL_SPACE_AVAILABLE")

    if trigger_proven:
        evidence.append("CONFIRMATION_PROVEN")
    else:
        warnings.append("CONFIRMATION_NOT_PROVEN")
    if risk_ready and survival:
        evidence.append("ECONOMIC_SURVIVAL_READY")
    else:
        warnings.append("ECONOMIC_SURVIVAL_UNPROVEN")

    # E9 describes intent only when the participant-behavior chain supports it.
    if control["trapped_side"] in DIRECTIONS:
        control["market_intent"] = "FORCED_REPRICING_" + control["repricing_direction"]
    elif control["controlled_side"] in {"BUY", "SELL"}:
        control["market_intent"] = "POTENTIAL_REPRICING_" + control["controlled_side"]
    elif range_state:
        control["market_intent"] = "LIQUIDITY_SEEKING_WITHOUT_DIRECTIONAL_CONTROL"
    elif transition:
        control["market_intent"] = "DIRECTIONAL_INTENT_UNRESOLVED_DURING_TRANSITION"
    else:
        control["market_intent"] = "DIRECTIONAL_INTENT_UNPROVEN"

    # Independent evidence strength. This is an interpretation score, not a
    # probability of profit and never overrides E7/E8 hard gates.
    strength = 0.0
    strength += 30.0 if control["trapped_side"] in DIRECTIONS else 0.0
    strength += 15.0 if sweep and rejection else 0.0
    strength += 10.0 if failed_break else 0.0
    strength += 10.0 if accepted_above or rejected_below else 0.0
    strength += 10.0 if favorable else 0.0
    strength += 10.0 if trigger_proven else 0.0
    strength += 10.0 if risk_ready and survival else 0.0
    strength += 5.0 if direction in DIRECTIONS and control["repricing_direction"] == direction else 0.0
    strength -= 15.0 if pending else 0.0
    strength -= 10.0 if transition else 0.0
    strength -= 10.0 if range_state and control["trapped_side"] == "NONE" else 0.0
    strength = max(0.0, min(100.0, strength))

    if strength >= 75:
        regime = "CONTROL_ESTABLISHED"
    elif strength >= 50:
        regime = "CONTROL_FORMING"
    elif range_state:
        regime = "BALANCED_NO_CONTROL"
    else:
        regime = "CONTROL_UNPROVEN"

    actor = control["dominant_actor"]
    if actor == "BUYERS":
        actor_reason = "BUYERS_HAVE_CURRENT_RESPONSE_CONTROL"
    elif actor == "SELLERS":
        actor_reason = "SELLERS_HAVE_CURRENT_RESPONSE_CONTROL"
    else:
        actor_reason = "NO_PARTICIPANT_HAS_PROVEN_CONTROL"

    if control["trapped_side"] in DIRECTIONS:
        interpretation = (
            f"{actor_reason}; {control['trapped_side']} appear trapped after the observed liquidity event, "
            f"supporting potential {control['repricing_direction']} repricing, but execution still requires E7/E8 proof."
        )
    elif control["market_intent"] == "LIQUIDITY_SEEKING_WITHOUT_DIRECTIONAL_CONTROL":
        interpretation = "ตลาดยังอยู่ในสมดุลและกำลังค้นหาสภาพคล่อง ยังไม่มีฝ่ายใดควบคุมทิศทางอย่างพิสูจน์ได้"
    elif transition:
        interpretation = "ตลาดอยู่ใน Transition; มีเจตนาบางส่วนแต่ยังไม่มีหลักฐานเพียงพอว่าใครควบคุมการ Repricing"
    else:
        interpretation = "ยังไม่มี Participant-Control chain ที่สมบูรณ์ จึงยังไม่ควรอ้างว่าใครเป็นเจ้าตลาด"

    return {
        **control,
        "state": regime,
        "strength": round(strength, 2),
        "evidence": list(dict.fromkeys(evidence)),
        "warnings": list(dict.fromkeys(warnings)),
        "thesis": thesis,
        "participant_chain": {
            "liquidity_taker": taker or "UNRESOLVED",
            "response_actor": response_actor or "UNRESOLVED",
            "liquidity_type": liquidity_type,
            "event_level": liquidity_level,
            "chain_complete": control["trapped_side"] in DIRECTIONS,
        },
        "interpretation": interpretation,
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    engines = [upstream.get(f"E{i}") for i in range(1, 9)]
    o = [_out(e) for e in engines]
    e1, e2, e3, e4, e5, e6, e7, e8 = o
    reasons: list[str] = []
    conflicts: list[str] = []
    supports: list[str] = []
    counter: list[str] = []

    setup_dir = _direction(e6.get("direction"), e6.get("direction_thesis"))
    trigger_dir = _direction(e7.get("direction"), setup_dir)
    risk_dir = _direction(e8.get("direction"), setup_dir)
    dirs = [x for x in (setup_dir, trigger_dir, risk_dir) if x in DIRECTIONS]
    if len(set(dirs)) > 1:
        conflicts.append("SETUP_TRIGGER_RISK_DIRECTION_CONFLICT")
    direction = setup_dir if setup_dir in DIRECTIONS and len(set(dirs)) <= 1 else "NEUTRAL"

    setup = str(e6.get("setup", e6.get("setup_family", "NONE")))
    thesis = str(e6.get("thesis", e6.get("candidate_setup_thesis", "UNRESOLVED")))
    maturity = _text(e6.get("maturity"))
    confirmation = _text(e7.get("confirmation", e7.get("confirmation_state", "UNRESOLVED")))
    risk_gate = _text(e8.get("risk_gate", e8.get("finding", "RISK_NOT_READY")))
    plan = e8.get("trade_plan") or {}

    setup_ready = maturity == "MATURE" and setup != "NONE" and direction in DIRECTIONS
    trigger_observed = bool(e7.get("trigger_observed") or e7.get("closed_candle_trigger") or e7.get("confirmation_proven"))
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED"} and trigger_observed
    economics_ready = risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE"} and bool(plan.get("valid"))

    for i, eo in enumerate(o[:5], 1):
        f = _finding(eo)
        codes = _codes(eo)
        if f not in {"", "UNRESOLVED", "UNKNOWN", "NONE", "NO_SETUP", "NO_TRADE"}:
            supports.append(f"E{i}:{f}")
        for c in codes:
            if c in HARD_CONFLICT_CODES or "INVALIDAT" in c or "CONFLICT" in c or "OPPOS" in c:
                conflicts.append(f"E{i}:{c}")
            elif c in SOFT_CODES:
                counter.append(f"E{i}:{c}")

    for label, eo in (("E6", e6), ("E7", e7), ("E8", e8)):
        for c in _codes(eo):
            if c in HARD_CONFLICT_CODES or "INVALIDAT" in c or "CONFLICT" in c or "OPPOS" in c:
                conflicts.append(f"{label}:{c}")
            elif c not in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"}:
                counter.append(f"{label}:{c}")

    if _finding(e1) in {"TRANSITION", "UNCLEAR"}:
        counter.append(f"E1:{_finding(e1)}")
    if _finding(e3) in {"MIXED", "TRANSITION", "UNCLEAR"}:
        counter.append(f"E3:{_finding(e3)}")
    if _finding(e2) in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS"}:
        counter.append(f"E2:{_finding(e2)}")

    for label, eo in (("E1", e1), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5)):
        d = _direction(eo.get("direction"), eo.get("directional_pressure"), eo.get("pressure"), eo.get("opportunity_direction"), eo.get("thesis_direction"))
        if d in DIRECTIONS and direction in DIRECTIONS and d != direction:
            conflicts.append(f"{label}:DIRECTION_OPPOSES_E6")

    market_control = _market_control_brain(e1, e2, e3, e4, e5, e6, e7, e8, direction, setup, thesis)
    if market_control["state"] == "CONTROL_ESTABLISHED":
        supports.append("E9:MARKET_CONTROL_ESTABLISHED")
    elif market_control["state"] in {"CONTROL_FORMING", "BALANCED_NO_CONTROL"}:
        counter.extend(f"E9:{x}" for x in market_control["warnings"])
    else:
        counter.append("E9:MARKET_CONTROL_UNPROVEN")

    if direction == "NEUTRAL":
        reasons.append("DIRECTION_UNRESOLVED")
    if setup == "NONE" or maturity in {"", "UNRESOLVED", "ABSENT", "FAILED", "INVALIDATED", "EXPIRED"}:
        reasons.append("SETUP_NOT_ESTABLISHED")
    elif not setup_ready:
        reasons.append("SETUP_NOT_MATURE")
    if not confirmation_ready:
        reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready:
        reasons.append("RISK_NOT_READY")

    rr = _score_num(e8.get("real_rr", e8.get("rr_used")), 0.0)
    edge = _score_num(e8.get("economic_edge_r", e8.get("expected_value_r")), 0.0)
    margin = _score_num(e8.get("economic_margin"), 0.0)
    prob = _score_num(e8.get("stress_probability", e8.get("probability")), -1.0)
    rq = e8.get("risk_quality", {})
    risk_quality = _score_num(rq.get("score"), 0.0) if isinstance(rq, dict) else 0.0

    if rr > 0 and rr < 1.50:
        reasons.append("ECONOMIC_EDGE_RR_BELOW_PROFESSIONAL_MINIMUM")
    if edge < 0.10:
        reasons.append("ECONOMIC_EDGE_TOO_THIN")
    if margin < 0.05:
        reasons.append("ECONOMIC_MARGIN_TOO_THIN")
    if prob >= 0 and prob < 0.50:
        reasons.append("STRESSED_PROBABILITY_BELOW_MINIMUM")
    if e8.get("risk_quality") and risk_quality > 0 and risk_quality < 0.68:
        reasons.append("RISK_QUALITY_BELOW_DECISION_THRESHOLD")

    for c in _codes(e8):
        if c in {"REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY"}:
            reasons.append(c)
        elif c in {"SURVIVAL_FRAGILE", "ECONOMICS_SENSITIVITY_FRAGILE", "ECONOMIC_MARGIN_TOO_THIN", "PROBABILITY_EDGE_NOT_POSITIVE"}:
            counter.append(f"E8:{c}")

    def dedupe(items):
        return list(dict.fromkeys(str(x) for x in items if x))

    conflicts, counter, supports, reasons = map(dedupe, (conflicts, counter, supports, reasons))
    hard_reasons = {
        "DIRECTION_UNRESOLVED", "SETUP_NOT_ESTABLISHED", "SETUP_NOT_MATURE", "ENTRY_CONFIRMATION_NOT_PROVEN", "RISK_NOT_READY",
        "ECONOMIC_EDGE_RR_BELOW_PROFESSIONAL_MINIMUM", "ECONOMIC_EDGE_TOO_THIN", "ECONOMIC_MARGIN_TOO_THIN",
        "STRESSED_PROBABILITY_BELOW_MINIMUM", "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "REAL_RR_BELOW_MINIMUM",
        "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
        "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    }
    hard_veto = bool(conflicts) or any(r in hard_reasons for r in reasons)

    market_control_veto = market_control["strength"] < 35 and market_control["market_intent"].startswith("FORCED_REPRICING")
    if market_control_veto:
        counter.append("E9:MARKET_CONTROL_THESIS_TOO_WEAK")
        hard_veto = True

    decision = direction if not hard_veto else "NO_TRADE"

    evidence_quality = max(0.0, min(100.0, 35.0 + 8.0 * len(supports) - 10.0 * len(counter) - 20.0 * len(conflicts)))
    gate_quality = 100.0 if setup_ready and confirmation_ready and economics_ready else 55.0
    edge_quality = 50.0 + 15.0 * min(2.0, max(0.0, edge / 0.10)) + 10.0 * min(2.0, max(0.0, margin / 0.05)) + (10.0 if rr >= 1.50 else -20.0)
    edge_quality = max(0.0, min(100.0, edge_quality))
    score = max(0.0, min(100.0, 0.40 * evidence_quality + 0.25 * gate_quality + 0.20 * edge_quality + 0.15 * market_control["strength"]))
    if decision == "NO_TRADE":
        score = min(score, 64.0)

    authority_checks = {f"E{i}_finding": _finding(eo) for i, eo in enumerate(o, 1)}
    authority_checks.update({"E6_thesis": thesis, "E6_setup": setup, "E6_maturity": maturity, "E7_confirmation": confirmation, "E8_risk_gate": risk_gate})

    output = {
        "question": QUESTION, "decision": decision, "direction": direction, "thesis": thesis, "setup": setup,
        "maturity": maturity, "confirmation": confirmation, "risk_gate": risk_gate, "setup_ready": setup_ready,
        "confirmation_ready": confirmation_ready, "economics_ready": economics_ready, "trade_plan": plan,
        "reasoning_role": "MASTER_DECISION_ANALYST", "decision_authority": "E9", "trade_decision_authority": True,
        "architecture": "SINGLE_AXIS_E1_TO_E9", "reconciliation": "EVIDENCE_HIERARCHY_PLUS_COUNTER_THESIS_PLUS_MARKET_CONTROL_NOT_VOTING",
        "authority_checks": authority_checks, "conflicts": conflicts, "evidence_used": "E1_E2_E3_E4_E5_E6_E7_E8",
        "supporting_evidence": supports, "counter_evidence": counter, "counter_thesis": counter,
        "evidence_hierarchy": ["E1_MARKET_CONTEXT", "E2_OPPORTUNITY", "E3_STRUCTURE", "E4_LIQUIDITY", "E5_LOCATION", "E6_SETUP", "E7_CONFIRMATION", "E8_ECONOMICS"],
        "market_control_brain": market_control,
        "market_control_model": "LIQUIDITY -> PARTICIPANT_BEHAVIOR -> TRAP -> REPRICING -> TARGET",
        "evidence_quality": round(evidence_quality, 2), "edge_quality": round(edge_quality, 2),
        "decision_confidence": round(score, 2), "decision_score": round(score, 2),
        "quantitative_economics": {"real_rr": rr, "economic_edge_r": edge, "economic_margin": margin, "stress_probability": None if prob < 0 else prob, "risk_quality": risk_quality},
        "uncertainty": {"state": "HIGH" if score < 55 else "MEDIUM" if score < 75 else "LOW", "reasons": counter},
        "counter_evidence_vetoed": bool(conflicts),
        "invalidation": ["new closed-candle evidence changes a decisive prerequisite", "thesis invalidation or explicit domain contradiction", "economics edge falls below the professional decision floor", "market-control thesis loses its liquidity/participant-behavior chain"],
        "professional_reasoning": {
            "conclusion": thesis, "decision": decision, "why_trade": supports, "why_not_trade": dedupe(reasons + conflicts),
            "what_can_disprove": dedupe(counter + conflicts), "edge_assessment": edge, "evidence_quality": evidence_quality,
            "decision_confidence": score, "market_control_conclusion": market_control["interpretation"],
        },
    }
    return EngineResult("E9", NAME, decision in DIRECTIONS, score, output, tuple(dedupe(reasons + conflicts)))
