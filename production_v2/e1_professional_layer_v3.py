"""E1 professional reconciliation v3.

Adds state-memory-style reconciliation without changing E1 ownership:
market-state only, closed candles only, no setup/entry/risk/trade decision.
"""
from __future__ import annotations

from typing import Any

from .e1_brain import analyze_e1 as _core_analyze_e1

ACCEPTANCE_BARS = 3
MIN_ACCEPTANCE = 2
STATE_WINDOW = 12


def _dir(bar: dict[str, Any]) -> str:
    o, c = float(bar["open"]), float(bar["close"])
    return "UP" if c > o else "DOWN" if c < o else "FLAT"


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    sample = bars[-n:]
    if not sample:
        return 0.0
    return sum(float(b["high"]) - float(b["low"]) for b in sample) / len(sample)


def _acceptance(bars: list[dict[str, Any]], level: float | None, direction: str, atr: float) -> dict[str, Any]:
    sample = bars[-ACCEPTANCE_BARS:]
    if level is None or direction not in {"UP", "DOWN"}:
        return {"confirmed": False, "count": 0, "required": MIN_ACCEPTANCE, "bars": len(sample)}
    buffer = max(0.15 * atr, 1e-12)
    count = sum(
        float(b["close"]) > level + buffer if direction == "UP" else float(b["close"]) < level - buffer
        for b in sample
    )
    return {"confirmed": count >= MIN_ACCEPTANCE, "count": count, "required": MIN_ACCEPTANCE, "bars": len(sample), "level": level}


