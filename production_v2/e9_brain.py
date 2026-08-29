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
    trigger_observed = bool(
        e7.get("trigger_observed") or e7.get("closed_candle_trigger")
        or e7.get("confirmation_proven")
    )
    confirmation_ready = confirmation in {"CONFIRMED", "PROVEN", "VALIDATED"} and trigger_observed
    economics_ready = risk_gate in {"RISK_READY", "ECONOMICALLY_ACCEPTABLE"} and bool(plan.get("valid"))

    # E1-E5 are context/structure evidence: absence is not a veto; explicit
    # contradiction is. This preserves domain ownership while giving E9 veto power.
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

    # Explicit upstream directional disagreement is a thesis-level conflict.
    for label, eo in (("E1", e1), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5)):
        d = _direction(
            eo.get("direction"), eo.get("directional_pressure"), eo.get("pressure"),
            eo.get("opportunity_direction"), eo.get("thesis_direction")
        )
        if d in DIRECTIONS and direction in DIRECTIONS and d != direction:
            conflicts.append(f"{label}:DIRECTION_OPPOSES_E6")

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

    # E8 quantitative economics become explicit master-decision floors.
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
        if c in {
            "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH",
            "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE",
            "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM",
            "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
            "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
        }:
            reasons.append(c)
        elif c in {
            "SURVIVAL_FRAGILE", "ECONOMICS_SENSITIVITY_FRAGILE",
            "ECONOMIC_MARGIN_TOO_THIN", "PROBABILITY_EDGE_NOT_POSITIVE",
        }:
            counter.append(f"E8:{c}")

    def dedupe(items):
        return list(dict.fromkeys(str(x) for x in items if x))

    conflicts = dedupe(conflicts)
    counter = dedupe(counter)
    supports = dedupe(supports)
    reasons = dedupe(reasons)

    hard_reasons = {
        "DIRECTION_UNRESOLVED", "SETUP_NOT_ESTABLISHED", "SETUP_NOT_MATURE",
        "ENTRY_CONFIRMATION_NOT_PROVEN", "RISK_NOT_READY",
        "ECONOMIC_EDGE_RR_BELOW_PROFESSIONAL_MINIMUM", "ECONOMIC_EDGE_TOO_THIN",
        "ECONOMIC_MARGIN_TOO_THIN", "STRESSED_PROBABILITY_BELOW_MINIMUM",
        "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "REAL_RR_BELOW_MINIMUM",
        "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN",
        "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM",
        "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW",
        "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    }
    hard_veto = bool(conflicts) or any(r in hard_reasons for r in reasons)
    decision = direction if not hard_veto else "NO_TRADE"

    # Confidence is decision quality, not win probability and never 100/0.
    evidence_quality = max(0.0, min(100.0, 35.0 + 8.0 * len(supports)
                                      - 10.0 * len(counter) - 20.0 * len(conflicts)))
    gate_quality = 100.0 if setup_ready and confirmation_ready and economics_ready else 55.0
    edge_quality = 50.0 + 15.0 * min(2.0, max(0.0, edge / 0.10))
    edge_quality += 10.0 * min(2.0, max(0.0, margin / 0.05))
    edge_quality += 10.0 if rr >= 1.50 else -20.0
    edge_quality = max(0.0, min(100.0, edge_quality))
    score = max(0.0, min(100.0, 0.45 * evidence_quality + 0.30 * gate_quality + 0.25 * edge_quality))
    if decision == "NO_TRADE":
        score = min(score, 64.0)

    authority_checks = {f"E{i}_finding": _finding(eo) for i, eo in enumerate(o, 1)}
    authority_checks.update({
        "E6_thesis": thesis, "E6_setup": setup, "E6_maturity": maturity,
        "E7_confirmation": confirmation, "E8_risk_gate": risk_gate,
    })

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
        "reconciliation": "EVIDENCE_HIERARCHY_PLUS_COUNTER_THESIS_NOT_VOTING",
        "authority_checks": authority_checks,
        "conflicts": conflicts,
        "evidence_used": "E1_E2_E3_E4_E5_E6_E7_E8",
        "supporting_evidence": supports,
        "counter_evidence": counter,
        "counter_thesis": counter,
        "evidence_hierarchy": [
            "E1_MARKET_CONTEXT", "E2_OPPORTUNITY", "E3_STRUCTURE", "E4_LIQUIDITY",
            "E5_LOCATION", "E6_SETUP", "E7_CONFIRMATION", "E8_ECONOMICS",
        ],
        "evidence_quality": round(evidence_quality, 2),
        "edge_quality": round(edge_quality, 2),
        "decision_confidence": round(score, 2),
        "decision_score": round(score, 2),
        "quantitative_economics": {
            "real_rr": rr,
            "economic_edge_r": edge,
            "economic_margin": margin,
            "stress_probability": None if prob < 0 else prob,
            "risk_quality": risk_quality,
        },
        "uncertainty": {
            "state": "HIGH" if score < 55 else "MEDIUM" if score < 75 else "LOW",
            "reasons": counter,
        },
        "counter_evidence_vetoed": bool(conflicts),
        "invalidation": [
            "new closed-candle evidence changes a decisive prerequisite",
            "thesis invalidation or explicit domain contradiction",
            "economics edge falls below the professional decision floor",
        ],
        "professional_reasoning": {
            "conclusion": thesis,
            "decision": decision,
            "why_trade": supports,
            "why_not_trade": dedupe(reasons + conflicts),
            "what_can_disprove": dedupe(counter + conflicts),
            "edge_assessment": edge,
            "evidence_quality": evidence_quality,
            "decision_confidence": score,
        },
    }
    return EngineResult("E9", NAME, decision in DIRECTIONS, score, output,
                        tuple(dedupe(reasons + conflicts)))
