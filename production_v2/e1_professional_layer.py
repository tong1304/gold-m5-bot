"""E1 professional reconciliation layer.

Keeps the existing E1 analyzer as the primary market-state calculator and adds
an independent decision-quality layer: protected structure, multi-candle
acceptance, counter-evidence severity, thesis commitment and explicit
invalidation. It never creates a setup, entry, risk plan or trade decision.
"""
from __future__ import annotations

from typing import Any

from .e1_brain import analyze_e1 as _core_analyze_e1

BUFFER_ATR = 0.15
ACCEPTANCE_BARS = 3
MIN_ACCEPTANCE = 2


def _direction(bar: dict[str, Any]) -> str:
    o, c = float(bar["open"]), float(bar["close"])
    return "UP" if c > o else "DOWN" if c < o else "FLAT"


def _close_acceptance(bars: list[dict[str, Any]], level: float, direction: str, buffer: float) -> dict[str, Any]:
    sample = bars[-ACCEPTANCE_BARS:]
    if direction not in {"UP", "DOWN"} or not sample:
        return {"confirmed": False, "count": 0, "required": MIN_ACCEPTANCE, "bars": len(sample)}
    count = sum(
        float(b["close"]) > level + buffer if direction == "UP" else float(b["close"]) < level - buffer
        for b in sample
    )
    return {"confirmed": count >= MIN_ACCEPTANCE, "count": count, "required": MIN_ACCEPTANCE, "bars": len(sample)}


