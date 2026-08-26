from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What is the market doing right now?"
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _clean_bars(bars: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    valid: list[dict[str, Any]] = []
    problems: list[str] = []
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict):
            problems.append(f"bar_{i}_not_mapping")
            continue
        values = {k: _num(bar.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            problems.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = values["open"], values["high"], values["low"], values["close"]
        if h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"bar_{i}_ohlc_inconsistent")
            continue
        valid.append({**bar, **values})
    return valid, problems


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    result: list[float] = []
    previous = None
    for bar in bars:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        result.append(high - low if previous is None else max(high - low, abs(high - previous), abs(low - previous)))
        previous = close
    return result


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    values = _true_ranges(bars[-period:])
    return mean(values) if values else 0.0


def _atr_ratio(bars: list[dict[str, Any]], short: int = 14, long: int = 50) -> float:
    return _atr(bars, short) / max(_atr(bars, long), 1e-12)


def _efficiency(closes: list[float], lookback: int) -> float:
    sample = closes[-lookback:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)


def _signed_efficiency(closes: list[float], lookback: int) -> float:
    sample = closes[-lookback:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return (sample[-1] - sample[0]) / max(path, 1e-12)


def _slope_atr(values: list[float], atr: float, lookback: int) -> float:
    if len(values) <= lookback or atr <= 0:
        return 0.0
    return (values[-1] - values[-1 - lookback]) / atr


def _direction(value: float, threshold: float) -> str:
    if value > threshold:
        return "UP"
    if value < -threshold:
        return "DOWN"
    return "FLAT"


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    if len(bars) < 2 * wing + 1:
        return highs, lows
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        high, low = float(bars[i]["high"]), float(bars[i]["low"])
        if high >= max(float(x["high"]) for x in window):
            highs.append(high)
        if low <= min(float(x["low"]) for x in window):
            lows.append(low)
    return highs, lows


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    highs, lows = _pivots(bars)
    highs, lows = highs[-6:], lows[-6:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear:
        state, quality = "BULLISH", min(1.0, 0.65 + 0.08 * bull)
    elif bear >= 2 and bear > bull:
        state, quality = "BEARISH", min(1.0, 0.65 + 0.08 * bear)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.55
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.55
    else:
        state, quality = "MIXED", 0.30
    return state, quality, {"pivot_highs": highs, "pivot_lows": lows, "higher_highs": hh, "lower_highs": lh, "higher_lows": hl, "lower_lows": ll}


def _volatility(bars: list[dict[str, Any]]) -> tuple[str, bool, bool, float, dict[str, Any]]:
    ratio = _atr_ratio(bars)
    ranges = [float(b["high"]) - float(b["low"]) for b in bars]
    recent = mean(ranges[-6:])
    baseline = mean(ranges[-26:-6]) if len(ranges) >= 26 else median(ranges[:-6] or ranges)
    range_ratio = recent / max(baseline, 1e-12)
    compression = ratio < 0.78 and range_ratio < 0.82
    expansion = ratio > 1.18 or range_ratio >= 1.35
    state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    return state, compression, expansion, range_ratio, {"atr_short_long_ratio": round(ratio, 4), "recent_vs_baseline_range": round(range_ratio, 4)}


def _location(closes: list[float], atr: float) -> tuple[str, float]:
    sample = closes[-20:]
    if len(sample) < 5 or atr <= 0:
        return "EQUILIBRIUM", 0.5
    lo, hi = min(sample), max(sample)
    percentile = (closes[-1] - lo) / max(hi - lo, atr)
    if percentile >= 0.80:
        return "UPPER_RANGE", percentile
    if percentile <= 0.20:
        return "LOWER_RANGE", percentile
    return "EQUILIBRIUM", percentile


def _confidence(state: str, structure_quality: float, persistence: float, efficiency10: float, efficiency20: float, ema_confirmed: bool, conflicts: int, data_quality: float) -> float:
    base = {"TREND_UP": 0.58, "TREND_DOWN": 0.58, "RANGE": 0.56, "COMPRESSION": 0.62, "EXPANSION": 0.55, "TRANSITION": 0.52, "UNCLEAR": 0.25}.get(state, 0.25)
    quality = 0.20 * structure_quality + 0.20 * persistence + 0.16 * min(1.0, efficiency10 / 0.70) + 0.16 * min(1.0, efficiency20 / 0.70) + 0.10 * float(ema_confirmed) + 0.18 * data_quality
    return round(max(0.0, min(0.99, base + 0.34 * quality - min(0.24, 0.04 * conflicts))), 3)


def _incomplete(reason: str, conflicts: list[str] | None = None, evidence: list[str] | None = None) -> dict[str, Any]:
    conflicts = conflicts or []
    evidence = evidence or []
    return {
        "question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "trend_state": "NONE",
        "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN",
        "confidence": 0.0, "evidence": evidence, "conflicts": conflicts,
        "reasoning_trace": [f"QUESTION -> {PROFESSIONAL_QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "direction": "NEUTRAL", "thesis": reason, "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": {}, "directional_consensus": {"ema": "FLAT", "short": "FLAT", "medium": "FLAT", "long": "FLAT", "confirmed": False}, "conflict_detected": bool(conflicts), "conflict_count": len(conflicts), "trend_confirmed": False, "classification_reason": reason, "data_quality": 0.0},
        "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
    }


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """E1 is a market-state analyst, not a trade executor.

    Professional rule: disagreement lowers confidence or marks transition; it does
    not automatically erase a directional thesis. Structure, pressure, persistence,
    volatility and EMA are diagnosed separately and reconciled at the state layer.
    """
    valid, data_problems = _clean_bars(bars)
    if len(valid) < 60:
        return _incomplete("insufficient reliable candles; classification withheld", data_problems[:6], ["valid_candles_below_minimum", *data_problems[:6]])

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    if atr <= 0:
        return _incomplete("ATR invalid; classification withheld", ["ATR_INVALID"], ["atr_invalid"])

    ema20s, ema50s = _ema_series(closes, 20), _ema_series(closes, 50)
    ema20, ema50 = ema20s[-1], ema50s[-1]
    ema_relation = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    ema_gap = (ema20 - ema50) / atr
    ema20_slope, ema50_slope = _slope_atr(ema20s, atr, 5), _slope_atr(ema50s, atr, 5)

    structure, structure_quality, structure_detail = _structure(valid)
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "FLAT"
    volatility_state, compression, expansion, range_ratio, volatility_detail = _volatility(valid)

    short_slope, medium_slope, long_slope = _slope_atr(closes, atr, 5), _slope_atr(closes, atr, 10), _slope_atr(closes, atr, 20)
    short_direction, medium_direction, long_direction = _direction(short_slope, 0.15), _direction(medium_slope, 0.20), _direction(long_slope, 0.30)
    price_dirs = [short_direction, medium_direction, long_direction]
    up_count, down_count = price_dirs.count("UP"), price_dirs.count("DOWN")
    if up_count > down_count:
        pressure = "UP"
    elif down_count > up_count:
        pressure = "DOWN"
    else:
        pressure = "BALANCED"

    if pressure in {"UP", "DOWN"}:
        aligned = sum([
            short_slope >= 0.20 if pressure == "UP" else short_slope <= -0.20,
            medium_slope >= 0.30 if pressure == "UP" else medium_slope <= -0.30,
            long_slope >= 0.45 if pressure == "UP" else long_slope <= -0.45,
        ])
        persistence = aligned / 3.0
    else:
        aligned, persistence = 0, 0.0

    efficiency10, efficiency20 = _efficiency(closes, 10), _efficiency(closes, 20)
    signed_eff10, signed_eff20 = _signed_efficiency(closes, 10), _signed_efficiency(closes, 20)
    ema_confirmed = pressure in {"UP", "DOWN"} and ema_relation == pressure and ((pressure == "UP" and ema20_slope >= -0.05 and ema50_slope >= -0.10) or (pressure == "DOWN" and ema20_slope <= 0.05 and ema50_slope <= 0.10))
    ema_conflict = pressure in {"UP", "DOWN"} and ema_relation in {"UP", "DOWN"} and ema_relation != pressure
    structural_conflict = pressure in {"UP", "DOWN"} and structure_direction in {"UP", "DOWN"} and structure_direction != pressure
    horizon_conflict = len({d for d in price_dirs if d in {"UP", "DOWN"}}) > 1

    prior_high, prior_low = max(highs[-21:-1]), min(lows[-21:-1])
    swept_high = highs[-1] > prior_high and closes[-1] < prior_high
    swept_low = lows[-1] < prior_low and closes[-1] > prior_low
    liquidity_event = swept_high or swept_low

    conflicts: list[str] = []
    if data_problems: conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict: conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structural_conflict: conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict: conflicts.append("SHORT_VS_LONG_HORIZON")
    if liquidity_event: conflicts.append("LIQUIDITY_SWEEP_OR_FAILED_BREAK")
    if pressure == "BALANCED": conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")

    # A mixed structure is evidence about structure quality, not a veto on direction.
    directional_consensus = {"ema": ema_relation, "short": short_direction, "medium": medium_direction, "long": long_direction, "confirmed": pressure in {"UP", "DOWN"} and ema_confirmed and up_count + down_count >= 2 and persistence >= 2 / 3}
    structural_alignment = structure_direction == pressure
    strong_structure = structural_alignment and structure_quality >= 0.55
    trend_confirmed = pressure in {"UP", "DOWN"} and directional_consensus["confirmed"] and efficiency20 >= 0.25 and abs(ema_gap) >= 0.12 and not structural_conflict and not (horizon_conflict and persistence < 2 / 3) and (strong_structure or persistence >= 2 / 3)

    recent_counter_move = False
    if pressure in {"UP", "DOWN"} and len(closes) >= 3:
        a, b = closes[-2] - closes[-3], closes[-1] - closes[-2]
        recent_counter_move = (pressure == "UP" and b < 0 < a) or (pressure == "DOWN" and b > 0 > a)

    # Transition means evidence is actively changing, not merely imperfect.
    genuine_transition = (
        (structural_conflict and persistence < 1.0)
        or (horizon_conflict and persistence < 2 / 3 and efficiency20 < 0.45)
        or (liquidity_event and persistence < 2 / 3)
        or (ema_conflict and structure_direction == pressure and persistence < 2 / 3)
    )

    # Professional hierarchy: compression can dominate when directional evidence is
    # weak; otherwise a persistent directional pressure is retained even when
    # structure is mixed. This is the key fix for the previous false UNCLEAR states.
    if compression and pressure == "BALANCED":
        market_state, final_pressure, reason = "COMPRESSION", "NEUTRAL", "volatility_compression_dominates_while_direction_is_balanced"
    elif genuine_transition and not trend_confirmed:
        market_state, final_pressure, reason = "TRANSITION", pressure if pressure in {"UP", "DOWN"} else "BALANCED", "evidence_is_actively_changing_or_materially_conflicting"
    elif trend_confirmed:
        market_state, final_pressure, reason = ("TREND_UP" if pressure == "UP" else "TREND_DOWN"), pressure, "persistent_direction_and_structural_evidence_are_aligned"
    elif expansion and pressure in {"UP", "DOWN"} and efficiency10 >= 0.25:
        market_state, final_pressure, reason = "EXPANSION", pressure, "volatility_and_price_displacement_are_expanding"
    elif pressure in {"UP", "DOWN"} and persistence >= 1 / 3 and efficiency20 >= 0.20 and not (ema_conflict and structural_conflict):
        market_state, final_pressure, reason = ("TREND_UP" if pressure == "UP" else "TREND_DOWN"), pressure, "directional_pressure_is_persistent_even_though_structure_confirmation_is_incomplete"
    elif pressure == "BALANCED" and efficiency20 < 0.35:
        market_state, final_pressure, reason = "RANGE", "NEUTRAL", "directional_efficiency_is_low_and_neither_side_controls"
    elif pressure in {"UP", "DOWN"}:
        market_state, final_pressure, reason = "UNCLEAR", pressure, "direction_exists_but_persistence_and_regime_evidence_are_insufficient"
    else:
        market_state, final_pressure, reason = "UNCLEAR", "NEUTRAL", "directional_evidence_is_balanced"

    # A one-bar counter move does not reverse an established state.
    if recent_counter_move and market_state in {"TREND_UP", "TREND_DOWN"}:
        reason += ";single_counter_candle_not_enough_to_reverse_state"

    transition = "PRESENT" if market_state == "TRANSITION" else "ABSENT"
    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"
    pressure_label = "UP" if final_pressure == "UP" else "DOWN" if final_pressure == "DOWN" else "NEUTRAL"
    location, location_percentile = _location(closes, atr)
    data_quality = max(0.0, 1.0 - min(1.0, len(data_problems) / max(1, len(valid))))
    confidence = _confidence(market_state, structure_quality, persistence, efficiency10, efficiency20, ema_confirmed, len(conflicts), data_quality)

    if market_state == "TRANSITION":
        thesis = f"Market is transitioning with {('bullish' if final_pressure == 'UP' else 'bearish' if final_pressure == 'DOWN' else 'balanced')} pressure; E1 records the conflict without inventing certainty."
    elif market_state in {"TREND_UP", "TREND_DOWN"}:
        thesis = f"Market is {('bullish' if final_pressure == 'UP' else 'bearish')} and persistent; directional pressure is established while structure quality is {structure_quality:.2f}."
    elif market_state == "EXPANSION":
        thesis = f"Market is expanding with {('bullish' if final_pressure == 'UP' else 'bearish')} pressure; expansion is established before full structural trend confirmation."
    elif market_state == "RANGE":
        thesis = "Market is rotational; directional efficiency is low and neither side controls price persistently."
    elif market_state == "COMPRESSION":
        thesis = "Market is compressed; volatility is contracting and directional pressure is insufficient to dominate the state."
    else:
        thesis = f"Market direction is {pressure_label.lower()}, but regime evidence is not coherent enough for a stronger classification."

    independent_evidence = {
        "ema_relationship": ema_relation, "ema_gap_atr": round(ema_gap, 4), "ema20_slope_atr": round(ema20_slope, 4), "ema50_slope_atr": round(ema50_slope, 4),
        "structure": structure, "structure_quality": round(structure_quality, 3), "price_horizons": {"short": short_direction, "medium": medium_direction, "long": long_direction},
        "price_slopes_atr": {"short": round(short_slope, 4), "medium": round(medium_slope, 4), "long": round(long_slope, 4)},
        "pressure": pressure_label, "volatility": volatility_state, "atr_short_long_ratio": round(volatility_detail["atr_short_long_ratio"], 4), "recent_vs_baseline_range": round(range_ratio, 4),
        "efficiency_10": round(efficiency10, 4), "efficiency_20": round(efficiency20, 4), "signed_efficiency_10": round(signed_eff10, 4), "signed_efficiency_20": round(signed_eff20, 4),
        "liquidity_event": liquidity_event, "location": location, "location_percentile": round(location_percentile, 4),
    }

    evidence = [
        f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"price_slope_atr={short_slope:.3f}", f"price_medium_slope_atr={medium_slope:.3f}", f"price_long_slope_atr={long_slope:.3f}",
        f"structure={structure}", f"structure_quality={structure_quality:.3f}", f"directional_pressure={pressure_label}", f"price_consensus={max(up_count, down_count)}/3",
        f"trend_persistence={persistence:.3f}", f"price_efficiency_10={efficiency10:.3f}", f"price_efficiency_20={efficiency20:.3f}", f"ema_confirmed={ema_confirmed}",
        f"ema_conflict={ema_conflict}", f"structure_conflict={structural_conflict}", f"horizon_conflict={horizon_conflict}", f"sweep_high={swept_high}", f"sweep_low={swept_low}",
    ]

    reasoning_trace = [
        f"QUESTION -> {PROFESSIONAL_QUESTION}", f"DATA_QUALITY -> valid_candles={len(valid)} problems={len(data_problems)}",
        f"VOLATILITY -> {volatility_state} compression={compression} expansion={expansion}", f"STRUCTURE -> {structure} quality={structure_quality:.2f}",
        f"PRESSURE -> {pressure_label} short={short_direction} medium={medium_direction} long={long_direction}", f"PERSISTENCE -> {persistence:.2f} aligned_windows={aligned}",
        f"STATE -> {market_state} because={reason}", f"TRANSITION -> {transition} conflicts={','.join(conflicts) if conflicts else 'NONE'}", f"THESIS -> {thesis}",
    ]

    return {
        "question": PROFESSIONAL_QUESTION, "market_state": market_state, "directional_pressure": pressure_label, "trend_state": trend_state,
        "volatility_state": volatility_state, "structure_state": structure, "structure_quality": round(structure_quality, 3),
        "compression": "PRESENT" if compression else "ABSENT", "expansion": "PRESENT" if expansion else "ABSENT", "transition": transition,
        "confidence": confidence, "evidence": evidence, "conflicts": conflicts, "reasoning_trace": reasoning_trace,
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": market_state, "direction": final_pressure, "thesis": thesis,
            "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": independent_evidence, "directional_consensus": directional_consensus,
            "structure_detail": structure_detail, "persistence_detail": {"aligned_windows": aligned, "windows": {"short": round(short_slope, 4), "medium": round(medium_slope, 4), "long": round(long_slope, 4)}},
            "volatility_detail": volatility_detail, "ema": {"relation": ema_relation, "gap_atr": round(ema_gap, 4), "ema20_slope_atr": round(ema20_slope, 4), "ema50_slope_atr": round(ema50_slope, 4), "confirmed": ema_confirmed, "conflict": ema_conflict},
            "conflict_detected": bool(conflicts), "conflict_count": len(conflicts), "trend_confirmed": trend_confirmed, "classification_reason": reason, "data_quality": round(data_quality, 3),
        },
        "analysis_status": "COMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
    }
