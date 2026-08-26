from __future__ import annotations

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

# These are interpretation weights, not vote weights. They describe how much
# each specialist contributes to thesis quality. E9 never counts BUY/SELL
# strings as votes.
EVIDENCE_WEIGHTS = {
    "E1": 1.00,
    "E2": 1.00,
    "E3": 1.20,
    "E4": 1.15,
    "E5": 1.10,
    "E6": 1.20,
    "E7": 1.30,
    "E8": 1.25,
}

DIRECTIONS = {"BUY", "SELL"}


def run_professional_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    raw = _engine_analyzer(engine_id, dict(context))
    output = dict(raw.output)
    output.update(
        {
            "analysis_status": "COMPLETE",
            "analysis_complete": True,
            "specialist_question": SPECIALIST_QUESTIONS.get(
                engine_id, "Analyze the assigned market dimension."
            ),
            "trade_decision_authority": False,
            "specialist_gate": "NONE",
            "gate": None,
            "input_mode": "SHARED_MARKET_AND_PEER_EVIDENCE",
            "upstream_engine_dependency": None,
            "reasoning_role": "SPECIALIST_EVIDENCE",
            "analysis_reason_codes": list(raw.reason_codes),
        }
    )
    return EngineResult(raw.engine_id, raw.name, None, raw.score, output, raw.reason_codes)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _text(value: Any) -> str:
    return str(value).upper()


def _has(blob: str, *terms: str) -> bool:
    return any(term in blob for term in terms)


def _nested_values(value: Any) -> list[Any]:
    """Flatten dictionaries/lists for conservative evidence inspection."""
    if isinstance(value, dict):
        values: list[Any] = []
        for item in value.values():
            values.extend(_nested_values(item))
        return values
    if isinstance(value, (list, tuple, set)):
        values: list[Any] = []
        for item in value:
            values.extend(_nested_values(item))
        return values
    return [value]


def _blob(e: EngineResult | None) -> str:
    if e is None:
        return ""
    return _text(_nested_values(e.output))


def _structured_direction(e: EngineResult | None) -> str | None:
    if e is None:
        return None
    output = e.output or {}
    candidates = [
        output.get("direction"),
        output.get("bias"),
        output.get("orientation"),
        output.get("market_direction"),
    ]
    for candidate in candidates:
        value = _text(candidate).strip()
        if value in DIRECTIONS:
            return value
        if value in {"BULLISH", "UP", "LONG", "TREND_UP"}:
            return "BUY"
        if value in {"BEARISH", "DOWN", "SHORT", "TREND_DOWN"}:
            return "SELL"
    return None


def _directional_evidence(e: EngineResult | None) -> tuple[float, float]:
    """Return directional support without turning free-form text into votes.

    Structured direction is primary. Text is used only to identify an explicit
    specialist conclusion, and only when it contains an unambiguous directional
    token rather than a negated/conflicting phrase.
    """
    if e is None:
        return 0.0, 0.0
    weight = EVIDENCE_WEIGHTS.get(e.engine_id, 1.0)
    direction = _structured_direction(e)
    if direction == "BUY":
        return weight, 0.0
    if direction == "SELL":
        return 0.0, weight

    output = e.output or {}
    conclusion = _text(
        output.get("professional_reasoning", {}).get("conclusion")
        if isinstance(output.get("professional_reasoning"), dict)
        else ""
    )
    if not conclusion:
        return 0.0, 0.0
    buy = _has(conclusion, "BUY", "BULLISH", "TREND_UP", "LONG")
    sell = _has(conclusion, "SELL", "BEARISH", "TREND_DOWN", "SHORT")
    if buy and not sell:
        return weight * 0.75, 0.0
    if sell and not buy:
        return 0.0, weight * 0.75
    return 0.0, 0.0


def _direction(evidence: dict[str, EngineResult]) -> str:
    buy = sell = 0.0
    for result in evidence.values():
        b, s = _directional_evidence(result)
        buy += b
        sell += s
    if buy == sell:
        return "NEUTRAL"
    return "BUY" if buy > sell else "SELL"


def _weighted_alignment(upstream: list[EngineResult]) -> float:
    values: list[float] = []
    weights: list[float] = []
    for e in upstream:
        w = EVIDENCE_WEIGHTS.get(e.engine_id, 1.0)
        values.append(_clamp(e.score) * w)
        weights.append(w)
    return round(sum(values) / sum(weights), 2) if weights else 0.0