def _protected_structure(core: dict[str, Any], bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    pr = core.get("professional_reasoning") or {}
    evidence = pr.get("independent_evidence") or {}
    structure = evidence.get("structure") or {}
    high = structure.get("recent_swing_high")
    low = structure.get("recent_swing_low")
    if high is None:
        high = core.get("professional_reasoning", {}).get("recent_swing_high")
    if low is None:
        low = core.get("professional_reasoning", {}).get("recent_swing_low")
    if high is None:
        high = max(float(b["high"]) for b in bars[-20:])
    if low is None:
        low = min(float(b["low"]) for b in bars[-20:])

    buffer = max(BUFFER_ATR * atr, 1e-12)
    return {
        "bullish_protected_low": float(low),
        "bearish_protected_high": float(high),
        "buffer_atr": BUFFER_ATR,
        "buffer": buffer,
        "bullish_break_acceptance": _close_acceptance(bars, float(low), "DOWN", buffer),
        "bearish_break_acceptance": _close_acceptance(bars, float(high), "UP", buffer),
    }


def _reconcile(core: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    professional = dict(core.get("professional_reasoning") or {})
    evidence = dict(professional.get("independent_evidence") or {})
    volatility = evidence.get("volatility") or {}
    atr = float(volatility.get("atr14") or 0.0)
    if atr <= 0 and len(bars) >= 2:
        atr = sum(float(b["high"]) - float(b["low"]) for b in bars[-14:]) / min(14, len(bars[-14:]))

    protected = _protected_structure(core, bars, atr)
    state = str(core.get("market_state") or "UNCLEAR")
    direction = str(professional.get("direction") or core.get("directional_pressure") or "NEUTRAL")
    if direction == "BULLISH":
        direction = "UP"
    if direction == "BEARISH":
        direction = "DOWN"

    # A counter move on one closed candle is noise until it persists or breaks
    # the protected structure with multi-candle acceptance.
    last3 = bars[-3:]
    candle_dirs = [_direction(b) for b in last3]
    counter_candles = 0
    if direction in {"UP", "DOWN"}:
        opposite = "DOWN" if direction == "UP" else "UP"
        counter_candles = sum(x == opposite for x in candle_dirs)

    invalidation = dict(professional.get("invalidation") or {})
    invalidation.setdefault("conditions", [])
    if direction == "UP":
        invalidation["protected_level"] = protected["bullish_protected_low"]
        invalidation["acceptance_required"] = "2_OF_LAST_3_CLOSED_CANDLES_BELOW_PROTECTED_LOW"
    elif direction == "DOWN":
        invalidation["protected_level"] = protected["bearish_protected_high"]
        invalidation["acceptance_required"] = "2_OF_LAST_3_CLOSED_CANDLES_ABOVE_PROTECTED_HIGH"

    acceptance = protected["bullish_break_acceptance"] if direction == "UP" else protected["bearish_break_acceptance"] if direction == "DOWN" else {"confirmed": False, "count": 0, "required": MIN_ACCEPTANCE, "bars": len(last3)}

    counter = list(professional.get("counter_evidence") or [])
    severity = "NONE"
    if counter_candles == 1:
        if "SINGLE_COUNTER_CANDLE" not in counter:
            counter.append("SINGLE_COUNTER_CANDLE")
        severity = "LOW"
    elif counter_candles >= 2:
        if "PERSISTENT_COUNTER_PRESSURE" not in counter:
            counter.append("PERSISTENT_COUNTER_PRESSURE")
        severity = "HIGH"

    transition = bool(professional.get("transition_confirmed"))
    if transition and not acceptance["confirmed"]:
        # Do not call a one-sided repricing event a committed regime transition.
        transition = False
        counter.append("TRANSITION_NOT_ACCEPTED_BY_CLOSED_CANDLES")

    stability = dict(professional.get("state_stability") or {})
    stability_score = float(stability.get("score") or 0.0)
    if severity == "LOW":
        stability_score *= 0.95
    elif severity == "HIGH":
        stability_score *= 0.70
    if transition:
        stability_score *= 0.65
    stability_score = max(0.0, min(1.0, stability_score))
    stability["score"] = round(stability_score, 3)
    stability["status"] = "STABLE" if stability_score >= .70 and not transition else "WATCH" if stability_score >= .45 else "UNSTABLE"

    support = float((professional.get("confidence_model") or {}).get("support") or 0.0)
    counter_score = min(1.0, len([x for x in counter if x != "NO_MATERIAL_COUNTER_EVIDENCE"]) / 6.0)
    confidence = max(0.0, min(.99, .55 * support + .25 * stability_score + .20 * float(professional.get("trend_score") or 0.0) - .20 * counter_score))
    if state == "UNCLEAR":
        confidence = min(confidence, .65)

    thesis = dict(professional.get("primary_thesis") or {})
    thesis["counter_evidence"] = list(dict.fromkeys(counter))
    thesis["counter_severity"] = severity
    thesis["closed_candle_acceptance"] = acceptance
    thesis["status"] = "CONFIRMED" if state in {"TREND_UP", "TREND_DOWN"} and stability["status"] == "STABLE" else "DEVELOPING" if direction in {"UP", "DOWN"} else "UNRESOLVED"

    professional["primary_thesis"] = thesis
    professional["counter_evidence"] = list(dict.fromkeys(counter))
    professional["counter_evidence_severity"] = severity
    professional["state_stability"] = stability
    professional["confidence"] = round(confidence, 3)
    professional["protected_structure"] = protected
    professional["closed_candle_acceptance"] = acceptance
    professional["transition_confirmed"] = transition
    professional["transition_rule"] = "REQUIRES_INDEPENDENT_EVIDENCE_PLUS_2_OF_3_CLOSED_CANDLE_ACCEPTANCE"
    professional["decision_boundary"] = "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION"

    trace = list(core.get("reasoning_trace") or [])
    trace.extend([
        f"PROTECTED_STRUCTURE -> low={protected['bullish_protected_low']:.6f} high={protected['bearish_protected_high']:.6f}",
        f"CLOSED_CANDLE_ACCEPTANCE -> {acceptance}",
        f"COUNTER_EVIDENCE -> severity={severity} count={len(counter)}",
        f"THESIS -> {thesis.get('direction')} status={thesis.get('status')}",
        f"STABILITY -> {stability['status']} score={stability['score']:.3f}",
        f"CONFIDENCE -> {confidence:.3f}",
    ])

    output = dict(core)
    output["confidence"] = round(confidence, 3)
    output["conflicts"] = list(dict.fromkeys(list(core.get("conflicts") or []) + [x for x in counter if x not in {"NO_MATERIAL_COUNTER_EVIDENCE"}]))
    output["reasons"] = list(dict.fromkeys(list(core.get("reasons") or []) + (["COUNTER_EVIDENCE_PRESENT"] if counter else [])))
    output["reasoning_trace"] = trace
    output["professional_reasoning"] = professional
    output["e1_contract_version"] = "PROFESSIONAL_RECONCILED_V2"
    output["e1_trade_authority"] = False
    return output


def analyze_e1_professional(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Run core E1 then reconcile it into a professional market-state thesis."""
    clean = [b for b in (bars or []) if isinstance(b, dict)]
    core = _core_analyze_e1(clean)
    if core.get("analysis_status") == "INCOMPLETE" or len(clean) < 60:
        return core
    return _reconcile(core, clean)
