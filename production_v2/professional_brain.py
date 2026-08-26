from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .engines import ENGINE_NAMES, ENGINE_WEIGHTS, EDGE_THRESHOLD, run_engine as _legacy_run_engine

_FATAL_REASONS = {"E1_DATA_INVALID", "E3_STRUCTURE_INVALIDATED", "E6_SETUP_INVALIDATED"}


def _status_from_legacy(result: EngineResult) -> str:
    reasons = set(result.reason_codes)
    if reasons & _FATAL_REASONS:
        return "CONFLICT_OR_INVALID"
    if result.engine_id == "E7":
        confirmation = result.output.get("professional_reasoning", {}).get("confirmation")
        return "CONFIRMED" if confirmation == "CONFIRMATION_PASS" else "NOT_CONFIRMED"
    if result.engine_id == "E8":
        return "ECONOMICS_READY" if result.output.get("trade_plan", {}).get("valid") else "ECONOMICS_UNAVAILABLE"
    if result.score >= 75:
        return "STRONG_EVIDENCE"
    if result.score >= 55:
        return "PARTIAL_EVIDENCE"
    return "WEAK_EVIDENCE"


def _professional_answer(engine_id: str, output: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    """Create the specialist's conclusion without assigning a trade action."""
    r = dict(output.get("professional_reasoning") or {})
    r["inputs_from_previous_engines"] = [
        key for key, value in prior.items()
        if key.startswith("E") and key.endswith("_result") and isinstance(value, dict)
    ]
    r["specialist_status"] = _status_from_legacy(
        EngineResult(engine_id, ENGINE_NAMES[engine_id], True, float(output.get("evidence_quality", 0)), output)
    )
    r["specialist_conclusion"] = {
        "E1": "กำหนดสภาวะตลาดและ Market Bias เพื่ออธิบายว่าตลาดกำลังอยู่ในสภาพใด",
        "E2": "เลือก Regime และ Playbook ที่เหมาะกับสภาวะจาก E1 โดยยังไม่ตัดสินการเข้าเทรด",
        "E3": "ตรวจว่า Market Structure สนับสนุน ขัดแย้ง หรือยังไม่ชัดเจนเมื่อเทียบกับ E1-E2",
        "E4": "ระบุ Liquidity ที่เกี่ยวข้องและตีความ Sweep, Reclaim, Rejection หรือการไม่มี Event",
        "E5": "ประเมิน Location, Extension และ Space ว่าราคาปัจจุบันมีความได้เปรียบหรือเสียเปรียบ",
        "E6": "ระบุ Trade Setup ที่เกิดขึ้น สถานะการก่อตัว คุณภาพ และ Invalidation",
        "E7": "พิสูจน์ Trigger, Follow-through และ Confirmation จากแท่งที่ปิดแล้ว",
        "E8": "ประเมิน Invalidation, Stop, Target, RR และ Trade Economics ว่าคุ้มความเสี่ยงหรือไม่",
    }.get(engine_id, "")
    return r


def run_professional_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    raw = _legacy_run_engine(engine_id, context)
    output = dict(raw.output)
    output["professional_reasoning"] = _professional_answer(engine_id, output, context)
    output["analysis_status"] = _status_from_legacy(raw)
    output["analysis_complete"] = True
    output["handoff_allowed"] = True
    output["trade_decision_authority"] = False
    output["analysis_reason_codes"] = list(raw.reason_codes)
    fatal = bool(set(raw.reason_codes) & _FATAL_REASONS)
    # Missing trigger, weak setup, no sweep, or weak economics are specialist
    # conclusions. They must reach E9 rather than stopping the pipeline.
    if engine_id == "E8" and not output.get("trade_plan", {}).get("valid"):
        fatal = False
    output["specialist_gate"] = "ANALYSIS_FATAL" if fatal else "ANALYSIS_COMPLETE"
    return EngineResult(raw.engine_id, raw.name, not fatal, raw.score, output, raw.reason_codes)


def _weighted_evidence(upstream: list[EngineResult]) -> float:
    values = {e.engine_id: float(e.score) for e in upstream if e.engine_id in ENGINE_WEIGHTS}
    weight = sum(ENGINE_WEIGHTS[k] for k in values)
    return round(sum(values[k] * ENGINE_WEIGHTS[k] for k in values) / weight, 2) if weight else 0.0


def run_professional_e9(context: dict[str, Any], upstream: list[EngineResult]) -> EngineResult:
    """E9 is the only component allowed to emit BUY, SELL, or NO_TRADE."""
    by_id = {e.engine_id: e for e in upstream}
    e6, e7, e8 = by_id.get("E6"), by_id.get("E7"), by_id.get("E8")
    plan = e8.output.get("trade_plan", {}) if e8 else {}
    evidence_score = _weighted_evidence(upstream)
    r7 = e7.output.get("professional_reasoning", {}) if e7 else {}
    confirmation_ready = (
        r7.get("confirmation") == "CONFIRMATION_PASS"
        and r7.get("trigger_quality") == "QUALITY_PASS"
        and r7.get("follow_through") == "FOLLOW_THROUGH_OBSERVED"
    )
    economics_ready = bool(plan.get("valid")) and float(plan.get("rr_tp2", 0)) >= float(plan.get("min_rr", 1.5))
    critical_conflicts = [e.engine_id for e in upstream if e.engine_id in {"E1", "E3", "E6"} and not e.gate_passed]
    direction = plan.get("direction") if economics_ready else None
    reasons: list[str] = []
    if critical_conflicts:
        reasons.append("CRITICAL_EVIDENCE_CONFLICT:" + ",".join(critical_conflicts))
    if not confirmation_ready:
        reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics_ready:
        reasons.append("TRADE_ECONOMICS_NOT_READY")
    if evidence_score < EDGE_THRESHOLD:
        reasons.append("EVIDENCE_SCORE_BELOW_THRESHOLD")
    final = bool(direction in {"BUY", "SELL"} and confirmation_ready and economics_ready and not critical_conflicts and evidence_score >= EDGE_THRESHOLD)
    decision = direction if final else "NO_TRADE"
    out = {
        "decision": decision,
        "decision_authority": "E9",
        "trade_decision_authority": True,
        "pipeline": "E1>E2>E3>E4>E5>E6>E7>E8>E9",
        "trade_plan": plan,
        "evidence_score": evidence_score,
        "edge_score": evidence_score,
        "edge_threshold": EDGE_THRESHOLD,
        "gate_passed": final,
        "professional_decision": "APPROVE_TRADE" if final else "NO_TRADE",
        "blocked_by": None,
        "decision_reasons": reasons,
        "specialist_conclusions": {e.engine_id: e.output.get("professional_reasoning", {}).get("specialist_conclusion", "") for e in upstream},
        "setup_thesis": e6.output.get("professional_reasoning", {}) if e6 else {},
        "analysis_complete": True,
    }
    return EngineResult("E9", ENGINE_NAMES["E9"], final, evidence_score, out, tuple(reasons))
