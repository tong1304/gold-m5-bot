from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult
from .e9_learning import build_advisory
from .engines import ENGINE_NAMES, run_engine as _engine_analyzer

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

EVIDENCE_WEIGHTS = {"E1": 1.00, "E2": 1.00, "E3": 1.20, "E4": 1.15, "E5": 1.10, "E6": 1.20, "E7": 1.30, "E8": 1.25}


def run_professional_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    raw = _engine_analyzer(engine_id, dict(context))
    output = dict(raw.output)
    output.update({
        "analysis_status": "COMPLETE",
        "analysis_complete": True,
        "specialist_question": SPECIALIST_QUESTIONS.get(engine_id, "Analyze the assigned market dimension."),
        "trade_decision_authority": False,
        "specialist_gate": "NONE",
        "gate": None,
        "input_mode": "SHARED_MARKET_SNAPSHOT",
        "upstream_engine_dependency": None,
        "reasoning_role": "SPECIALIST_EVIDENCE",
        "analysis_reason_codes": list(raw.reason_codes),
    })
    return EngineResult(raw.engine_id, raw.name, True, raw.score, output, raw.reason_codes)


def _text(e: EngineResult | None) -> str:
    return str(e.output if e else "").upper()


def _has(blob: str, *terms: str) -> bool:
    return any(term in blob for term in terms)


def _direction(evidence: dict[str, EngineResult]) -> str:
    votes = {"BUY": 0.0, "SELL": 0.0}
    for eid, e in evidence.items():
        b = _text(e)
        w = EVIDENCE_WEIGHTS.get(eid, 1.0)
        if _has(b, "BUY", "BULLISH", "TREND_UP", "LONG", "UP") and not _has(b, "BEARISH", "TREND_DOWN"):
            votes["BUY"] += w
        if _has(b, "SELL", "BEARISH", "TREND_DOWN", "SHORT", "DOWN") and not _has(b, "BULLISH", "TREND_UP"):
            votes["SELL"] += w
    if votes["BUY"] == votes["SELL"]:
        return "NEUTRAL"
    return "BUY" if votes["BUY"] > votes["SELL"] else "SELL"


def _weighted_alignment(upstream: list[EngineResult]) -> float:
    vals = []
    weights = []
    for e in upstream:
        w = EVIDENCE_WEIGHTS.get(e.engine_id, 1.0)
        vals.append(max(0.0, min(100.0, float(e.score))) * w)
        weights.append(w)
    return round(sum(vals) / sum(weights), 2) if weights else 0.0


def _professional_dimensions(by: dict[str, EngineResult]) -> dict[str, Any]:
    b = {k: _text(v) for k, v in by.items()}
    return {
        "market_state": {"engine": "E1", "evidence": b.get("E1", "")[:600]},
        "opportunity": {"engine": "E2", "evidence": b.get("E2", "")[:600]},
        "structure": {"engine": "E3", "evidence": b.get("E3", "")[:600]},
        "liquidity": {"engine": "E4", "evidence": b.get("E4", "")[:600]},
        "location": {"engine": "E5", "evidence": b.get("E5", "")[:600]},
        "setup": {"engine": "E6", "evidence": b.get("E6", "")[:600]},
        "confirmation": {"engine": "E7", "evidence": b.get("E7", "")[:600]},
        "economics": {"engine": "E8", "evidence": b.get("E8", "")[:600]},
    }


