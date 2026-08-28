"""E1 Professional State Machine v4.

Reconciles the core E1 market-state thesis with deterministic historical
state, persistence, counter-pressure and closed-candle acceptance.
E1 remains market-state only and has no trade authority.
"""
from __future__ import annotations

from typing import Any

from .e1_brain import analyze_e1 as _core_analyze_e1

MIN_BARS = 60
STATE_WINDOW = 12
ACCEPTANCE_BARS = 3
MIN_ACCEPTANCE = 2
PERSISTENCE_MIN = 0.50

TRANSITION_LEVELS = ("NONE", "DETECTED", "WATCH", "VALIDATED", "COMMITTED")


def _clean(bars: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [b for b in (bars or []) if isinstance(b, dict)]


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    sample = bars[-n:]
    if not sample:
        return 0.0
    trs: list[float] = []
    prev = None
    for b in sample:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return sum(trs) / len(trs)


def _close_direction(b: dict[str, Any]) -> str:
    o, c = float(b["open"]), float(b["close"])
    return "UP" if c > o else "DOWN" if c < o else "FLAT"


def _persistence(bars: list[dict[str, Any]], direction: str) -> dict[str, float]:
    if direction not in {"UP", "DOWN"}:
        return {"bars_3": 0.0, "bars_5": 0.0, "bars_10": 0.0, "score": 0.0}
    values: dict[int, float] = {}
    for n in (3, 5, 10):
        sample = bars[-(n + 1):]
        if len(sample) < n + 1:
            values[n] = 0.0
            continue
        moves = [1.0 if (_close_direction(sample[i]) == direction) else 0.0 for i in range(1, len(sample))]
        values[n] = sum(moves) / n
    return {"bars_3": round(values[3], 3), "bars_5": round(values[5], 3), "bars_10": round(values[10], 3), "score": round((values[5] + values[10]) / 2.0, 3)}


def _acceptance(bars: list[dict[str, Any]], level: float | None, direction: str, atr: float) -> dict[str, Any]:
    sample = bars[-ACCEPTANCE_BARS:]
    if level is None or direction not in {"UP", "DOWN"}:
        return {"confirmed": False, "count": 0, "required": MIN_ACCEPTANCE, "bars": len(sample), "direction": direction}
    buffer = max(0.15 * atr, 1e-12)
    count = 0
    for b in sample:
        close = float(b["close"])
        if direction == "UP" and close > level + buffer:
            count += 1
        elif direction == "DOWN" and close < level - buffer:
            count += 1
    return {"confirmed": count >= MIN_ACCEPTANCE, "count": count, "required": MIN_ACCEPTANCE, "bars": len(sample), "level": level, "buffer_atr": 0.15, "direction": direction}


def _state_conflict(previous: str, current: str, previous_pressure: str, current_direction: str) -> bool:
    if previous in {"UNKNOWN", "UNCLEAR"}:
        return False
    if current == "TRANSITION":
        return True
    return previous in {"TREND_UP", "TREND_DOWN"} and current in {"TREND_UP", "TREND_DOWN"} and previous != current


def analyze_e1_professional_v4(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    clean = _clean(bars)
    core = _core_analyze_e1(clean)
    if core.get("analysis_status") == "INCOMPLETE" or len(clean) < MIN_BARS:
        return core

    current_state = str(core.get("market_state") or "UNCLEAR")
    current_pressure_raw = str(core.get("directional_pressure") or "NEUTRAL")
    current_direction = "UP" if current_pressure_raw in {"UP", "BULLISH"} else "DOWN" if current_pressure_raw in {"DOWN", "BEARISH"} else "NEUTRAL"

    prior = {"market_state": "UNKNOWN", "directional_pressure": "NEUTRAL"}
    if len(clean) >= MIN_BARS + STATE_WINDOW:
        prior_raw = _core_analyze_e1(clean[:-STATE_WINDOW])
        if prior_raw.get("analysis_status") != "INCOMPLETE":
            prior = prior_raw
    previous_state = str(prior.get("market_state") or "UNKNOWN")
    previous_pressure_raw = str(prior.get("directional_pressure") or "NEUTRAL")
    previous_direction = "UP" if previous_pressure_raw in {"UP", "BULLISH"} else "DOWN" if previous_pressure_raw in {"DOWN", "BEARISH"} else "NEUTRAL"

    pr = dict(core.get("professional_reasoning") or {})
    independent = dict(pr.get("independent_evidence") or {})
    structure = independent.get("structure") if isinstance(independent.get("structure"), dict) else {}
    atr = _atr(clean)
    protected_high = structure.get("recent_swing_high")
    protected_low = structure.get("recent_swing_low")
    if protected_high is None:
        protected_high = max(float(b["high"]) for b in clean[-20:])
    if protected_low is None:
        protected_low = min(float(b["low"]) for b in clean[-20:])

    persistence = _persistence(clean, current_direction)
    state_conflict = _state_conflict(previous_state, current_state, previous_direction, current_direction)
    pressure_flip = previous_direction in {"UP", "DOWN"} and current_direction in {"UP", "DOWN"} and previous_direction != current_direction

    transition_evidence: list[str] = []
    if current_state == "TRANSITION":
        transition_evidence.append("CORE_TRANSITION_SIGNAL")
    if pressure_flip:
        transition_evidence.append("DIRECTIONAL_PRESSURE_FLIP")
    if state_conflict:
        transition_evidence.append("PRIOR_CURRENT_STATE_CONFLICT")

    # A transition must be proved against the protected level of the prior thesis,
    # not merely against the current rolling swing. This prevents self-referential
    # acceptance tests during a fast repricing move.
    prior_direction = previous_direction if previous_direction in {"UP", "DOWN"} else current_direction
    invalidation_direction = "DOWN" if prior_direction == "UP" else "UP" if prior_direction == "DOWN" else "NONE"
    invalidation_level = protected_low if prior_direction == "UP" else protected_high if prior_direction == "DOWN" else None
    acceptance = _acceptance(clean, invalidation_level, invalidation_direction, atr)

    candidate = bool(state_conflict or pressure_flip or current_state == "TRANSITION")
    detected = candidate
    validated = bool(candidate and acceptance["confirmed"] and persistence["score"] >= PERSISTENCE_MIN)
    committed = bool(validated and current_direction in {"UP", "DOWN"} and prior_direction != current_direction)

    if committed:
        transition_status = "COMMITTED"
    elif validated:
        transition_status = "VALIDATED"
    elif candidate and (acceptance["confirmed"] or persistence["score"] >= PERSISTENCE_MIN):
        transition_status = "WATCH"
    elif detected:
        transition_status = "DETECTED"
    else:
        transition_status = "NONE"

    counter_candles = sum(1 for b in clean[-ACCEPTANCE_BARS:] if _close_direction(b) == invalidation_direction)
    if counter_candles >= 2:
        counter_severity = "HIGH"
    elif counter_candles == 1:
        counter_severity = "LOW"
    else:
        counter_severity = "NONE"

    base_stability = float((pr.get("state_stability") or {}).get("score", 0.0) or 0.0)
    stability = max(base_stability, persistence["score"])
    if transition_status == "DETECTED":
        stability *= 0.85
    elif transition_status == "WATCH":
        stability *= 0.70
    elif transition_status == "VALIDATED":
        stability *= 0.50
    elif transition_status == "COMMITTED":
        stability = min(stability * 0.35, 0.35)
    if counter_severity == "LOW":
        stability *= 0.95
    elif counter_severity == "HIGH":
        stability *= 0.75
    stability = round(max(0.0, min(1.0, stability)), 3)
    stability_status = "STABLE" if stability >= 0.70 and transition_status == "NONE" else "WATCH" if stability >= 0.45 else "UNSTABLE"

    support = float((pr.get("confidence_model") or {}).get("support", core.get("confidence", 0.0)) or 0.0)
    counter_score = min(1.0, counter_candles / 3.0)
    confidence = 0.50 * support + 0.25 * stability + 0.15 * persistence["score"] + 0.10 * float(structure.get("quality", 0.0) or 0.0) - 0.15 * counter_score
    if transition_status == "WATCH":
        confidence = min(confidence, 0.68)
    elif transition_status == "VALIDATED":
        confidence = min(confidence, 0.60)
    elif transition_status == "COMMITTED":
        confidence = min(confidence, 0.55)
    confidence = round(max(0.0, min(0.99, confidence)), 3)

    if transition_status == "COMMITTED":
        thesis_status = "TRANSITION_COMMITTED"
    elif transition_status == "VALIDATED":
        thesis_status = "TRANSITION_VALIDATED"
    elif transition_status in {"WATCH", "DETECTED"}:
        thesis_status = "UNDER_TRANSITION"
    else:
        thesis_status = str((pr.get("primary_thesis") or {}).get("status") or "UNRESOLVED")

    counter = ["PERSISTENT_COUNTER_PRESSURE"] if counter_severity == "HIGH" else ["SINGLE_COUNTER_CANDLE"] if counter_severity == "LOW" else []
    invalidation = {
        "prior_thesis_direction": prior_direction,
        "protected_level": invalidation_level,
        "acceptance": acceptance,
        "conditions": [
            "2_OF_LAST_3_CLOSED_CANDLES_BEYOND_PROTECTED_LEVEL",
            "PERSISTENCE_SCORE_AT_LEAST_0.50",
            "NEW_DIRECTIONAL_STATE_CONFIRMED",
        ],
        "status": "TRIGGERED" if validated else "WATCHING" if candidate else "VALID",
    }

    pr.update({
        "state_machine": {
            "version": "V4",
            "previous_regime": previous_state,
            "previous_direction": previous_direction,
            "current_regime": current_state,
            "current_direction": current_direction,
            "transition_candidate": candidate,
            "transition_detected": detected,
            "transition_status": transition_status,
            "transition_validated": validated,
            "transition_committed": committed,
            "levels": list(TRANSITION_LEVELS),
            "rule": "DETECTED -> WATCH -> VALIDATED -> COMMITTED; validation requires 2/3 closed-candle acceptance + persistence >= 0.50",
        },
        "primary_thesis": {
            "direction": current_direction,
            "status": thesis_status,
            "supporting_evidence": list((pr.get("primary_thesis") or {}).get("supporting_evidence", [])) if isinstance(pr.get("primary_thesis"), dict) else [],
            "counter_evidence": counter,
            "counter_severity": counter_severity,
        },
        "counter_evidence": counter,
        "counter_evidence_severity": counter_severity,
        "persistence": persistence,
        "protected_structure": {
            "prior_thesis_direction": prior_direction,
            "protected_high": protected_high,
            "protected_low": protected_low,
            "buffer_atr": 0.15,
        },
        "closed_candle_acceptance": acceptance,
        "state_stability": {"status": stability_status, "score": stability},
        "invalidation": invalidation,
        "confidence_model": {
            "support": round(support, 3),
            "counter_evidence": round(counter_score, 3),
            "structure": round(float(pr.get("structure_alignment", 0.0) or 0.0), 3),
            "persistence": persistence["score"],
            "stability": stability,
        },
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
    })

    trace = list(core.get("reasoning_trace") or [])
    trace.extend([
        f"STATE_MEMORY_V4 -> previous={previous_state}/{previous_direction} current={current_state}/{current_direction}",
        f"TRANSITION_V4 -> detected={detected} status={transition_status} validated={validated} committed={committed}",
        f"ACCEPTANCE_V4 -> {acceptance}",
        f"PERSISTENCE_V4 -> {persistence}",
        f"STABILITY_V4 -> {stability_status}:{stability:.3f}",
        f"THESIS_V4 -> {thesis_status} counter={counter_severity}",
    ])

    output = dict(core)
    output.update({
        "confidence": confidence,
        "reasoning_trace": trace,
        "professional_reasoning": pr,
        "e1_contract_version": "PROFESSIONAL_STATE_MACHINE_V4",
        "e1_trade_authority": False,
        "trade_decision_authority": False,
        "transition": "PRESENT" if candidate else "ABSENT",
        "transition_status": transition_status,
        "transition_validated": validated,
        "transition_committed": committed,
        "conflicts": list(dict.fromkeys(list(core.get("conflicts") or []) + ([f"REGIME_TRANSITION_{transition_status}"] if transition_status != "NONE" else []))),
        "reasons": list(dict.fromkeys(list(core.get("reasons") or []) + ([f"REGIME_TRANSITION_{transition_status}"] if transition_status != "NONE" else []))),
    })
    return output
