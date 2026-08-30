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
ECONOMIC_HARD_CODES = {
    "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
    "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW",
    "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
}


def _out(e):
    return e.output if e else {}


def _text(v):
    return str(v or "").upper().strip()


def _num(v, default=0.0):
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _codes(o):
    vals = o.get("reason_codes") or o.get("reasons") or o.get("counter_evidence") or []
    if isinstance(vals, str):
        vals = [vals]
    return [_text(x) for x in vals if x]


def _finding(o):
    return _text(o.get("finding", o.get("state", o.get("market_state", "UNRESOLVED"))))


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


def _blob(o):
    keys = ("direction", "pressure", "directional_pressure", "structure_direction", "bias",
            "opportunity_direction", "thesis_direction", "regime", "market_regime",
            "liquidity_state", "liquidity_type", "event", "response_actor", "liquidity_taker",
            "value_response_direction", "repricing_direction", "intent", "market_intent",
            "auction_phase", "auction_state", "finding", "state")
    parts = [_finding(o), *_codes(o)]
    parts.extend(_text(o.get(k)) for k in keys if k in o)
    return " ".join(x for x in parts if x)


def _dedupe(items):
    return list(dict.fromkeys(str(x) for x in items if x))


def _first(*values):
    for v in values:
        if v is not None and str(v).strip():
            return v
    return None