def _professional_dimensions(by: dict[str, EngineResult]) -> dict[str, Any]:
    return {
        key: {
            "engine": key,
            "evidence": _blob(by.get(key))[:1000],
            "score": round(float(by[key].score), 2) if key in by else None,
            "direction": _structured_direction(by.get(key)),
        }
        for key in SPECIALIST_QUESTIONS
    }


def _dimension_state(by: dict[str, EngineResult]) -> dict[str, Any]:
    blobs = {key: _blob(by.get(key)) for key in SPECIALIST_QUESTIONS}
    return {
        "market_context": bool(blobs["E1"] or blobs["E2"]),
        "structure_support": _has(blobs["E3"], "BOS", "BREAK_OF_STRUCTURE", "HIGHER_HIGH", "LOWER_LOW", "STRUCTURE") ,
        "liquidity_event": _has(blobs["E4"], "SWEEP", "RECLAIM", "REJECTION", "LIQUIDITY"),
        "location_quality": _has(blobs["E5"], "ADVANTAGEOUS", "FAVORABLE", "DISCOUNT", "PREMIUM", "GOOD_LOCATION"),
        "setup_mature": _has(blobs["E6"], "MATURE", "FORMED", "VALID_SETUP", "CONTINUATION_SETUP", "REVERSAL_SETUP"),
        "confirmation": _has(blobs["E7"], "CONFIRMED", "CONFIRMATION_PASS", "TRIGGER_OBSERVED", "FOLLOW_THROUGH"),
        "economics": _has(blobs["E8"], "ATTRACTIVE", "RISK_GATE_READY", "RR_OK", "POSITIVE_EXPECTANCY"),
    }


def _hard_invalidations(by: dict[str, EngineResult], direction: str) -> list[str]:
    """Only true invalidations can stop E9 before thesis judgement.

    Specialist diagnostic gates are deliberately ignored. We only act on
    explicit invalidation language or invalid execution geometry.
    """
    invalidations: list[str] = []
    for eid in ("E3", "E6", "E7", "E8"):
        e = by.get(eid)
        if e is None:
            continue
        blob = _blob(e)
        if _has(blob, "INVALIDATED", "HARD_INVALIDATION", "STRUCTURE_INVALIDATED", "SETUP_INVALIDATED"):
            invalidations.append(f"{eid}_THESIS_INVALIDATED")

    e8 = by.get("E8")
    if e8 is not None:
        blob = _blob(e8)
        if _has(blob, "INVALID_RISK", "INVALID_RISK_GEOMETRY", "NEGATIVE_RR", "RR_BELOW_MINIMUM"):
            invalidations.append("E8_RISK_GEOMETRY_INVALID")

    if direction == "NEUTRAL" and by:
        # Neutral is a lack of edge, not an invalidation. Kept out intentionally.
        pass
    return sorted(set(invalidations))


def _conflicts(by: dict[str, EngineResult]) -> list[str]:
    conflicts: list[str] = []
    e1, e3 = _structured_direction(by.get("E1")), _structured_direction(by.get("E3"))
    e6, e7 = _structured_direction(by.get("E6")), _structured_direction(by.get("E7"))
    if e1 and e3 and e1 != e3:
        conflicts.append("E1_E3_DIRECTION_CONFLICT")
    if e6 and e7 and e6 != e7:
        conflicts.append("E6_E7_DIRECTION_CONFLICT")
    return conflicts


def _thesis_score(
    by: dict[str, EngineResult],
    direction: str,
    dimensions: dict[str, Any],
    conflicts: list[str],
) -> float:
    if direction == "NEUTRAL":
        return 0.0

    # Start with quality of the evidence itself, then reward independent
    # dimensions that agree with the thesis. This is not a vote counter.
    evidence_quality = _weighted_alignment(list(by.values()))
    support = 0.0
    for key in ("structure_support", "liquidity_event", "location_quality", "setup_mature", "confirmation", "economics"):
        if dimensions[key]:
            support += 3.5
    penalty = min(24.0, len(conflicts) * 8.0)
    return round(_clamp(evidence_quality + support - penalty), 2)


