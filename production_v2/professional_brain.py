from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .engines import ENGINE_NAMES, ENGINE_WEIGHTS, EDGE_THRESHOLD, run_engine as _engine_analyzer

SPECIALIST_QUESTIONS = {
    "E1": "What market state is present right now?",
    "E2": "What opportunity/regime is the market offering?",
    "E3": "What does market structure say?",
    "E4": "Where is liquidity and what did price do with it?",
    "E5": "Is current price in an advantageous location?",
    "E6": "What setup, if any, is forming?",
    "E7": "Is the setup thesis confirmed by price action?",
    "E8": "What are the trade economics, invalidation and asymmetry?",
}


def run_professional_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    """Run one specialist against the shared market snapshot.

    This function deliberately does not read E1-E8 results and never assigns
    execution authority. A low-quality conclusion is evidence, not a gate.
    """
    raw = _engine_analyzer(engine_id, dict(context))
    output = dict(raw.output)
    output["analysis_status"] = "COMPLETE"
    output["analysis_complete"] = True
    output["specialist_question"] = SPECIALIST_QUESTIONS.get(engine_id, "Analyze the assigned market dimension.")
    output["trade_decision_authority"] = False
    output["specialist_gate"] = "NONE"
    output["gate"] = None
    output["input_mode"] = "SHARED_MARKET_SNAPSHOT"
    output["upstream_engine_dependency"] = None
    output["reasoning_role"] = "SPECIALIST_EVIDENCE"
    output["analysis_reason_codes"] = list(raw.reason_codes)
    if engine_id == "E8":
        plan = dict(output.get("trade_plan") or {})
        direction = plan.pop("direction", None)
        if direction in {"BUY", "SELL"}:
            plan["orientation"] = "UP" if direction == "BUY" else "DOWN"
        output["trade_plan"] = plan
    return EngineResult(raw.engine_id, raw.name, True, raw.score, output, raw.reason_codes)


def _weighted_evidence(upstream: list[EngineResult]) -> float:
    values = {e.engine_id: float(e.score) for e in upstream if e.engine_id in ENGINE_WEIGHTS}
    weight = sum(ENGINE_WEIGHTS[k] for k in values)
    return round(sum(values[k] * ENGINE_WEIGHTS[k] for k in values) / weight, 2) if weight else 0.0


def run_professional_e9(context: dict[str, Any], upstream: list[EngineResult]) -> EngineResult:
    """E9 is the sole master decision brain and synthesizes independent evidence."""
    by_id = {e.engine_id: e for e in upstream}
    e6, e7, e8 = by_id.get("E6"), by_id.get("E7"), by_id.get("E8")
    plan = dict(e8.output.get("trade_plan", {}) if e8 else {})
    evidence_score = _weighted_evidence(upstream)
    r7 = e7.output.get("professional_reasoning", {}) if e7 else {}
    confirmation_ready = (
        r7.get("confirmation") == "CONFIRMATION_PASS"
        and r7.get("trigger_quality") == "QUALITY_PASS"
        and r7.get("follow_through") == "FOLLOW_THROUGH_OBSERVED"
    )
    economics_ready = bool(plan.get("valid")) and float(plan.get("rr_tp2", plan.get("rr", 0)) or 0) >= float(plan.get("min_rr", 1.5) or 1.5)
    orientation = plan.get("orientation") if economics_ready else None
    direction = {"UP": "BUY", "DOWN": "SELL"}.get(orientation)
    reasons: list[str] = []
    if e6 is None or e6.output.get("trade_plan", {}).get("setup") in {None, "NONE"} or e6.output.get("setup") in {None, "NONE", "NO_VALID_SETUP"}:
        reasons.append("NO_MATURE_SETUP")
    if not confirmation_ready:
        reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready:
        reasons.append("TRADE_ECONOMICS_NOT_READY")
    if evidence_score < EDGE_THRESHOLD:
        reasons.append("EVIDENCE_SCORE_BELOW_THRESHOLD")
    # Directional disagreement is evidence conflict, not an upstream gate.
    e1 = by_id.get("E1")
    e3 = by_id.get("E3")
    e1_bias = (e1.output.get("professional_reasoning", {}) if e1 else {}).get("bias")
    e3_bias = e3.output.get("professional_reasoning", {}).get("bias") if e3 else None
    if e1_bias and e3_bias and e1_bias not in {"NEUTRAL", e3_bias}:
        reasons.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    final = bool(direction in {"BUY", "SELL"} and confirmation_ready and economics_ready and evidence_score >= EDGE_THRESHOLD and "DIRECTIONAL_EVIDENCE_CONFLICT" not in reasons)
    decision = direction if final else "NO_TRADE"
    out = {
        "decision": decision,
        "decision_authority": "E9",
        "trade_decision_authority": True,
        "pipeline": "PARALLEL:E1|E2|E3|E4|E5|E6|E7|E8 -> E9",
        "trade_plan": plan,
        "evidence_score": evidence_score,
        "edge_score": evidence_score,
        "edge_threshold": EDGE_THRESHOLD,
        "gate_passed": final,
        "professional_decision": "APPROVE_TRADE" if final else "NO_TRADE",
        "blocked_by": None,
        "decision_reasons": reasons,
        "evidence_conflicts": [r for r in reasons if "CONFLICT" in r],
        "specialist_conclusions": {e.engine_id: e.output.get("conclusion", e.output.get("professional_reasoning", {})) for e in upstream},
        "analysis_complete": True,
    }
    return EngineResult("E9", ENGINE_NAMES.get("E9", "Master Decision"), final, evidence_score, out, tuple(reasons))