def _market_control_brain(e1, e2, e3, e4, e5, e6, e7, e8, direction, setup, thesis):
    """E9-only causal market-control report; never grants execution permission."""
    e1b, e2b, e3b, e4b, e5b = map(_blob, (e1, e2, e3, e4, e5))
    event = _text(_first(e4.get("event"), e4.get("finding"), e4.get("liquidity_type")))
    taker = _text(e4.get("liquidity_taker"))
    responder = _text(e4.get("response_actor"))
    state4 = _text(e4.get("auction_state"))
    info4 = _text(e4.get("auction_information"))
    level = _first(e4.get("event_level"), e4.get("level"), e4.get("liquidity_level"),
                   e4.get("swept_level"), e4.get("target_level"), e4.get("liquidity_target"))
    sweep = any(k in e4b for k in ("SWEEP", "LIQUIDITY_TAKEN", "STOP_RUN"))
    rejection = any(k in e4b for k in ("REJECTION", "REJECTED", "FAILED_BREAK", "RECLAIM"))
    explicit_taker = taker in {"BUYERS", "SELLERS"}
    explicit_response = responder in {"BUYERS", "SELLERS"}
    pending = state4 in {"PENDING", "UNRESOLVED", "DEVELOPING", "WATCH"} or any(
        k in e4b for k in ("NOT_TERMINALLY_CONFIRMED", "TRUE_AUCTION_CONFIRMATION_NOT_PROVEN", "LOW_INFORMATION")
    )
    terminal = not pending and explicit_response and (sweep or rejection)
    transition = any(k in e1b + " " + e2b + " " + e3b for k in ("TRANSITION", "WATCH"))
    range_state = any(k in e1b + " " + e2b for k in ("RANGE", "BALANCED", "MEAN_REVERSION"))
    target = level if level is not None else (event if event not in {"", "UNKNOWN", "UNRESOLVED", "NONE", "LOW_INFORMATION"} else "UNRESOLVED")
    evidence, warnings, conflicts = [], [], []
    dominant, controlled, trapped, intent, repricing = "UNPROVEN", "NONE", "NONE", "DIRECTIONAL_INTENT_UNPROVEN", "NEUTRAL"

    if explicit_taker: evidence.append("LIQUIDITY_TAKER_OBSERVED")
    if explicit_response: evidence.append("RESPONSE_ACTOR_OBSERVED")
    if sweep: evidence.append("LIQUIDITY_TAKE_EVENT_OBSERVED")
    if rejection: evidence.append("REJECTION_OR_RECLAIM_OBSERVED")

    if explicit_taker and explicit_response and taker != responder and (sweep or rejection):
        dominant = responder
        controlled = "BUY" if responder == "BUYERS" else "SELL"
        repricing = controlled
        evidence.append("RESPONSE_OPPOSES_LIQUIDITY_TAKER")
        intent = "POTENTIAL_REPRICING_" + controlled
        if terminal:
            trapped = "SELL" if responder == "BUYERS" else "BUY"
            intent = "FORCED_REPRICING_" + controlled
            evidence.append("TRAP_CHAIN_SUPPORTED")
    elif explicit_response and (sweep or rejection):
        dominant = responder
        controlled = "BUY" if responder == "BUYERS" else "SELL"
        repricing = controlled
        intent = "POTENTIAL_REPRICING_" + controlled
        evidence.append("RESPONSE_ACTOR_AFTER_LIQUIDITY_EVENT")
    elif explicit_taker:
        dominant = taker
        evidence.append("LIQUIDITY_TAKER_ONLY_NO_CONTROL_PROOF")

    buy_context = sum([
        "PRESSURE=UP" in e1b or "PRESSURE UP" in e1b,
        _direction(e1.get("direction"), e1.get("structure_direction")) == "BUY",
        _direction(e2.get("direction"), e2.get("opportunity_direction"), e2.get("thesis_direction")) == "BUY",
        _direction(e3.get("direction"), e3.get("structure_direction"), e3.get("bias")) == "BUY",
        _direction(e5.get("direction"), e5.get("repricing_direction"), e5.get("value_response_direction")) == "BUY",
        "BUY" in _blob(e6),
    ])
    sell_context = sum([
        "PRESSURE=DOWN" in e1b or "PRESSURE DOWN" in e1b,
        _direction(e1.get("direction"), e1.get("structure_direction")) == "SELL",
        _direction(e2.get("direction"), e2.get("opportunity_direction"), e2.get("thesis_direction")) == "SELL",
        _direction(e3.get("direction"), e3.get("structure_direction"), e3.get("bias")) == "SELL",
        _direction(e5.get("direction"), e5.get("repricing_direction"), e5.get("value_response_direction")) == "SELL",
        "SELL" in _blob(e6),
    ])
    if dominant == "UNPROVEN":
        if buy_context >= 3 and buy_context > sell_context + 1:
            dominant, controlled, repricing, intent = "BUYERS", "BUY", "BUY", "DIRECTIONAL_INTENT_FORMING_BUY"
            evidence.append("CROSS_ENGINE_BUYER_CONVERGENCE")
        elif sell_context >= 3 and sell_context > buy_context + 1:
            dominant, controlled, repricing, intent = "SELLERS", "SELL", "SELL", "DIRECTIONAL_INTENT_FORMING_SELL"
            evidence.append("CROSS_ENGINE_SELLER_CONVERGENCE")
        elif buy_context >= 2 and sell_context >= 2:
            dominant, controlled, repricing, intent = "CONTESTED", "NONE", "NEUTRAL", "DIRECTIONAL_INTENT_CONTESTED"
            conflicts.append("DIRECTIONAL_CONTROL_EVIDENCE_CONTESTED")

    if pending: warnings.append("AUCTION_NOT_TERMINALLY_CONFIRMED")
    if info4 in {"LOW_INFORMATION", "MEDIUM_INFORMATION"}: warnings.append("AUCTION_INFORMATION_NOT_MAXIMAL")
    if not explicit_response: warnings.append("PARTICIPANT_RESPONSE_NOT_EXPLICIT")
    if transition: warnings.append("MARKET_STATE_TRANSITION")
    if range_state and dominant not in {"BUYERS", "SELLERS"}:
        intent = "LIQUIDITY_SEEKING_WITHOUT_DIRECTIONAL_CONTROL"

    accepted = any(k in e5b for k in ("ACCEPTED_ABOVE_VALUE", "ACCEPTED_BELOW_VALUE", "VALUE_ACCEPTANCE", "ACCEPTANCE_ABOVE", "ACCEPTANCE_BELOW"))
    follow = any(k in (_blob(e7) + " " + _blob(e8)) for k in ("FOLLOW_THROUGH_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN", "CONFIRMED", "PROVEN", "VALIDATED"))
    if accepted: evidence.append("VALUE_ACCEPTANCE_OBSERVED")
    if follow: evidence.append("FOLLOW_THROUGH_EVIDENCE_PRESENT")
    chain_complete = bool(explicit_taker and explicit_response and taker != responder and (sweep or rejection) and target not in {"UNRESOLVED", None, ""} and terminal and (accepted or follow))
    if chain_complete: evidence.append("MARKET_CONTROL_CHAIN_COMPLETE")
    else: warnings.append("MARKET_CONTROL_CHAIN_INCOMPLETE")

    if dominant in {"BUYERS", "SELLERS"} and controlled in DIRECTIONS:
        control_state = "CONTROL_ESTABLISHED" if chain_complete else "CONTROL_FORMING"
    elif dominant == "CONTESTED":
        control_state = "CONTROL_CONTESTED"
    elif range_state:
        control_state = "BALANCED_NO_CONTROL"
    else:
        control_state = "CONTROL_UNPROVEN"

    strength = 0.0
    strength += 15 if explicit_taker else 0
    strength += 20 if explicit_response else 0
    strength += 20 if (sweep or rejection) else 0
    strength += 15 if explicit_taker and explicit_response and taker != responder else 0
    strength += 15 if terminal else 0
    strength += 10 if (accepted or follow) else 0
    strength -= 20 if pending else 0
    strength -= 10 if info4 == "LOW_INFORMATION" else 0
    strength -= 10 if transition else 0
    strength -= 15 if dominant == "CONTESTED" else 0
    if not chain_complete: strength = min(strength, 74.0)
    strength = max(0.0, min(100.0, strength))

    if control_state == "CONTROL_ESTABLISHED":
        interpretation = "Participant-control chain ครบ: liquidity → response → repricing → target และมี acceptance/follow-through"
    elif control_state == "CONTROL_FORMING":
        interpretation = "พบ controller ที่มีน้ำหนัก แต่ auction ยังไม่ terminal; จึงรายงานเป็น control-forming ไม่ใช่ established"
    elif control_state == "CONTROL_CONTESTED":
        interpretation = "หลักฐาน Buyers/Sellers แข่งขันกัน ยังไม่ระบุฝ่ายควบคุมแบบเอกฉันท์"
    elif control_state == "BALANCED_NO_CONTROL":
        interpretation = "ตลาดสมดุลและกำลังค้นหา liquidity ยังไม่มี directional control ที่พิสูจน์ได้"
    else:
        interpretation = "ยังไม่มี causal chain เพียงพอที่จะระบุฝ่ายควบคุมตลาด"

    return {
        "state": control_state, "strength": round(strength, 2), "dominant_actor": dominant,
        "controlled_side": controlled, "trapped_side": trapped if chain_complete else "NONE",
        "liquidity_target": target, "market_intent": intent, "auction_phase": "TERMINAL_RESPONSE" if terminal else "POST_SWEEP_RECLAIM" if sweep and rejection else "LIQUIDITY_INTERACTION" if event else "BALANCED_RANGE" if range_state else "TRANSITION_AUCTION" if transition else "UNRESOLVED",
        "repricing_direction": repricing, "evidence": _dedupe(evidence), "warnings": _dedupe(warnings), "conflicts": _dedupe(conflicts),
        "thesis": thesis, "setup": setup,
        "directional_evidence": {"buy_signals": buy_context, "sell_signals": sell_context, "net": buy_context - sell_context, "direction_from_e6": direction},
        "participant_chain": {
            "liquidity_taker": taker or "UNPROVEN", "response_actor": responder or "UNPROVEN", "controller_role": dominant,
            "controller_basis": "TERMINAL_RESPONSE_AFTER_LIQUIDITY_EVENT" if terminal and explicit_response else "RESPONSE_AFTER_LIQUIDITY_EVENT" if explicit_response else "CROSS_ENGINE_CONVERGENCE" if dominant in {"BUYERS", "SELLERS"} else "UNPROVEN",
            "liquidity_type": _text(e4.get("liquidity_type")) or "UNPROVEN", "event_level": level,
            "chain_complete": chain_complete, "causal_order": ["LIQUIDITY", "PARTICIPANT_BEHAVIOR", "TRAP", "REPRICING", "TARGET"],
        },
        "interpretation": interpretation, "reporting_only": True, "cannot_override_execution_gates": True,
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    e = [_out(upstream.get(f"E{i}")) for i in range(1, 9)]
    e1, e2, e3, e4, e5, e6, e7, e8 = e
    reasons, conflicts, supports, counter = [], [], [], []
    setup_dir = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"))
    trigger_dir = _direction(e7.get("direction"), e7.get("confirmation_direction"), setup_dir)
    risk_dir = _direction(e8.get("direction"), e8.get("risk_direction"), setup_dir)
    dirs = [d for d in (setup_dir, trigger_dir, risk_dir) if d in DIRECTIONS]
    if len(set(dirs)) > 1: conflicts.append("SETUP_TRIGGER_RISK_DIRECTION_CONFLICT")
    direction = setup_dir if setup_dir in DIRECTIONS and len(set(dirs)) <= 1 else "NEUTRAL"
    setup = str(e6.get("setup", e6.get("setup_family", "NONE")))
    thesis = str(e6.get("thesis", e6.get("candidate_setup_thesis", "UNRESOLVED")))
    maturity = _text(e6.get("maturity"))
    confirmation = _text(e7.get("confirmation", e7.get("confirmation_state", "UNRESOLVED")))
    risk_gate = _text(e8.get("risk_gate", e8.get("finding", "RISK_NOT_READY")))
    plan = e8.get("trade_plan") or {}
    setup_ready = maturity in {"MATURE", "TRADE_READY"} and setup not in {"", "NONE", "UNKNOWN"} and direction in DIRECTIONS
    trigger_observed = bool(e7.get("trigger_observed") or e7.get("closed_candle_trigger") or e7.get("confirmation_proven"))
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED"} and trigger_observed
    economics_ready = risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE"} and bool(plan.get("valid") or plan.get("verified"))

    for i, eo in enumerate(e[:5], 1):
        f = _finding(eo)
        if f not in {"", "UNRESOLVED", "UNKNOWN", "NONE", "NO_SETUP", "NO_TRADE"}: supports.append(f"E{i}:{f}")
        for c in _codes(eo):
            if c in HARD_CONFLICT_CODES or "INVALIDAT" in c or "CONFLICT" in c or "OPPOS" in c: conflicts.append(f"E{i}:{c}")
            elif c in SOFT_CODES: counter.append(f"E{i}:{c}")
    for label, eo in (("E6", e6), ("E7", e7), ("E8", e8)):
        for c in _codes(eo):
            if c in HARD_CONFLICT_CODES or "INVALIDAT" in c or "CONFLICT" in c or "OPPOS" in c: conflicts.append(f"{label}:{c}")
            elif c not in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"}: counter.append(f"{label}:{c}")
    for label, eo in (("E1", e1), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5)):
        d = _direction(eo.get("direction"), eo.get("directional_pressure"), eo.get("pressure"), eo.get("opportunity_direction"), eo.get("thesis_direction"), eo.get("structure_direction"))
        if d in DIRECTIONS and direction in DIRECTIONS and d != direction: conflicts.append(f"{label}:DIRECTION_OPPOSES_E6")

    mc = _market_control_brain(e1, e2, e3, e4, e5, e6, e7, e8, direction, setup, thesis)
    conflicts.extend(f"E9:{x}" for x in mc["conflicts"])
    supports.append("E9:MARKET_CONTROL_ESTABLISHED" if mc["state"] == "CONTROL_ESTABLISHED" else "E9:MARKET_CONTROL_FORMING" if mc["state"] == "CONTROL_FORMING" else "E9:MARKET_CONTROL_CONTESTED" if mc["state"] == "CONTROL_CONTESTED" else "E9:MARKET_CONTROL_UNPROVEN")
    if mc["state"] == "CONTROL_CONTESTED": supports.pop(); counter.append("E9:MARKET_CONTROL_CONTESTED")
    counter.extend(f"E9:{x}" for x in mc["warnings"])

    if direction == "NEUTRAL": reasons.append("DIRECTION_UNRESOLVED")
    if setup in {"", "NONE", "UNKNOWN"} or maturity in {"", "UNRESOLVED", "ABSENT", "FAILED", "INVALIDATED", "EXPIRED"}: reasons.append("SETUP_NOT_ESTABLISHED")
    elif not setup_ready: reasons.append("SETUP_NOT_MATURE")
    if not confirmation_ready: reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready: reasons.append("RISK_NOT_READY")
    rr = _num(e8.get("real_rr", e8.get("rr_used")))
    edge = _num(e8.get("economic_edge_r", e8.get("expected_value_r")))
    margin = _num(e8.get("economic_margin"))
    prob = _num(e8.get("stress_probability", e8.get("probability")), -1.0)
    rq = e8.get("risk_quality", {})
    risk_quality = _num(rq.get("score"), 0.0) if isinstance(rq, dict) else 0.0
    if 0 < rr < 1.50: reasons.append("ECONOMIC_EDGE_RR_BELOW_PROFESSIONAL_MINIMUM")
    if edge < 0.10: reasons.append("ECONOMIC_EDGE_TOO_THIN")
    if margin < 0.05: reasons.append("ECONOMIC_MARGIN_TOO_THIN")
    if 0 <= prob < 0.50: reasons.append("STRESSED_PROBABILITY_BELOW_MINIMUM")
    if risk_quality > 0 and risk_quality < 0.68: reasons.append("RISK_QUALITY_BELOW_DECISION_THRESHOLD")
    for c in _codes(e8):
        if c in ECONOMIC_HARD_CODES: reasons.append(c)
        elif c in {"SURVIVAL_FRAGILE", "ECONOMICS_SENSITIVITY_FRAGILE", "ECONOMIC_MARGIN_TOO_THIN", "PROBABILITY_EDGE_NOT_POSITIVE"}: counter.append(f"E8:{c}")
    conflicts, counter, supports, reasons = map(_dedupe, (conflicts, counter, supports, reasons))
    hard_reasons = {"DIRECTION_UNRESOLVED", "SETUP_NOT_ESTABLISHED", "SETUP_NOT_MATURE", "ENTRY_CONFIRMATION_NOT_PROVEN", "RISK_NOT_READY", "ECONOMIC_EDGE_RR_BELOW_PROFESSIONAL_MINIMUM", "ECONOMIC_EDGE_TOO_THIN", "ECONOMIC_MARGIN_TOO_THIN", "STRESSED_PROBABILITY_BELOW_MINIMUM", "RISK_QUALITY_BELOW_DECISION_THRESHOLD", *ECONOMIC_HARD_CODES}
    hard_veto = bool(conflicts) or any(r in hard_reasons for r in reasons)
    decision = direction if not hard_veto else "NO_TRADE"
    evidence_quality = max(0.0, min(100.0, 35.0 + 8.0 * len(supports) - 10.0 * len(counter) - 20.0 * len(conflicts)))
    gate_quality = 100.0 if setup_ready and confirmation_ready and economics_ready else 55.0
    edge_quality = 50.0 + 15.0 * min(2.0, max(0.0, edge / 0.10)) + 10.0 * min(2.0, max(0.0, margin / 0.05)) + (10.0 if rr >= 1.50 else -20.0)
    edge_quality = max(0.0, min(100.0, edge_quality))
    score = max(0.0, min(100.0, 0.40 * evidence_quality + 0.25 * gate_quality + 0.20 * edge_quality + 0.15 * mc["strength"]))
    if decision == "NO_TRADE": score = min(score, 64.0)
    authority = {f"E{i}_finding": _finding(eo) for i, eo in enumerate(e, 1)}
    authority.update({"E6_thesis": thesis, "E6_setup": setup, "E6_maturity": maturity, "E7_confirmation": confirmation, "E8_risk_gate": risk_gate})
    output = {
        "question": QUESTION, "finding": decision,
        "observations": [f"direction={direction}", f"setup={setup}", f"maturity={maturity or 'UNRESOLVED'}", f"confirmation={confirmation or 'UNRESOLVED'}", f"risk_gate={risk_gate or 'UNRESOLVED'}", f"market_control={mc['state']}", f"control_strength={mc['strength']}"],
        "reasons": _dedupe(reasons + conflicts), "decision": decision, "direction": direction, "thesis": thesis, "setup": setup, "maturity": maturity, "confirmation": confirmation, "risk_gate": risk_gate,
        "setup_ready": setup_ready, "confirmation_ready": confirmation_ready, "economics_ready": economics_ready, "trade_plan": plan,
        "reasoning_role": "MASTER_DECISION_ANALYST", "decision_authority": "E9", "trade_decision_authority": True, "architecture": "SINGLE_AXIS_E1_TO_E9",
        "reconciliation": "EVIDENCE_HIERARCHY_PLUS_COUNTER_THESIS_PLUS_MARKET_CONTROL_NOT_VOTING", "authority_checks": authority,
        "conflicts": conflicts, "evidence_used": "E1_E2_E3_E4_E5_E6_E7_E8", "supporting_evidence": supports, "counter_evidence": counter, "counter_thesis": counter,
        "evidence_hierarchy": ["E1_MARKET_CONTEXT", "E2_OPPORTUNITY", "E3_STRUCTURE", "E4_LIQUIDITY", "E5_LOCATION", "E6_SETUP", "E7_CONFIRMATION", "E8_ECONOMICS"],
        "market_control_brain": mc, "market_control_model": "LIQUIDITY -> PARTICIPANT_BEHAVIOR -> TRAP -> REPRICING -> TARGET",
        "market_control_reporting": {"state": mc["state"], "intent": mc["market_intent"], "dominant_actor": mc["dominant_actor"], "controlled_side": mc["controlled_side"], "trapped_side": mc["trapped_side"], "liquidity_target": mc["liquidity_target"], "repricing_direction": mc["repricing_direction"], "auction_phase": mc["auction_phase"], "control_strength": mc["strength"], "interpretation": mc["interpretation"], "evidence": mc["evidence"], "warnings": mc["warnings"], "chain_complete": mc["participant_chain"]["chain_complete"], "controller_role": mc["participant_chain"]["controller_role"], "controller_basis": mc["participant_chain"]["controller_basis"]},
        "evidence_quality": round(evidence_quality, 2), "edge_quality": round(edge_quality, 2), "decision_confidence": round(score, 2), "decision_score": round(score, 2),
        "quantitative_economics": {"real_rr": rr, "economic_edge_r": edge, "economic_margin": margin, "stress_probability": None if prob < 0 else prob, "risk_quality": risk_quality},
        "uncertainty": {"state": "HIGH" if score < 55 else "MEDIUM" if score < 75 else "LOW", "reasons": counter}, "counter_evidence_vetoed": bool(conflicts),
        "invalidation": ["new closed-candle evidence changes a decisive prerequisite", "thesis invalidation or explicit domain contradiction", "economics edge falls below the professional decision floor", "market-control thesis loses its liquidity/participant-behavior chain"],
        "professional_reasoning": {"conclusion": thesis, "decision": decision, "why_trade": supports, "why_not_trade": _dedupe(reasons + conflicts), "what_can_disprove": _dedupe(counter + conflicts), "edge_assessment": edge, "evidence_quality": evidence_quality, "decision_confidence": score, "market_control_conclusion": mc["interpretation"]},
    }
    return EngineResult("E9", NAME, decision in DIRECTIONS, score, output, tuple(_dedupe(reasons + conflicts)))