def run_professional_e9(
    context: dict[str, Any],
    upstream: list[EngineResult],
    historical_calibration: dict[str, Any] | None = None,
) -> EngineResult:
    """E9 Master Decision Brain.

    E9 behaves as a professional discretionary decision layer:
    1. understand market context;
    2. form a directional thesis;
    3. test structure/liquidity/location/setup/confirmation;
    4. identify what invalidates the thesis;
    5. evaluate asymmetry and conflicts;
    6. decide BUY, SELL or NO_TRADE.

    E1-E8 are evidence providers only. Their diagnostic gates are never copied
    into E9. Historical calibration is advisory and cannot override judgement.
    """
    by = {e.engine_id: e for e in upstream}
    direction = _direction(by)
    dimensions = _dimension_state(by)
    conflicts = _conflicts(by)
    hard_invalidations = _hard_invalidations(by, direction)
    alignment = _weighted_alignment(upstream)
    thesis_quality = _thesis_score(by, direction, dimensions, conflicts)

    reasons: list[str] = []
    if not by:
        reasons.append("NO_UPSTREAM_EVIDENCE")
    if direction == "NEUTRAL":
        reasons.append("DIRECTIONAL_THESIS_UNRESOLVED")
    if not dimensions["setup_mature"]:
        reasons.append("SETUP_NOT_MATURE")
    if not dimensions["confirmation"]:
        reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not dimensions["economics"]:
        reasons.append("TRADE_ECONOMICS_NOT_READY")
    reasons.extend(conflicts)
    reasons.extend(hard_invalidations)

    # Professional decision rule: absence of a positive edge is NO_TRADE;
    # optional evidence weakens the thesis but does not become a hidden gate.
    # A trade still requires a mature setup, confirmation, economic readiness,
    # a coherent direction and enough thesis quality. True invalidations always
    # override those positive conditions.
    execution_ready = (
        direction in DIRECTIONS
        and dimensions["setup_mature"]
        and dimensions["confirmation"]
        and dimensions["economics"]
        and thesis_quality >= 70.0
        and not conflicts
        and not hard_invalidations
    )
    decision = direction if execution_ready else "NO_TRADE"

    calibration = historical_calibration or {}
    advisory = build_advisory(direction, calibration) if calibration else None
    primary = (
        f"{direction} continuation/reversal thesis supported by independent evidence"
        if direction in DIRECTIONS
        else "No sufficiently clear directional thesis"
    )
    alternative = (
        "Opposite-direction scenario becomes relevant only if structure or confirmation invalidates the primary thesis"
    )
    invalidation = (
        "; ".join(hard_invalidations)
        if hard_invalidations
        else "Primary thesis is invalid if the structural/setup/confirmation premise fails"
    )

    out = {
        "decision": decision,
        "decision_authority": "E9",
        "trade_decision_authority": True,
        "pipeline": "E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9",
        "architecture": "PROFESSIONAL_THESIS_REASONING",
        "analysis_complete": True,
        "evidence_alignment": alignment,
        "thesis_quality": thesis_quality,
        "direction": direction,
        "directional_evidence": {
            "buy": round(sum(_directional_evidence(e)[0] for e in by.values()), 2),
            "sell": round(sum(_directional_evidence(e)[1] for e in by.values()), 2),
        },
        "professional_reasoning": {
            "question": "Is there a clear, asymmetric, confirmed opportunity worth risking capital on now?",
            "primary_thesis": primary,
            "alternative_thesis": alternative,
            "invalidation": invalidation,
            "dimensions": dimensions,
            "conflicts": conflicts,
            "hard_invalidations": hard_invalidations,
            "execution_ready": execution_ready,
        },
        "confluence": {
            "count": sum(bool(v) for v in dimensions.values()),
            **dimensions,
        },
        "conflict_analysis": {
            "detected": bool(conflicts),
            "status": "CONFLICT" if conflicts else "ALIGNED",
            "items": conflicts,
        },
        "thesis": {
            "primary": primary,
            "alternative": alternative,
            "invalidation": invalidation,
        },
        "professional_dimensions": _professional_dimensions(by),
        "historical_calibration": advisory,
        "learning_policy": "ADVISORY_ONLY_NO_OVERRIDE",
        "decision_reasons": reasons,
        "evidence_conflicts": conflicts,
        "hard_invalidations": hard_invalidations,
        "all_evidence_received": sorted(by),
        "upstream_gates_ignored": True,
        "gate_semantics": "E9_MASTER_ONLY",
        "professional_decision": "APPROVE_TRADE" if execution_ready else "NO_TRADE",
        "learning_target": "REPLAY_OUTCOME_REQUIRED",
    }
    return EngineResult(
        "E9",
        ENGINE_NAMES.get("E9", "Master Decision Brain"),
        execution_ready,
        thesis_quality,
        out,
        tuple(reasons),
    )
