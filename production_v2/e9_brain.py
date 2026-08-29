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
        if any(k in x for k in ("BULLISH", "UP", "LONG", "BUYERS", "TREND_UP")):
            return "BUY"
        if any(k in x for k in ("BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN")):
            return "SELL"
    return "NEUTRAL"


def _codes(o):
    vals = o.get("reason_codes") or o.get("reasons") or o.get("counter_evidence") or []
    if isinstance(vals, str):
        vals = [vals]
    return [_text(x) for x in vals if x]


def _finding(o):
    return _text(o.get("finding", o.get("state", o.get("market_state", "UNRESOLVED"))))


def _blob(o):
    return " ".join([_finding(o), *_codes(o), _text(o.get("direction")),
                     _text(o.get("pressure")), _text(o.get("directional_pressure"))])


def _has(o, *terms):
    b = _blob(o)
    return any(t.upper() in b for t in terms)


def _num(v, default=0.0):
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _market_control_brain(e1, e2, e3, e4, e5, e6, e7, e8, direction, setup, thesis):
    """E9-only synthesis of E1-E8 into a market-control thesis.

    This is inference from observable engine evidence, not a claim of knowing
    a real participant's identity.  It never overrides E7/E8 execution gates.
    """
    control = {
        "dominant_actor": "UNRESOLVED",
        "controlled_side": "NONE",
        "trapped_side": "NONE",
        "liquidity_target": "UNRESOLVED",
        "market_intent": "DIRECTIONAL_INTENT_UNPROVEN",
        "auction_phase": "UNRESOLVED",
        "repricing_direction": direction if direction in DIRECTIONS else "NEUTRAL",
    }
    evidence: list[str] = []
    warnings: list[str] = []

    e1b, e2b, e3b, e4b, e5b, e6b, e7b, e8b = map(_blob, (e1, e2, e3, e4, e5, e6, e7, e8))
    e1d = _direction(e1.get("direction"), e1.get("pressure"), e1.get("directional_pressure"), e1.get("structure_direction"))
    e2d = _direction(e2.get("direction"), e2.get("opportunity_direction"), e2.get("thesis_direction"))
    e3d = _direction(e3.get("direction"), e3.get("structure_direction"), e3.get("bias"))
    e4d = _direction(e4.get("direction"), e4.get("liquidity_taker"), e4.get("response_actor"))
    e5d = _direction(e5.get("direction"), e5.get("value_response_direction"), e5.get("repricing_direction"))

    pressure_buy = any(k in e1b for k in ("PRESSURE=UP", "PRESSURE UP", "BUYING_PRESSURE", "BUYERS"))
    pressure_sell = any(k in e1b for k in ("PRESSURE=DOWN", "PRESSURE DOWN", "SELLING_PRESSURE", "SELLERS"))
    sellers_took = _text(e4.get("liquidity_taker")) == "SELLERS"
    buyers_took = _text(e4.get("liquidity_taker")) == "BUYERS"
    response = _text(e4.get("response_actor"))
    event = _text(e4.get("event") or e4.get("liquidity_type") or e4.get("finding"))
    level = e4.get("event_level", e4.get("level", e4.get("liquidity_level")))

    sweep = any(k in e4b for k in ("SWEEP", "LIQUIDITY_TAKEN", "STOP_RUN"))
    reclaim = any(k in e4b for k in ("RECLAIM", "FAILED_BREAK", "REJECTION"))
    pending = any(k in e4b for k in ("PENDING", "NOT_TERMINALLY_CONFIRMED", "LOW_INFORMATION"))
    transition = any(k in e1b + " " + e2b + " " + e3b for k in ("TRANSITION", "WATCH"))
    range_state = "RANGE" in e1b or "RANGE" in e2b
    discount = "DISCOUNT" in e5b
    premium = "PREMIUM" in e5b
    accepted_above = "ACCEPTED_ABOVE_VALUE" in e5b
    rejected_below = "REJECTED_BELOW_VALUE" in e5b

    # Liquidity event is the strongest participant-behaviour evidence.
    if level is not None:
        control["liquidity_target"] = level
    elif event and event not in {"UNRESOLVED", "LOW_INFORMATION"}:
        control["liquidity_target"] = event

    if sellers_took:
        control["dominant_actor"] = "SELLERS"
        evidence.append("SELLERS_TAKING_LIQUIDITY")
    elif buyers_took:
        control["dominant_actor"] = "BUYERS"
        evidence.append("BUYERS_TAKING_LIQUIDITY")
    elif response in {"BUYERS", "SELLERS"}:
        control["dominant_actor"] = response
        evidence.append("EXPLICIT_RESPONSE_ACTOR")

    # Cross-engine convergence can establish a directional control thesis even
    # when E4 has no explicit response actor. It does not create a trap claim.
    sell_signals = sum([
        pressure_sell, e1d == "SELL", e2d == "SELL", e3d == "SELL", e5d == "SELL",
        sellers_took, "SELL" in e6b, "SELL" in e7b,
    ])
    buy_signals = sum([
        pressure_buy, e1d == "BUY", e2d == "BUY", e3d == "BUY", e5d == "BUY",
        buyers_took, "BUY" in e6b, "BUY" in e7b,
    ])

    if control["dominant_actor"] == "UNRESOLVED":
        if sell_signals >= 3 and sell_signals > buy_signals:
            control["dominant_actor"] = "SELLERS"
            evidence.append("CROSS_ENGINE_SELLER_CONVERGENCE")
        elif buy_signals >= 3 and buy_signals > sell_signals:
            control["dominant_actor"] = "BUYERS"
            evidence.append("CROSS_ENGINE_BUYER_CONVERGENCE")

    if control["dominant_actor"] == "SELLERS" and sell_signals >= 3:
        control["controlled_side"] = "SELL"
        control["repricing_direction"] = "SELL"
        evidence.append("SELL_SIDE_CONTROL_FORMING")
    elif control["dominant_actor"] == "BUYERS" and buy_signals >= 3:
        control["controlled_side"] = "BUY"
        control["repricing_direction"] = "BUY"
        evidence.append("BUY_SIDE_CONTROL_FORMING")
    elif control["dominant_actor"] == "SELLERS" and sellers_took:
        control["controlled_side"] = "SELL"
        control["repricing_direction"] = "SELL"
    elif control["dominant_actor"] == "BUYERS" and buyers_took:
        control["controlled_side"] = "BUY"
        control["repricing_direction"] = "BUY"

    if sweep and reclaim and response == "SELLERS" and buyers_took:
        control["trapped_side"] = "BUYERS"
        control["market_intent"] = "FORCED_REPRICING_SELL"
        evidence.append("BUYERS_TRAPPED_AFTER_LIQUIDITY_TAKE")
    elif sweep and reclaim and response == "BUYERS" and sellers_took:
        control["trapped_side"] = "SELLERS"
        control["market_intent"] = "FORCED_REPRICING_BUY"
        evidence.append("SELLERS_TRAPPED_AFTER_LIQUIDITY_TAKE")
    elif control["controlled_side"] in DIRECTIONS:
        control["market_intent"] = "POTENTIAL_REPRICING_" + control["controlled_side"]
    elif range_state:
        control["market_intent"] = "LIQUIDITY_SEEKING_WITHOUT_DIRECTIONAL_CONTROL"
    elif transition:
        control["market_intent"] = "DIRECTIONAL_INTENT_UNRESOLVED_DURING_TRANSITION"

    if sweep and reclaim:
        control["auction_phase"] = "POST_SWEEP_RECLAIM"
        evidence.append("SWEEP_RECLAIM_SEQUENCE")
    elif event:
        control["auction_phase"] = "LIQUIDITY_INTERACTION"
    elif range_state:
        control["auction_phase"] = "BALANCED_RANGE"
    elif transition:
        control["auction_phase"] = "TRANSITION_AUCTION"

    if discount:
        evidence.append("PRICE_IN_DISCOUNT")
    if premium:
        evidence.append("PRICE_IN_PREMIUM")
    if accepted_above:
        evidence.append("VALUE_ACCEPTANCE_ABOVE")
    if rejected_below:
        evidence.append("VALUE_REJECTION_BELOW")
    if pending:
        warnings.append("AUCTION_NOT_TERMINALLY_CONFIRMED")
    if transition:
        warnings.append("MARKET_STATE_TRANSITION")
    if response not in {"BUYERS", "SELLERS"}:
        warnings.append("PARTICIPANT_RESPONSE_NOT_EXPLICIT")

    long_space = _num(e5.get("available_space_atr_long"))
    short_space = _num(e5.get("available_space_atr_short"))
    if direction == "BUY" and 0 < long_space < 0.75:
        warnings.append("BUY_SPACE_CONSTRAINED")
    if direction == "SELL" and 0 < short_space < 0.75:
        warnings.append("SELL_SPACE_CONSTRAINED")

    confirmation_proven = any(k in e7b for k in ("CONFIRMED", "PROVEN", "VALIDATED"))
    risk_ready = any(k in e8b for k in ("RISK_READY", "ECONOMICALLY_ACCEPTABLE"))
    survival_ok = not any(k in e8b for k in ("SURVIVAL_NOT_PROVEN", "STRUCTURAL_SURVIVAL_NOT_PROVEN"))
    if confirmation_proven:
        evidence.append("CONFIRMATION_PROVEN")
    else:
        warnings.append("CONFIRMATION_NOT_PROVEN")
    if risk_ready and survival_ok:
        evidence.append("ECONOMIC_SURVIVAL_READY")
    else:
        warnings.append("ECONOMIC_SURVIVAL_UNPROVEN")

    strength = 0.0
    strength += 25.0 if control["dominant_actor"] in {"BUYERS", "SELLERS"} else 0.0
    strength += 20.0 if control["controlled_side"] in DIRECTIONS else 0.0
    strength += 20.0 if control["trapped_side"] in DIRECTIONS else 0.0
    strength += 10.0 if sweep and reclaim else 0.0
    strength += 10.0 if (accepted_above or rejected_below) else 0.0
    strength += 10.0 if confirmation_proven else 0.0
    strength += 10.0 if risk_ready and survival_ok else 0.0
    strength -= 15.0 if pending else 0.0
    strength -= 10.0 if transition else 0.0
    strength -= 10.0 if abs(sell_signals - buy_signals) <= 1 else 0.0
    strength = max(0.0, min(100.0, strength))

    # Control state is deliberately separate from trade permission.
    if control["trapped_side"] in DIRECTIONS and strength >= 75:
        state = "CONTROL_ESTABLISHED"
    elif control["dominant_actor"] in {"BUYERS", "SELLERS"} and control["controlled_side"] in DIRECTIONS:
        state = "CONTROL_FORMING"
    elif range_state:
        state = "BALANCED_NO_CONTROL"
    else:
        state = "CONTROL_UNPROVEN"

    if control["dominant_actor"] == "BUYERS":
        interpretation = "หลักฐานขณะนี้ให้น้ำหนักว่าฝั่ง Buyers กำลังเป็นฝ่ายควบคุมการประมูล แต่ยังต้องดู Acceptance/Follow-through เพื่อยืนยันการ Repricing"
    elif control["dominant_actor"] == "SELLERS":
        interpretation = "หลักฐานขณะนี้ให้น้ำหนักว่าฝั่ง Sellers กำลังเป็นฝ่ายควบคุมการประมูล แต่ยังต้องดู Acceptance/Follow-through เพื่อยืนยันการ Repricing"
    elif range_state:
        interpretation = "ตลาดอยู่ในสมดุลและกำลังค้นหา Liquidity ยังไม่พบฝ่ายใดควบคุมทิศทางอย่างมีหลักฐานเพียงพอ"
    elif transition:
        interpretation = "ตลาดอยู่ใน Transition มีแรงบางฝั่ง แต่ Participant-Control chain ยังไม่สมบูรณ์"
    else:
        interpretation = "ยังไม่มีหลักฐานเพียงพอที่จะระบุฝ่ายควบคุมตลาด"

    return {
        **control,
        "state": state,
        "strength": round(strength, 2),
        "evidence": list(dict.fromkeys(evidence)),
        "warnings": list(dict.fromkeys(warnings)),
        "thesis": thesis,
        "participant_chain": {
            "liquidity_taker": _text(e4.get("liquidity_taker")) or "UNRESOLVED",
            "response_actor": response or "UNRESOLVED",
            "liquidity_type": event or "UNRESOLVED",
            "event_level": level,
            "chain_complete": control["trapped_side"] in DIRECTIONS,
        },
        "interpretation": interpretation,
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    o = [_out(upstream.get(f"E{i}")) for i in range(1, 9)]
    e1, e2, e3, e4, e5, e6, e7, e8 = o
    reasons: list[str] = []
    conflicts: list[str] = []
    supports: list[str] = []
    counter: list[str] = []

    setup_dir = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"))
    trigger_dir = _direction(e7.get("direction"), setup_dir)
    risk_dir = _direction(e8.get("direction"), setup_dir)
    dirs = [d for d in (setup_dir, trigger_dir, risk_dir) if d in DIRECTIONS]
    if len(set(dirs)) > 1:
        conflicts.append("SETUP_TRIGGER_RISK_DIRECTION_CONFLICT")
    direction = setup_dir if setup_dir in DIRECTIONS and len(set(dirs)) <= 1 else "NEUTRAL"

    setup = str(e6.get("setup", e6.get("setup_family", "NONE")))
    thesis = str(e6.get("thesis", e6.get("candidate_setup_thesis", "UNRESOLVED")))
    maturity = _text(e6.get("maturity"))
    confirmation = _text(e7.get("confirmation", e7.get("confirmation_state", "UNRESOLVED")))
    risk_gate = _text(e8.get("risk_gate", e8.get("finding", "RISK_NOT_READY")))
    plan = e8.get("trade_plan") or {}

    setup_ready = maturity == "MATURE" and setup not in {"", "NONE", "UNKNOWN"} and direction in DIRECTIONS
    trigger_observed = bool(e7.get("trigger_observed") or e7.get("closed_candle_trigger") or e7.get("confirmation_proven"))
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED"} and trigger_observed
    economics_ready = risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE"} and bool(plan.get("valid") or plan.get("verified"))

    for i, eo in enumerate(o[:5], 1):
        f = _finding(eo)
        if f not in {"", "UNRESOLVED", "UNKNOWN", "NONE", "NO_SETUP", "NO_TRADE"}:
            supports.append(f"E{i}:{f}")
        for c in _codes(eo):
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

    for label, eo in (("E1", e1), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5)):
        d = _direction(eo.get("direction"), eo.get("directional_pressure"), eo.get("pressure"), eo.get("opportunity_direction"), eo.get("thesis_direction"))
        if d in DIRECTIONS and direction in DIRECTIONS and d != direction:
            conflicts.append(f"{label}:DIRECTION_OPPOSES_E6")

    mc = _market_control_brain(e1, e2, e3, e4, e5, e6, e7, e8, direction, setup, thesis)
    if mc["state"] == "CONTROL_ESTABLISHED":
        supports.append("E9:MARKET_CONTROL_ESTABLISHED")
    elif mc["state"] == "CONTROL_FORMING":
        supports.append("E9:MARKET_CONTROL_FORMING")
    else:
        counter.append("E9:MARKET_CONTROL_UNPROVEN")
    counter.extend(f"E9:{x}" for x in mc["warnings"])

    if direction == "NEUTRAL":
        reasons.append("DIRECTION_UNRESOLVED")
    if setup in {"", "NONE", "UNKNOWN"} or maturity in {"", "UNRESOLVED", "ABSENT", "FAILED", "INVALIDATED", "EXPIRED"}:
        reasons.append("SETUP_NOT_ESTABLISHED")
    elif not setup_ready:
        reasons.append("SETUP_NOT_MATURE")
    if not confirmation_ready:
        reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready:
        reasons.append("RISK_NOT_READY")

    rr = _num(e8.get("real_rr", e8.get("rr_used")))
    edge = _num(e8.get("economic_edge_r", e8.get("expected_value_r")))
    margin = _num(e8.get("economic_margin"))
    prob = _num(e8.get("stress_probability", e8.get("probability")), -1.0)
    rq = e8.get("risk_quality", {})
    risk_quality = _num(rq.get("score"), 0.0) if isinstance(rq, dict) else 0.0

    if 0 < rr < 1.50:
        reasons.append("ECONOMIC_EDGE_RR_BELOW_PROFESSIONAL_MINIMUM")
    if edge < 0.10:
        reasons.append("ECONOMIC_EDGE_TOO_THIN")
    if margin < 0.05:
        reasons.append("ECONOMIC_MARGIN_TOO_THIN")
    if 0 <= prob < 0.50:
        reasons.append("STRESSED_PROBABILITY_BELOW_MINIMUM")
    if risk_quality > 0 and risk_quality < 0.68:
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
    decision = direction if not hard_veto else "NO_TRADE"

    evidence_quality = max(0.0, min(100.0, 35.0 + 8.0 * len(supports) - 10.0 * len(counter) - 20.0 * len(conflicts)))
    gate_quality = 100.0 if setup_ready and confirmation_ready and economics_ready else 55.0
    edge_quality = 50.0 + 15.0 * min(2.0, max(0.0, edge / 0.10)) + 10.0 * min(2.0, max(0.0, margin / 0.05)) + (10.0 if rr >= 1.50 else -20.0)
    edge_quality = max(0.0, min(100.0, edge_quality))
    score = max(0.0, min(100.0, 0.40 * evidence_quality + 0.25 * gate_quality + 0.20 * edge_quality + 0.15 * mc["strength"]))
    if decision == "NO_TRADE":
        score = min(score, 64.0)

    authority_checks = {f"E{i}_finding": _finding(eo) for i, eo in enumerate(o, 1)}
    authority_checks.update({"E6_thesis": thesis, "E6_setup": setup, "E6_maturity": maturity, "E7_confirmation": confirmation, "E8_risk_gate": risk_gate})

    output = {
        "question": QUESTION,
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
        "reasoning_role": "MASTER_DECISION_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": True,
        "architecture": "SINGLE_AXIS_E1_TO_E9",
        "reconciliation": "EVIDENCE_HIERARCHY_PLUS_COUNTER_THESIS_PLUS_MARKET_CONTROL_NOT_VOTING",
        "authority_checks": authority_checks,
        "conflicts": conflicts,
        "evidence_used": "E1_E2_E3_E4_E5_E6_E7_E8",
        "supporting_evidence": supports,
        "counter_evidence": counter,
        "counter_thesis": counter,
        "evidence_hierarchy": ["E1_MARKET_CONTEXT", "E2_OPPORTUNITY", "E3_STRUCTURE", "E4_LIQUIDITY", "E5_LOCATION", "E6_SETUP", "E7_CONFIRMATION", "E8_ECONOMICS"],
        "market_control_brain": mc,
        "market_control_model": "LIQUIDITY -> PARTICIPANT_BEHAVIOR -> TRAP -> REPRICING -> TARGET",
        "evidence_quality": round(evidence_quality, 2),
        "edge_quality": round(edge_quality, 2),
        "decision_confidence": round(score, 2),
        "decision_score": round(score, 2),
        "quantitative_economics": {"real_rr": rr, "economic_edge_r": edge, "economic_margin": margin, "stress_probability": None if prob < 0 else prob, "risk_quality": risk_quality},
        "uncertainty": {"state": "HIGH" if score < 55 else "MEDIUM" if score < 75 else "LOW", "reasons": counter},
        "counter_evidence_vetoed": bool(conflicts),
        "invalidation": ["new closed-candle evidence changes a decisive prerequisite", "thesis invalidation or explicit domain contradiction", "economics edge falls below the professional decision floor", "market-control thesis loses its liquidity/participant-behavior chain"],
        "professional_reasoning": {
            "conclusion": thesis,
            "decision": decision,
            "why_trade": supports,
            "why_not_trade": dedupe(reasons + conflicts),
            "what_can_disprove": dedupe(counter + conflicts),
            "edge_assessment": edge,
            "evidence_quality": evidence_quality,
            "decision_confidence": score,
            "market_control_conclusion": mc["interpretation"],
        },
    }
    return EngineResult("E9", NAME, decision in DIRECTIONS, score, output, tuple(dedupe(reasons + conflicts)))
