"""E1 V13 — professional market-state arbitration core.

E1 answers one question only: What is the market doing right now?
It never creates setup, entry, stop, target, RR, risk, or trade decisions.

V13 adds explicit state arbitration:
- data quality is a hard prerequisite
- structure and persistent long-horizon evidence establish the dominant basis
- counter-trend structure is classified explicitly instead of flipping the regime
- transition requires persistent structural repricing across independent evidence
- volatility is an overlay, never the primary directional authority
- uncertainty is preferred over forced directional classification
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
ARBITRATION_ORDER = [
    "DATA_QUALITY", "STRUCTURE", "LONG_HORIZON", "PERSISTENCE",
    "PRESSURE", "EMA_CONTEXT", "VOLATILITY", "COUNTER_EVIDENCE", "TRANSITION",
]
DIRECTIONS = {"UP", "DOWN"}


def _num(x: Any) -> float | None:
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _clean(bars: list[dict[str, Any]] | None):
    valid, invalid = [], 0
    for raw in bars or []:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        values = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            invalid += 1
            continue
        o, h, l, c = values["open"], values["high"], values["low"], values["close"]
        if h < l or h < max(o, c) or l > min(o, c):
            invalid += 1
            continue
        valid.append({**raw, **values})
    return valid, invalid


def _ema(xs: list[float], n: int) -> list[float]:
    if not xs:
        return []
    alpha = 2.0 / (n + 1.0)
    current = xs[0]
    out = [current]
    for value in xs[1:]:
        current = alpha * value + (1.0 - alpha) * current
        out.append(current)
    return out


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    sample = bars[-n:]
    trs, previous = [], None
    for bar in sample:
        h, l, c = bar["high"], bar["low"], bar["close"]
        trs.append(h - l if previous is None else max(h - l, abs(h - previous), abs(l - previous)))
        previous = c
    return mean(trs) if trs else 0.0


def _slope(xs: list[float], atr: float, n: int) -> float:
    if atr <= 0 or len(xs) <= n:
        return 0.0
    return (xs[-1] - xs[-1 - n]) / atr


def _efficiency(xs: list[float], n: int) -> float:
    sample = xs[-n:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)


def _structure(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    highs, lows = [], []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING:i + PIVOT_WING + 1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in window):
            highs.append(h)
        if l <= min(x["low"] for x in window):
            lows.append(l)
    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear:
        state, quality = "BULLISH", min(1.0, 0.62 + 0.07 * bull)
    elif bear >= 2 and bear > bull:
        state, quality = "BEARISH", min(1.0, 0.62 + 0.07 * bear)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.52
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.52
    else:
        state, quality = "MIXED", 0.30
    last = bars[-1]["close"]
    recent_high = max(highs, default=last)
    recent_low = min(lows, default=last)
    buffer = max(0.10 * atr, 1e-12)
    bos = "UP" if last > recent_high + buffer else "DOWN" if last < recent_low - buffer else "NONE"
    return {
        "state": state,
        "quality": quality,
        "counts": {"HH": hh, "HL": hl, "LH": lh, "LL": ll},
        "bos": bos,
        "recent_high": recent_high,
        "recent_low": recent_low,
    }


def _direction(state: str) -> str:
    return "UP" if state == "BULLISH" else "DOWN" if state == "BEARISH" else "NEUTRAL"


def _incomplete(reason: str, valid: int, invalid: int) -> dict[str, Any]:
    return {
        "question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False,
        "decision_authority": "E9_ONLY", "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN_V13",
        "market_state": "UNCLEAR", "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR",
        "structure_quality": 0.0, "structure_alignment": "UNRESOLVED", "directional_pressure": "NEUTRAL",
        "current_pressure": "NEUTRAL", "counter_pressure": "NONE", "dominant_direction": "NEUTRAL",
        "directional_state": "UNRESOLVED", "market_phase": "UNRESOLVED", "transition": "UNRESOLVED",
        "transition_status": "UNRESOLVED", "transition_confirmed": False, "transition_committed": False,
        "structural_persistence": False, "confidence": 0.0, "evidence": [f"valid_candles={valid}", f"invalid_candles={invalid}"],
        "observations": [f"valid_candles={valid}", f"invalid_candles={invalid}"],
        "conflicts": ["DATA_QUALITY_ANOMALIES"] if invalid else [], "reasons": [reason], "reason_codes": [reason],
        "counter_evidence": {"direction": "NEUTRAL", "strength": 0.0, "items": []},
        "transition_commitment": {"required": True, "missing": ["RELIABLE_MARKET_DATA"]},
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"STATE -> UNCLEAR because={reason}"],
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY", "arbitration_order": ARBITRATION_ORDER,
            "trade_boundary": "MARKET_STATE_ONLY", "primary_thesis": {"direction": "NEUTRAL", "status": "UNRESOLVED", "supporting_evidence": [], "counter_evidence": []},
            "confidence_model": {"support": 0.0, "counter_evidence": 0.0, "structure": 0.0, "persistence": 0.0, "stability": 0.0},
            "invalidation": {"conditions": [reason]},
        },
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V13", "e1_engine_version": "PROFESSIONAL_MARKET_STATE_V13",
        "e1_trade_authority": False, "analysis_status": "INCOMPLETE",
    }


def analyze_e1_professional_v13(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    good, invalid = _clean(bars)
    if len(good) < MIN_BARS:
        return _incomplete("INSUFFICIENT_RELIABLE_CLOSED_CANDLES", len(good), invalid)
    if invalid:
        return _incomplete("DATA_QUALITY_ANOMALIES_PRESENT_CLASSIFICATION_WITHHELD", len(good), invalid)

    closes = [b["close"] for b in good]
    atr = _atr(good, 14)
    atr50 = _atr(good, 50)
    if atr <= 0 or atr50 <= 0:
        return _incomplete("ATR_INVALID", len(good), invalid)

    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    ema = "UP" if e20[-1] > e50[-1] else "DOWN" if e20[-1] < e50[-1] else "NEUTRAL"
    ema_gap = (e20[-1] - e50[-1]) / atr

    horizons = (5, 10, 20, 40)
    thresholds = (0.15, 0.20, 0.30, 0.40)
    slopes = [_slope(closes, atr, n) for n in horizons]
    states = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s, t in zip(slopes, thresholds)]
    up, down = states.count("UP"), states.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "NEUTRAL"
    consensus = max(up, down) / 4.0

    long_states = states[1:]
    long_up, long_down = long_states.count("UP"), long_states.count("DOWN")
    long_direction = "UP" if long_up > long_down else "DOWN" if long_down > long_up else "NEUTRAL"
    long_consensus = max(long_up, long_down) / 3.0

    if pressure == "UP":
        persistence = sum(s >= t for s, t in zip(slopes, (0.20, 0.25, 0.35, 0.45))) / 4.0
        long_persistence = sum(s >= t for s, t in zip(slopes[1:], (0.25, 0.35, 0.45))) / 3.0
    elif pressure == "DOWN":
        persistence = sum(s <= -t for s, t in zip(slopes, (0.20, 0.25, 0.35, 0.45))) / 4.0
        long_persistence = sum(s <= -t for s, t in zip(slopes[1:], (0.25, 0.35, 0.45))) / 3.0
    else:
        persistence = long_persistence = 0.0

    structure = _structure(good, atr)
    sd = _direction(structure["state"])
    structure_80 = _structure(good[-80:], _atr(good[-80:], 14))
    structure_40 = _structure(good[-40:], _atr(good[-40:], 14))
    structural_persistence = sd in DIRECTIONS and sd == _direction(structure_80["state"]) == _direction(structure_40["state"])
    structural_candidate = sd in DIRECTIONS and structure["quality"] >= 0.52

    prior_atr = _atr(good[-64:-14], 50) if len(good) >= 64 else atr50
    volatility_ratio = atr / max(prior_atr, 1e-12)
    compression = volatility_ratio < 0.78
    expansion = volatility_ratio > 1.20
    efficiency20, efficiency40 = _efficiency(closes, 20), _efficiency(closes, 40)

    recent_delta = closes[-1] - closes[-6]
    recent_pressure = "UP" if recent_delta >= 0.15 * atr else "DOWN" if recent_delta <= -0.15 * atr else "NEUTRAL"
    recent8 = _slope(closes, atr, 8)
    context30 = _slope(closes, atr, 30)
    context_flip = abs(context30) >= 0.45 and abs(recent8) >= 0.65 and (context30 > 0) != (recent8 > 0)

    persistent_long = long_direction in DIRECTIONS and long_consensus >= (2 / 3) and long_persistence >= (2 / 3)

    if structural_candidate and persistent_long and sd == long_direction:
        dominant, basis = sd, "STRUCTURE_LONG_HORIZON_PERSISTENCE"
    elif persistent_long and ema == long_direction and abs(ema_gap) >= 0.50:
        dominant, basis = long_direction, "LONG_HORIZON_EMA_ALIGNMENT"
    elif structural_candidate and sd == ema and abs(ema_gap) >= 0.50 and long_direction in {"NEUTRAL", sd}:
        dominant, basis = sd, "STRUCTURE_EMA_ALIGNMENT"
    elif structural_candidate and persistent_long:
        dominant, basis = sd, "STRUCTURE_WITH_LONG_HORIZON_SUPPORT"
    else:
        dominant, basis = "NEUTRAL", "NO_DOMINANT_REGIME"

    if dominant in DIRECTIONS and sd == dominant:
        structure_alignment = "ALIGNED"
    elif dominant in DIRECTIONS and sd in DIRECTIONS and sd != dominant:
        structure_alignment = "COUNTER_TREND"
    elif sd == "MIXED":
        structure_alignment = "MIXED"
    else:
        structure_alignment = "UNRESOLVED"

    counter_direction = "DOWN" if dominant == "UP" else "UP" if dominant == "DOWN" else "NEUTRAL"
    counter_items = []
    if counter_direction in DIRECTIONS:
        if sd == counter_direction: counter_items.append("COUNTER_TREND_STRUCTURE_PRESENT")
        if pressure == counter_direction: counter_items.append("SHORT_HORIZON_COUNTER_PRESSURE")
        if recent_pressure == counter_direction: counter_items.append("RECENT_COUNTER_PRESSURE")
        if context_flip: counter_items.append("CONTEXT_FLIP_REQUIRES_PERSISTENT_REPRICING")
    counter_strength = min(1.0, 0.35 * (sd == counter_direction) + 0.25 * (pressure == counter_direction) + 0.20 * (recent_pressure == counter_direction) + 0.20 * context_flip) if counter_direction in DIRECTIONS else 0.0
    if not counter_items: counter_items = ["NO_MATERIAL_COUNTER_EVIDENCE"]

    candidate_structure = structural_candidate and sd == counter_direction
    candidate_long = long_direction == counter_direction and long_consensus >= (2 / 3) and long_persistence >= (2 / 3)
    candidate_pressure = pressure == counter_direction and recent_pressure == counter_direction
    candidate_ema = ema == counter_direction and abs(ema_gap) >= 0.50
    candidate_bos = structure["bos"] == counter_direction
    candidate_persistent_structure = candidate_structure and structural_persistence
    transition_checks = {
        "STRUCTURAL_REPRICING": candidate_persistent_structure, "LONG_HORIZON_REPRICING": candidate_long,
        "PRESSURE_REPRICING": candidate_pressure, "EMA_REPRICING": candidate_ema,
        "BOS_REPRICING": candidate_bos, "CONTEXT_PERSISTENCE": context_flip,
    }
    transition_confirmed = dominant in DIRECTIONS and all(transition_checks.values())
    transition_missing = [name for name, passed in transition_checks.items() if not passed]

    if transition_confirmed:
        state, transition, phase = "TRANSITION", "CONFIRMED", "TRANSITION"
    elif dominant in DIRECTIONS:
        state = "TREND_UP" if dominant == "UP" else "TREND_DOWN"
        transition = "WATCH" if counter_items != ["NO_MATERIAL_COUNTER_EVIDENCE"] else "ABSENT"
        phase = "PULLBACK" if recent_pressure not in {dominant, "NEUTRAL"} else "IMPULSE" if recent_pressure == dominant else "CONSOLIDATION"
    elif abs(slopes[2]) < 0.65 and efficiency20 < 0.35 and efficiency40 < 0.40:
        state, transition, phase = "RANGE", "ABSENT", "RANGE"
    elif compression:
        state, transition, phase = "COMPRESSION", "WATCH", "COMPRESSION"
    elif expansion:
        state, transition, phase = "EXPANSION", "WATCH", "EXPANSION"
    else:
        state, transition, phase = "TRANSITION", "WATCH", "TRANSITION"

    volatility_state = "CONTRACTING" if compression else "EXPANDING" if expansion else "NORMAL"
    support = min(1.0, 0.45 * long_consensus + 0.30 * long_persistence + 0.25 * structure["quality"]) if dominant in DIRECTIONS else 0.0
    stability = min(1.0, 0.50 * persistence + 0.50 * float(structural_persistence))
    confidence = min(1.0, max(0.0, 0.55 * support + 0.25 * stability + 0.20 * (1.0 - counter_strength))) if dominant in DIRECTIONS else 0.0

    reasons = [f"DOMINANT_BASIS={basis}", "DATA_INTEGRITY_VALIDATED"]
    if structure_alignment == "COUNTER_TREND": reasons.insert(0, "COUNTER_TREND_STRUCTURE_CANNOT_AUTO_FLIP_STATE")
    if persistent_long: reasons.append("LONG_HORIZON_PERSISTENCE_CONFIRMED")
    reasons.append("EMA_AS_CONTEXT_NOT_AUTHORITY")
    if compression: reasons.append("VOLATILITY_COMPRESSION_DETECTED")
    if transition_confirmed: reasons.append("PERSISTENT_STRUCTURAL_REPRICING_CONFIRMED")
    elif dominant in DIRECTIONS: reasons.append("TRANSITION_REQUIRES_PERSISTENT_REPRICING")

    thesis_direction = dominant if dominant in DIRECTIONS else pressure if pressure in DIRECTIONS else "NEUTRAL"
    thesis_status = "ESTABLISHED" if dominant in DIRECTIONS else "UNRESOLVED"
    invalidation = ["PERSISTENT_DOWN_STRUCTURAL_REPRICING", "LONG_HORIZON_DOWN_PERSISTENCE"] if dominant == "UP" else ["PERSISTENT_UP_STRUCTURAL_REPRICING", "LONG_HORIZON_UP_PERSISTENCE"] if dominant == "DOWN" else ["ESTABLISH_RELIABLE_DOMINANT_DIRECTION"]
    observations = [f"valid_candles={len(good)}", f"invalid_candles={invalid}", f"ema20_vs_ema50={ema}", f"ema_gap_atr={ema_gap:.3f}", *[f"price_slope_{n}_atr={s:.3f}" for n, s in zip(horizons, slopes)], f"multi_horizon={','.join(states)}", f"directional_consensus={consensus:.3f}", f"long_horizon_direction={long_direction}", f"long_horizon_consensus={long_consensus:.3f}", f"long_horizon_persistence={long_persistence:.3f}"]
    reasoning_trace = [f"QUESTION -> {QUESTION}", f"PRIMARY_STATE -> {state}", f"DOMINANT_DIRECTION -> {dominant}", f"DOMINANT_BASIS -> {basis}", f"STRUCTURE_ALIGNMENT -> {structure_alignment}", f"COUNTER_EVIDENCE -> {counter_direction}:{counter_strength:.3f}", f"TRANSITION -> {'CONFIRMED' if transition_confirmed else 'NOT_COMMITTED'}"]
    structure_state = structure["state"]

    return {
        "question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False,
        "decision_authority": "E9_ONLY", "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN_V13", "market_state": state,
        "trend_state": dominant if dominant in DIRECTIONS else "NONE", "volatility_state": volatility_state,
        "structure_state": structure_state, "structure_quality": structure["quality"], "structure_alignment": structure_alignment,
        "directional_pressure": pressure, "current_pressure": recent_pressure, "counter_pressure": counter_direction if counter_items != ["NO_MATERIAL_COUNTER_EVIDENCE"] else "NONE",
        "dominant_direction": dominant, "directional_state": state, "market_phase": phase, "transition": transition,
        "transition_status": transition, "transition_confirmed": transition_confirmed, "transition_committed": transition_confirmed,
        "structural_persistence": structural_persistence, "confidence": confidence, "evidence_strength": confidence,
        "observations": observations, "evidence": observations, "reasons": reasons, "reason_codes": reasons,
        "conflicts": counter_items if counter_items != ["NO_MATERIAL_COUNTER_EVIDENCE"] else [],
        "counter_evidence": {"direction": counter_direction, "strength": counter_strength, "items": counter_items},
        "transition_commitment": {"required": dominant in DIRECTIONS, "confirmed": transition_confirmed, "missing": transition_missing},
        "reasoning_trace": reasoning_trace,
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY", "arbitration_order": ARBITRATION_ORDER, "trade_boundary": "MARKET_STATE_ONLY",
            "primary_thesis": {"direction": thesis_direction, "status": thesis_status, "supporting_evidence": [basis, "LONG_HORIZON_PERSISTENCE" if persistent_long else "LONG_HORIZON_UNRESOLVED", f"STRUCTURE={structure_state}"], "counter_evidence": counter_items},
            "confidence_model": {"support": support, "counter_evidence": counter_strength, "structure": structure["quality"], "persistence": long_persistence, "stability": stability},
            "invalidation": {"conditions": invalidation}, "transition_commitment": transition_checks,
        },
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V13", "e1_engine_version": "PROFESSIONAL_MARKET_STATE_V13", "e1_trade_authority": False,
        "analysis_status": "COMPLETE",
    }


__all__ = ["analyze_e1_professional_v13"]