def run_professional_e9(
    context: dict[str, Any],
    upstream: list[EngineResult],
    historical_calibration: dict[str, Any] | None = None,
) -> EngineResult:
    """Professional E9: assess evidence, confluence, conflict, thesis and economics.

    Historical calibration is advisory only. It can inform the analyst, but it
    can never override E9, change thresholds, or enable live orders.
    """
    by = {e.engine_id: e for e in upstream}
    blobs = {k: _text(v) for k, v in by.items()}
    alignment = _weighted_alignment(upstream)
    direction = _direction(by)

    setup_mature = _has(blobs.get("E6", ""), "MATURE", "FORMED", "VALID_SETUP", "SETUP_QUALITY", "CONTINUATION_SETUP", "REVERSAL_SETUP")
    confirmation = _has(blobs.get("E7", ""), "CONFIRMED", "CONFIRMATION_PASS", "TRIGGER_OBSERVED", "FOLLOW_THROUGH")
    economics = _has(blobs.get("E8", ""), "ATTRACTIVE", "RISK_GATE_READY", "RR_OK", "POSITIVE_EXPECTANCY")
    good_location = _has(blobs.get("E5", ""), "ADVANTAGEOUS", "FAVORABLE", "DISCOUNT", "PREMIUM", "GOOD_LOCATION")
    structural_support = _has(blobs.get("E3", ""), "BULLISH", "BEARISH", "BREAK_OF_STRUCTURE", "BOS", "STRUCTURE")
    liquidity_event = _has(blobs.get("E4", ""), "SWEEP", "RECLAIM", "REJECTION", "LIQUIDITY")

    buy_support = sum(EVIDENCE_WEIGHTS.get(k, 1.0) for k, b in blobs.items() if _has(b, "BUY", "BULLISH", "TREND_UP", "LONG"))
    sell_support = sum(EVIDENCE_WEIGHTS.get(k, 1.0) for k, b in blobs.items() if _has(b, "SELL", "BEARISH", "TREND_DOWN", "SHORT"))
    conflict = abs(buy_support - sell_support) < 1.0 and direction != "NEUTRAL"
    if _has(blobs.get("E1", ""), "TREND_UP") and _has(blobs.get("E3", ""), "TREND_DOWN", "BEARISH"):
        conflict = True
    if _has(blobs.get("E1", ""), "TREND_DOWN") and _has(blobs.get("E3", ""), "TREND_UP", "BULLISH"):
        conflict = True

    reasons = []
    if direction == "NEUTRAL": reasons.append("DIRECTIONAL_THESIS_UNRESOLVED")
    if not setup_mature: reasons.append("SETUP_THESIS_NOT_MATURE")
    if not confirmation: reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not economics: reasons.append("TRADE_ECONOMICS_NOT_READY")
    if not good_location: reasons.append("LOCATION_QUALITY_NOT_ESTABLISHED")
    if conflict: reasons.append("DIRECTIONAL_EVIDENCE_CONFLICT")

    confluence_count = sum((structural_support, liquidity_event, good_location, setup_mature, confirmation, economics))
    thesis_quality = round(min(100.0, alignment + confluence_count * 2.5 - (12.0 if conflict else 0.0)), 2)
    final = direction in {"BUY", "SELL"} and setup_mature and confirmation and economics and thesis_quality >= 70.0 and not conflict
    decision = direction if final else "NO_TRADE"

    calibration = historical_calibration or {}
    advisory = build_advisory(direction, calibration) if calibration else None
    primary = f"{direction} thesis" if direction in {"BUY", "SELL"} else "No directional thesis"
    alternative = "Opposite-direction scenario if structure/confirmation fails"
    invalidation = "Use E8 invalidation evidence; if absent, thesis is not execution-ready"

    out = {
        "decision": decision,
        "decision_authority": "E9",
        "trade_decision_authority": True,
        "pipeline": "PARALLEL:E1|E2|E3|E4|E5|E6|E7|E8 -> E9",
        "architecture": "PROFESSIONAL_EVIDENCE_SYNTHESIS",
        "analysis_complete": True,
        "evidence_alignment": alignment,
        "thesis_quality": thesis_quality,
        "direction": direction,
        "directional_evidence": {"buy": round(buy_support, 2), "sell": round(sell_support, 2)},
        "confluence": {"count": confluence_count, "structure": structural_support, "liquidity": liquidity_event, "location": good_location, "setup": setup_mature, "confirmation": confirmation, "economics": economics},
        "conflict_analysis": {"detected": conflict, "status": "CONFLICT" if conflict else "ALIGNED"},
        "thesis": {"primary": primary, "alternative": alternative, "invalidation": invalidation},
        "professional_dimensions": _professional_dimensions(by),
        "historical_calibration": advisory,
        "learning_policy": "ADVISORY_ONLY_NO_OVERRIDE",
        "decision_reasons": reasons,
        "evidence_conflicts": [r for r in reasons if "CONFLICT" in r],
        "all_evidence_received": sorted(by),
        "upstream_gates_ignored": True,
        "gate_semantics": "E9_MASTER_ONLY",
        "professional_decision": "APPROVE_TRADE" if final else "NO_TRADE",
        "learning_target": "REPLAY_OUTCOME_REQUIRED",
    }
    return EngineResult("E9", ENGINE_NAMES.get("E9", "Master Decision Brain"), final, thesis_quality, out, tuple(reasons))
