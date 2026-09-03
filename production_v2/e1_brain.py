"""E1 Professional Market-State Brain.

E1 answers only: what is the market doing right now?
It never creates a setup, entry, risk plan, or trade decision.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 80
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> MULTI_HORIZON -> VOLATILITY -> TRANSITION -> STABILITY -> MARKET_STATE"
OWNERSHIP = {
    "owns": [
        "data_integrity", "volatility_regime", "market_structure_context",
        "directional_pressure", "multi_horizon_alignment", "trend_persistence",
        "range_regime", "compression_regime", "expansion_regime",
        "regime_transition", "state_stability", "counter_evidence",
        "market_state_invalidation", "market_regime",
    ],
    "does_not_own": [
        "opportunity_setup", "trade_location", "entry_confirmation",
        "trade_economics", "risk_management", "trade_execution", "BUY", "SELL",
    ],
}


def _num(value: Any):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    current = values[0]
    result = [current]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    trs: list[float] = []
    previous_close = None
    for bar in bars[-period:]:
        high, low, close = bar["high"], bar["low"], bar["close"]
        trs.append(high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    return mean(trs) if trs else 0.0


def _slope(values: list[float], atr: float, period: int) -> float:
    return 0.0 if len(values) <= period or atr <= 0 else (values[-1] - values[-1 - period]) / atr


def _efficiency(values: list[float], period: int) -> float:
    sample = values[-period:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return _clamp(abs(sample[-1] - sample[0]) / max(path, 1e-12))


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING:i + PIVOT_WING + 1]
        high, low = bars[i]["high"], bars[i]["low"]
        if high >= max(x["high"] for x in window):
            highs.append(high)
        if low <= min(x["low"] for x in window):
            lows.append(low)
    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    bullish, bearish = min(hh, hl), min(lh, ll)
    if bullish >= 2 and bullish > bearish:
        return "BULLISH", _clamp(0.58 + 0.07 * bullish)
    if bearish >= 2 and bearish > bullish:
        return "BEARISH", _clamp(0.58 + 0.07 * bearish)
    if hh + hl >= 3 and hh + hl > lh + ll:
        return "BULLISH", 0.52
    if lh + ll >= 3 and lh + ll > hh + hl:
        return "BEARISH", 0.52
    return "MIXED", 0.30


def _base_output() -> dict[str, Any]:
    return {
        "question": QUESTION,
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }


def _incomplete(conflicts: list[str], evidence: list[str], reason: str) -> dict[str, Any]:
    return {
        **_base_output(),
        "market_state": "UNCLEAR",
        "directional_pressure": "NEUTRAL",
        "trend_state": "NONE",
        "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR",
        "structure_quality": 0.0,
        "compression": "UNKNOWN",
        "expansion": "UNKNOWN",
        "transition": "UNKNOWN",
        "confidence": 0.0,
        "evidence": evidence,
        "conflicts": conflicts,
        "reasons": [reason],
        "analysis_status": "INCOMPLETE",
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": "UNCLEAR",
            "trend_maturity": "UNAVAILABLE",
            "trend_confirmed": False,
            "conflict_detected": bool(conflicts),
            "classification_reason": reason,
            "ownership_boundaries": OWNERSHIP,
        },
    }


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, raw in enumerate(bars or []):
        if not isinstance(raw, dict):
            problems.append(f"bar_{index}_not_mapping")
            continue
        values = {key: _num(raw.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            problems.append(f"bar_{index}_ohlc_invalid")
            continue
        open_, high, low, close = values["open"], values["high"], values["low"], values["close"]
        if high < low or high < max(open_, close) or low > min(open_, close):
            problems.append(f"bar_{index}_ohlc_inconsistent")
            continue
        valid.append({**raw, **values})

    if len(valid) < MIN_BARS:
        result = _incomplete(problems[:6], ["valid_candles_below_minimum"], "insufficient reliable candles; classification withheld")
        return result

    closes = [bar["close"] for bar in valid]
    atr14 = _atr(valid, 14)
    if atr14 <= 0:
        return _incomplete([*problems[:5], "ATR_INVALID"], ["atr_invalid"], "ATR invalid; classification withheld")

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema_relation = "UP" if ema20[-1] > ema50[-1] else "DOWN" if ema20[-1] < ema50[-1] else "FLAT"
    ema_gap = (ema20[-1] - ema50[-1]) / atr14
    ema20_slope = _slope(ema20, atr14, 5)
    ema50_slope = _slope(ema50, atr14, 5)

    short_slope = _slope(closes, atr14, 5)
    medium_slope = _slope(closes, atr14, 10)
    long_slope = _slope(closes, atr14, 20)
    directions = [
        "UP" if short_slope > 0.15 else "DOWN" if short_slope < -0.15 else "FLAT",
        "UP" if medium_slope > 0.20 else "DOWN" if medium_slope < -0.20 else "FLAT",
        "UP" if long_slope > 0.30 else "DOWN" if long_slope < -0.30 else "FLAT",
    ]
    up_count, down_count = directions.count("UP"), directions.count("DOWN")
    internal_pressure = "UP" if up_count > down_count else "DOWN" if down_count > up_count else "BALANCED"

    persistence_hits = sum(
        (value >= threshold if internal_pressure == "UP" else value <= -threshold)
        for value, threshold in ((short_slope, 0.20), (medium_slope, 0.30), (long_slope, 0.45))
    ) if internal_pressure in {"UP", "DOWN"} else 0
    persistence = persistence_hits / 3.0

    structure_state, structure_quality = _structure(valid)
    structure_direction = "UP" if structure_state == "BULLISH" else "DOWN" if structure_state == "BEARISH" else "NONE"
    ema_ok = (
        internal_pressure in {"UP", "DOWN"}
        and ema_relation == internal_pressure
        and ((internal_pressure == "UP" and ema20_slope >= -0.05 and ema50_slope >= -0.10)
             or (internal_pressure == "DOWN" and ema20_slope <= 0.05 and ema50_slope <= 0.10))
    )
    ema_conflict = internal_pressure in {"UP", "DOWN"} and ema_relation in {"UP", "DOWN"} and ema_relation != internal_pressure
    structure_conflict = internal_pressure in {"UP", "DOWN"} and structure_direction in {"UP", "DOWN"} and structure_direction != internal_pressure
    horizon_conflict = len({direction for direction in directions if direction in {"UP", "DOWN"}}) > 1

    conflicts = []
    if problems:
        conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict:
        conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structure_conflict:
        conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict:
        conflicts.append("SHORT_VS_LONG_HORIZON")
    if internal_pressure == "BALANCED":
        conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")

    consensus = internal_pressure in {"UP", "DOWN"} and max(up_count, down_count) >= 2 and persistence >= 2 / 3
    strong_structure = structure_direction == internal_pressure and structure_quality >= 0.55
    trend_confirmed = (
        consensus and ema_ok and abs(ema_gap) >= 0.10 and not ema_conflict and not structure_conflict
        and (strong_structure or persistence == 1.0)
    )
    transition_present = (not trend_confirmed) and (
        (ema_conflict and persistence >= 1 / 3)
        or (structure_conflict and persistence >= 1 / 3)
        or (horizon_conflict and _efficiency(closes, 20) < 0.45)
    )

    atr_ratio = _atr(valid, 14) / max(_atr(valid, 50), 1e-12)
    compression = atr_ratio < 0.78
    expansion = atr_ratio > 1.18
    efficiency10 = _efficiency(closes, 10)
    efficiency20 = _efficiency(closes, 20)

    if compression and internal_pressure == "BALANCED":
        market_state, final_direction, classification_reason = "COMPRESSION", "NEUTRAL", "volatility_compression_with_balanced_direction"
    elif transition_present:
        market_state, final_direction, classification_reason = "TRANSITION", internal_pressure, "material_conflict_between_regime_dimensions"
    elif trend_confirmed:
        market_state, final_direction, classification_reason = ("TREND_UP" if internal_pressure == "UP" else "TREND_DOWN"), internal_pressure, "persistent_multi_horizon_direction_with_ema_and_structure_coherence"
    elif expansion and internal_pressure in {"UP", "DOWN"} and efficiency10 >= 0.25:
        market_state, final_direction, classification_reason = "EXPANSION", internal_pressure, "volatility_expansion_with_directional_displacement"
    elif internal_pressure == "BALANCED" and efficiency20 < 0.35:
        market_state, final_direction, classification_reason = "RANGE", "NEUTRAL", "balanced_pressure_and_low_directional_efficiency"
    elif internal_pressure in {"UP", "DOWN"} and consensus and ema_ok and efficiency20 >= 0.12:
        market_state, final_direction, classification_reason = "UNCLEAR", internal_pressure, "directional_regime_developing_without_full_confirmation"
    else:
        market_state, final_direction, classification_reason = "UNCLEAR", internal_pressure, "directional_evidence_exists_but_regime_confirmation_is_insufficient"

    # Public contract: trend_state and directional_pressure are intentionally
    # different vocabularies. Internal UP/DOWN never leaks into pressure output.
    directional_pressure = "BULLISH" if internal_pressure == "UP" else "BEARISH" if internal_pressure == "DOWN" else "NEUTRAL"
    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"
    transition = "PRESENT" if transition_present else "ABSENT"
    volatility_state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    maturity = "ESTABLISHED" if trend_confirmed else "DEVELOPING" if consensus and ema_ok else "DIRECTIONAL_ONLY" if internal_pressure in {"UP", "DOWN"} else "NONE"
    confidence = round(_clamp(0.45 + 0.25 * structure_quality + 0.20 * persistence + 0.10 * min(1.0, efficiency20 / 0.70) + 0.10 * float(ema_ok) - 0.05 * len(conflicts)), 3)

    if market_state == "UNCLEAR":
        confidence = min(confidence, 0.49)
    if market_state == "TRANSITION":
        confidence = min(confidence, 0.75)

    reasoning_trace = [
        f"QUESTION -> {QUESTION}",
        f"STRUCTURE -> {structure_state} quality={structure_quality:.2f}",
        f"PRESSURE -> {directional_pressure} short={directions[0]} medium={directions[1]} long={directions[2]}",
        f"PERSISTENCE -> {persistence:.2f}",
        f"REGIME_CONFIRMATION -> trend_confirmed={trend_confirmed} maturity={maturity}",
        f"STATE -> {market_state} because={classification_reason}",
        f"TRANSITION -> {transition}",
    ]
    reasons = list(conflicts)
    if market_state == "UNCLEAR":
        reasons.append("REGIME_CONFIRMATION_INSUFFICIENT")
    if market_state == "TRANSITION":
        reasons.append("REGIME_CONFLICT_ACTIVE")

    return {
        **_base_output(),
        "market_state": market_state,
        "directional_pressure": directional_pressure,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure_state,
        "structure_quality": round(structure_quality, 3),
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": transition,
        "confidence": confidence,
        "evidence": [
            f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={ema_gap:.3f}",
            f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
            f"price_slope_atr={short_slope:.3f}", f"price_medium_slope_atr={medium_slope:.3f}",
            f"price_long_slope_atr={long_slope:.3f}", f"structure={structure_state}",
            f"structure_quality={structure_quality:.3f}", f"directional_pressure={directional_pressure}",
            f"price_consensus={max(up_count, down_count)}/3", f"trend_persistence={persistence:.3f}",
            f"price_efficiency_10={efficiency10:.3f}", f"price_efficiency_20={efficiency20:.3f}",
            f"trend_maturity={maturity}",
        ],
        "conflicts": conflicts,
        "reasons": reasons,
        "reasoning_trace": reasoning_trace,
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": market_state,
            "market_state": market_state,
            "direction": final_direction,
            "directional_pressure": directional_pressure,
            "trend_maturity": maturity,
            "trend_confirmed": trend_confirmed,
            "conflict_detected": bool(conflicts),
            "conflict_count": len(conflicts),
            "classification_reason": classification_reason,
            "directional_consensus": {
                "ema": ema_relation,
                "short": directions[0], "medium": directions[1], "long": directions[2],
                "confirmed": bool(ema_ok and consensus),
                "count": max(up_count, down_count), "required_count": 2,
            },
            "independent_evidence": {
                "ema_gap_atr": round(ema_gap, 4),
                "structure": structure_state,
                "structure_quality": round(structure_quality, 3),
                "efficiency_10": round(efficiency10, 4),
                "efficiency_20": round(efficiency20, 4),
            },
            "evidence_hierarchy": EVIDENCE_HIERARCHY,
            "ownership_boundaries": OWNERSHIP,
        },
        "analysis_status": "COMPLETE",
    }