def _direction_persistence(bars: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    if direction not in {"UP", "DOWN"}:
        return {"bars_3": 0.0, "bars_5": 0.0, "bars_10": 0.0, "score": 0.0}
    values = []
    for n in (3, 5, 10):
        sample = bars[-(n + 1):]
        if len(sample) < n + 1:
            values.append(0.0)
            continue
        matches = 0
        for i in range(1, len(sample)):
            d = _dir({"open": sample[i-1]["close"], "close": sample[i]["close"]})
            matches += d == direction
        values.append(matches / n)
    return {"bars_3": round(values[0], 3), "bars_5": round(values[1], 3), "bars_10": round(values[2], 3), "score": round(0.5 * values[1] + 0.5 * values[2], 3)}


def _recent_state(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if len(bars) < 60:
        return {"market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "confidence": 0.0}
    return _core_analyze_e1(bars)["market_state"], _core_analyze_e1(bars).get("directional_pressure", "NEUTRAL")


def analyze_e1_professional_v3(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    clean = [b for b in (bars or []) if isinstance(b, dict)]
    core = _core_analyze_e1(clean)
    if core.get("analysis_status") == "INCOMPLETE" or len(clean) < 60:
        return core

    current_state = str(core.get("market_state") or "UNCLEAR")
    current_pressure = str(core.get("directional_pressure") or "NEUTRAL")
    direction = "UP" if current_pressure in {"UP", "BULLISH"} else "DOWN" if current_pressure in {"DOWN", "BEARISH"} else "NEUTRAL"

    # Compare the current regime with a prior closed-candle context. This is
    # deterministic state memory derived from the supplied history, not hidden
    # mutable state, so replay/live evaluation remains reproducible.
    prior = {"market_state": "UNKNOWN", "directional_pressure": "NEUTRAL", "confidence": 0.0}
    if len(clean) >= 84:
        prior_raw = _core_analyze_e1(clean[:-STATE_WINDOW])
        if prior_raw.get("analysis_status") != "INCOMPLETE":
            prior = prior_raw
    previous_state = str(prior.get("market_state") or "UNKNOWN")
    previous_pressure = str(prior.get("directional_pressure") or "NEUTRAL")

    persistence = _direction_persistence(clean, direction)
    candle_dirs = [_dir(b) for b in clean[-ACCEPTANCE_BARS:]]
    opposite = "DOWN" if direction == "UP" else "UP" if direction == "DOWN" else "FLAT"
    counter_count = candle_dirs.count(opposite)

    pr = dict(core.get("professional_reasoning") or {})
    evidence = dict(pr.get("independent_evidence") or {})
    structure = evidence.get("structure") if isinstance(evidence.get("structure"), dict) else {}
    high = structure.get("recent_swing_high")
    low = structure.get("recent_swing_low")
    if high is None:
        high = max(float(b["high"]) for b in clean[-20:])
    if low is None:
        low = min(float(b["low"]) for b in clean[-20:])
    atr = _atr(clean)

    protected = {
        "bullish_protected_low": float(low),
        "bearish_protected_high": float(high),
        "buffer_atr": 0.15,
    }
    acceptance = _acceptance(
        clean,
        protected["bullish_protected_low"] if direction == "UP" else protected["bearish_protected_high"] if direction == "DOWN" else None,
        "DOWN" if direction == "UP" else "UP" if direction == "DOWN" else "NONE",
        atr,
    )

    material_state_change = previous_state not in {"UNKNOWN", "UNCLEAR"} and current_state not in {"UNCLEAR", previous_state}
    transition_candidate = material_state_change or (previous_pressure in {"UP", "DOWN"} and direction in {"UP", "DOWN"} and previous_pressure != direction)
    transition_committed = bool(transition_candidate and counter_count >= MIN_ACCEPTANCE and acceptance["confirmed"] and persistence["score"] >= 0.50)
    if transition_committed:
        transition_status = "COMMITTED"
    elif transition_candidate:
        transition_status = "WATCH"
    else:
        transition_status = "NONE"

    severity = "NONE"
    if counter_count == 1:
        severity = "LOW"
    elif counter_count >= 2:
        severity = "HIGH"
    if transition_candidate and not transition_committed:
        severity = "HIGH" if counter_count >= 2 else "MEDIUM"

    stability_score = float(pr.get("state_stability", {}).get("score", 0.0) or 0.0)
    if direction in {"UP", "DOWN"}:
        stability_score = max(stability_score, persistence["score"])
    if severity == "LOW":
        stability_score *= 0.95
    elif severity in {"MEDIUM", "HIGH"}:
        stability_score *= 0.70
    if transition_status == "WATCH":
        stability_score *= 0.85
    if transition_status == "COMMITTED":
        stability_score = min(stability_score, 0.45)
    stability_score = round(max(0.0, min(1.0, stability_score)), 3)
    stability_status = "STABLE" if stability_score >= 0.70 and transition_status == "NONE" else "WATCH" if stability_score >= 0.45 else "UNSTABLE"

    support = float(pr.get("confidence_model", {}).get("support", core.get("confidence", 0.0)) or 0.0)
    confidence = max(0.0, min(0.99, 0.50 * support + 0.30 * stability_score + 0.20 * persistence["score"] - (0.08 if severity == "LOW" else 0.18 if severity == "MEDIUM" else 0.25 if severity == "HIGH" else 0.0)))
    if transition_status == "WATCH":
        confidence = min(confidence, 0.68)
    if current_state == "UNCLEAR":
        confidence = min(confidence, 0.55)
    confidence = round(confidence, 3)

    thesis_direction = direction
    thesis_status = "CONFIRMED" if current_state in {"TREND_UP", "TREND_DOWN"} and stability_status == "STABLE" else "DEVELOPING" if direction in {"UP", "DOWN"} else "UNRESOLVED"
    invalidation = {
        "conditions": [],
        "protected_level": protected["bullish_protected_low"] if direction == "UP" else protected["bearish_protected_high"] if direction == "DOWN" else None,
        "acceptance_required": "2_OF_LAST_3_CLOSED_CANDLES",
    }
    if direction == "UP":
        invalidation["conditions"] = ["persistent bearish pressure", "2_of_last_3_closed_candles_below_protected_low", "bullish_structure_loss"]
    elif direction == "DOWN":
        invalidation["conditions"] = ["persistent bullish pressure", "2_of_last_3_closed_candles_above_protected_high", "bearish_structure_loss"]
    else:
        invalidation["conditions"] = ["directional state becomes coherent and persistent"]

    pr.update({
        "primary_thesis": {
            "direction": thesis_direction,
            "status": thesis_status,
            "supporting_evidence": list(pr.get("primary_thesis", {}).get("supporting_evidence", [])) if isinstance(pr.get("primary_thesis"), dict) else [],
            "counter_evidence": ["SINGLE_COUNTER_CANDLE"] if severity == "LOW" else ["PERSISTENT_COUNTER_PRESSURE"] if severity == "HIGH" else [],
            "counter_severity": severity,
            "closed_candle_acceptance": acceptance,
        },
        "counter_evidence": ["SINGLE_COUNTER_CANDLE"] if severity == "LOW" else ["PERSISTENT_COUNTER_PRESSURE"] if severity == "HIGH" else [],
        "counter_evidence_severity": severity,
        "persistence": persistence,
        "state_stability": {"status": stability_status, "score": stability_score},
        "protected_structure": protected,
        "closed_candle_acceptance": acceptance,
        "invalidation": invalidation,
        "confidence_model": {"support": round(support, 3), "counter_evidence": round(min(1.0, counter_count / 3.0), 3), "structure": round(float(pr.get("structure_alignment", 0.0) or 0.0), 3), "persistence": persistence["score"], "stability": stability_score},
        "state_machine": {
            "previous_regime": previous_state,
            "previous_pressure": previous_pressure,
            "current_regime": current_state,
            "current_pressure": current_pressure,
            "transition_candidate": bool(transition_candidate),
            "transition_status": transition_status,
            "transition_committed": transition_committed,
            "acceptance_rule": "2_OF_LAST_3_CLOSED_CANDLES + PERSISTENCE >= 0.50",
        },
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
    })

    trace = list(core.get("reasoning_trace") or [])
    trace.extend([
        f"STATE_MEMORY -> previous={previous_state} current={current_state}",
        f"PERSISTENCE -> {persistence}",
        f"TRANSITION -> candidate={transition_candidate} status={transition_status} acceptance={acceptance}",
        f"STABILITY -> {stability_status} score={stability_score:.3f}",
        f"THESIS -> direction={thesis_direction} status={thesis_status} counter={severity}",
        f"INVALIDATION -> {invalidation['conditions']}",
        f"CONFIDENCE -> {confidence:.3f}",
    ])

    output = dict(core)
    output.update({
        "confidence": confidence,
        "reasoning_trace": trace,
        "professional_reasoning": pr,
        "e1_contract_version": "PROFESSIONAL_STATE_MACHINE_V3",
        "e1_trade_authority": False,
        "trade_decision_authority": False,
        "conflicts": list(dict.fromkeys(list(core.get("conflicts") or []) + (["REGIME_TRANSITION_WATCH"] if transition_status == "WATCH" else []))),
        "reasons": list(dict.fromkeys(list(core.get("reasons") or []) + (["REGIME_TRANSITION_WATCH"] if transition_status == "WATCH" else []))),
    })
    return output
