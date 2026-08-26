from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .engines import ENGINE_NAMES, ENGINE_WEIGHTS, EDGE_THRESHOLD, run_engine as _legacy_run_engine


# E1-E8 are specialist analysts, not trade-decision makers.
# Their gate means "analysis completed and evidence can be handed off",
# never "BUY/SELL approved". Only E9 has trade-decision authority.

_FATAL_REASONS = {
    "E1_DATA_INVALID",
    "E3_STRUCTURE_INVALIDATED",
    "E6_SETUP_INVALIDATED",
}


def _status_from_legacy(result: EngineResult) -> str:
    reasons = set(result.reason_codes)
    if reasons & _FATAL_REASONS:
        return "CONFLICT_OR_INVALID"
    if result.engine_id == "E7":
        confirmation = result.output.get("professional_reasoning", {}).get("confirmation")
        return "CONFIRMED" if confirmation == "CONFIRMATION_PASS" else "NOT_CONFIRMED"
    if result.engine_id == "E8":
        plan = result.output.get("trade_plan", {})
        return "ECONOMICS_READY" if plan.get("valid") else "ECONOMICS_UNAVAILABLE"
    if result.score >= 75:
        return "STRONG_EVIDENCE"
    if result.score >= 55:
        return "PARTIAL_EVIDENCE"
    return "WEAK_EVIDENCE"


def _professional_answer(engine_id: str, output: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    """Convert sub-engine evidence into one specialist conclusion.

    The specialist may describe bullish/bearish evidence, but it never emits
    BUY or SELL. Those words are reserved exclusively for E9.
    """
    r = dict(output.get("professional_reasoning") or {})
    prior_summary = {
        key: (value.get("professional_reasoning") if isinstance(value, dict) else None)
        for key, value in prior.items()
        if key.startswith("E") and key.endswith("_result")
    }
    r["inputs_from_previous_engines"] = list(prior_summary.keys())
    r["specialist_status"] = _status_from_legacy(EngineResult(engine_id, ENGINE_NAMES[engine_id], True, float(output.get("evidence_quality", 0)), output, tuple(output.get("professional_reason_codes", []))))

    conclusions = {
        "E1": "กำหนดสภาวะตลาดและ Market Bias เพื่อให้ระบบรู้ว่าตลาดกำลังอยู่ในสภาพใด",
        "E2": "เลือก Regime และ Playbook ที่เหมาะกับสภาวะจาก E1 โดยยังไม่ตัดสินการเข้าเทรด",
        "E3": "ตรวจว่า Market Structure สนับสนุน ขัดแย้ง หรือยังไม่ชัดเจนเมื่อเทียบกับบริบทจาก E1-E2",
        "E4": "ระบุ Liquidity ที่เกี่ยวข้องและตีความว่า Price Action ได้แสดง Sweep, Reclaim หรือ Rejection หรือยัง",
        "E5": "ประเมินว่าราคาปัจจุบันอยู่ใน Location ที่มีความได้เปรียบ มีพื้นที่ และไม่ไล่ราคาหรือไม่",
        "E6": "ระบุว่าเกิด Trade Setup ประเภทใด อยู่ในขั้นก่อตัวหรือพร้อม และอะไรคือ Invalidation",
        "E7": "พิสูจน์ว่า Setup จาก E6 เกิด Trigger และ Follow-through จริงหรือยัง โดยใช้แท่งที่ปิดแล้ว",
        "E8": "ประเมิน Entry/Invalidation/Target/RR และต้นทุนความเสี่ยงว่ามี Trade Economics ที่สมเหตุผลหรือไม่",
    }
    r["specialist_conclusion"] = conclusions.get(engine_id, "")
    return r


def run_professional_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    """Run the existing quantitative sub-engines, then reinterpret their result
    as a specialist answer. E1-E8 do not block the next specialist merely
    because their conclusion is weak or negative.
    """
    raw = _legacy_run_engine(engine_id, context)
    output = dict(raw.output)
    output["professional_reasoning"] = _professional_answer(engine_id, output, context)
    output["analysis_status"] = _status_from_legacy(raw)
    output["analysis_complete"] = True
    output["handoff_allowed"] = True
    output["trade_decision_authority"] = False
    output["analysis_reason_codes"] = list(raw.reason_codes)

    # Only true data/setup invalidation is a hard analysis failure. A weak
    # setup, missing sweep, missing trigger, or unfavorable economics is an
    # answer from that specialist, not a pipeline failure.
    fatal = bool(set(raw.reason_codes) & _FATAL_REASONS)
    if engine_id == "E8" and not output.get("trade_plan", {}).get("valid"):
        # E8 still completed its job: it concluded that economics cannot be
        # validated. E9 must see that evidence rather than treating E8 as
        # an execution-time exception.
        fatal = False

    output["specialist_gate"] = "ANALYSIS_FATAL" if fatal else "ANALYSIS_COMPLETE"
    return EngineResult(
        engine_id=raw.engine_id,
        name=raw.name,
        gate_passed=not fatal,
        score=raw.score,
        output=output,
        reason_codes=raw.reason_codes,
    )


def _weighted_evidence(upstream: list[EngineResult]) -> float:
    values = {e.engine_id: float(e.score) for e in upstream if e.engine_id in ENGINE_WEIGHTS}
    weight = sum(ENGINE_WEIGHTS[k] for k in values)
    if weight <= 0:
        return 0.0
    return round(sum(values[k] * ENGINE_WEIGHTS[k] for k in values) / weight, 2)


def run_professional_e9(context: dict[str, Any], upstream: list[EngineResult]) -> EngineResult:
    """Only E9 may convert accumulated evidence into BUY/SELL/NO_TRADE."""
    by_id = {e.engine_id: e for e in upstream}
    e1, e3, e5, e6, e7, e8 = (by_id.get(x) for x in ("E1", "E3", "E5", "E6", "E7", "E8"))
    plan = (e8.output.get("trade_plan", {}) if e8 else {})
    evidence_score = _weighted_evidence(upstream)

    r7 = e7.output.get("professional_reasoning", {}) if e7 else {}
    r6 = e6.output.get("professional_reasoning", {}) if e6 else {}
    confirmation = r7.get("confirmation")
    trigger_quality = r7.get("trigger_quality")
    follow_through = r7.get("follow_through")

    # E9 evaluates evidence; it does not blindly obey an upstream gate.
    critical_conflicts = [e.engine_id for e in upstream if e.engine_id in {"E1", "E3", "E6"} and not e.gate_passed]
    confirmation_ready = (
        confirmation == "CONFIRMATION_PASS"
        and trigger_quality == "QUALITY_PASS"
        and follow_through == "FOLLOW_THROUGH_OBSERVED"
    )
    economics_ready = bool(plan.get("valid")) and float(plan.get("rr_tp2", 0)) >= float(plan.get("min_rr", 1.5))
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
        "edge_score": evidence_score if final else 0.0,
        "edge_threshold": EDGE_THRESHOLD,
        "gate_passed": final,
        "professional_decision": "APPROVE_TRADE" if final else "NO_TRADE",
        "blocked_by": None,
        "decision_reasons": reasons,
        "specialist_conclusions": {
            e.engine_id: e.output.get("professional_reasoning", {}).get("specialist_conclusion", "")
            for e in upstream
        },
        "setup_thesis": r6,
        "analysis_complete": True,
    }
    return EngineResult("E9", ENGINE_NAMES["E9"], final, evidence_score, out, tuple(reasons))
