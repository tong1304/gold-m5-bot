from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What is the market doing right now?"
# E1's own reasoning order. This is intentionally independent from E2-E9 and all sub-engines.
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
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
        result.append(value)
    return result


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    result: list[float] = []
    previous = None
    for bar in bars:
        h, l, c = float(bar["high"]), float(bar["low"]), float(bar["close"])
        result.append(h - l if previous is None else max(h - l, abs(h - previous), abs(l - previous)))
        previous = c
    return result


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    trs = _true_ranges(bars[-period:])
    return mean(trs) if trs else 0.0


def _atr_ratio(bars: list[dict[str, Any]], short: int = 14, long: int = 50) -> float:
    return _atr(bars, short) / max(_atr(bars, long), 1e-12)


def _slope_atr(values: list[float], atr: float, lookback: int) -> float:
    if len(values) <= lookback or atr <= 0:
        return 0.0
    return (values[-1] - values[-1 - lookback]) / atr


def _direction(value: float, threshold: float = 0.15) -> str:
    if value > threshold:
        return "UP"
    if value < -threshold:
        return "DOWN"
    return "FLAT"


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


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    if len(bars) < 2 * wing + 1:
        return highs, lows
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        high = float(bars[i]["high"])
        low = float(bars[i]["low"])
        if high >= max(float(x["high"]) for x in window):
            highs.append(high)
        if low <= min(float(x["low"]) for x in window):
            lows.append(low)
    return highs, lows


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    pivot_highs, pivot_lows = _pivots(bars)
    highs, lows = pivot_highs[-6:], pivot_lows[-6:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    bull = min(hh, hl)
    bear = min(lh, ll)
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
    return state, quality, {"higher_highs": hh, "lower_highs": lh, "higher_lows": hl, "lower_lows": ll,
                            "pivot_highs": highs, "pivot_lows": lows}


def _volatility(bars: list[dict[str, Any]]) -> tuple[str, bool, bool, float, dict[str, Any]]:
    ratio = _atr_ratio(bars)
    ranges = [float(b["high"]) - float(b["low"]) for b in bars]
    recent = mean(ranges[-6:])
    baseline = mean(ranges[-26:-6]) if len(ranges) >= 26 else median(ranges[:-6] or ranges)
    range_ratio = recent / max(baseline, 1e-12)
    compression = ratio < 0.78 and range_ratio < 0.82
    expansion = ratio > 1.18 or range_ratio >= 1.35
    state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    return state, compression, expansion, range_ratio, {"atr_short_long_ratio": ratio, "recent_vs_baseline_range": range_ratio}


def _confidence(state: str, structure_quality: float, persistence: float, efficiency: float,
                consensus: int, ema_confirmed: bool, conflict_count: int, data_quality: float) -> float:
    base = {"TREND_UP": 0.62, "TREND_DOWN": 0.62, "RANGE": 0.58, "COMPRESSION": 0.60,
            "EXPANSION": 0.54, "TRANSITION": 0.58, "UNCLEAR": 0.25}.get(state, 0.25)
    quality = (0.24 * structure_quality + 0.24 * persistence + 0.20 * min(1.0, efficiency / 0.70)
               + 0.12 * (consensus / 3.0) + 0.08 * float(ema_confirmed) + 0.12 * data_quality)
    penalty = min(0.32, 0.08 * conflict_count)
    return round(max(0.0, min(0.99, base + 0.34 * quality - penalty)), 3)


def _incomplete_result(reason: str, conflicts: list[str] | None = None) -> dict[str, Any]:
    conflicts = conflicts or []
    return {
        "question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL",
        "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR",
        "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0,
        "evidence": [reason], "conflicts": conflicts, "reasoning_trace": [f"QUESTION -> {PROFESSIONAL_QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR",
            "direction": "NEUTRAL", "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "confidence": 0.0,
            "trend_persistence": 0.0, "next_question": "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?",
            "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": {},
            "directional_consensus": {"ema": "FLAT", "short": "FLAT", "medium": "FLAT", "long": "FLAT", "confirmed": False},
            "conflict_detected": bool(conflicts), "conflict_count": len(conflicts), "classification_reason": reason,
        },
        "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False, "decision_authority": "E9_ONLY",
    }


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """E1 professional market-state brain.

    E1 is deliberately self-contained. It reads raw OHLC data and derives its own
    structure, price behaviour, pressure, persistence, volatility and EMA context.
    It does not consume E2-E9, peer evidence, specialist output, scores, gates or
    trade decisions. It describes the market; it never chooses an entry or trade.
    """
    valid, data_problems = _clean_bars(bars)
    if len(valid) < 60:
        return _incomplete_result("valid_candles_below_minimum", data_problems[:6])

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    if atr <= 0:
        return _incomplete_result("atr_invalid", ["atr_invalid"])

    ema20s, ema50s = _ema_series(closes, 20), _ema_series(closes, 50)
    ema20, ema50 = ema20s[-1], ema50s[-1]
    ema_relationship = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    ema20_slope = _slope_atr(ema20s, atr, 5)
    ema50_slope = _slope_atr(ema50s, atr, 5)
    ema_gap_atr = (ema20 - ema50) / atr

    structure, structure_quality, structure_detail = _structure(valid)
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "FLAT"
    volatility_state, compression, expansion, range_ratio, volatility_detail = _volatility(valid)

    short_slope = _slope_atr(closes, atr, 5)
    medium_slope = _slope_atr(closes, atr, 10)
    long_slope = _slope_atr(closes, atr, 20)
    short_direction = _direction(short_slope, 0.15)
    medium_direction = _direction(medium_slope, 0.20)
    long_direction = _direction(long_slope, 0.30)
    directions = [short_direction, medium_direction, long_direction]
    up_count, down_count = directions.count("UP"), directions.count("DOWN")

    if up_count >= 2 and up_count > down_count:
        pressure = "UP"
    elif down_count >= 2 and down_count > up_count:
        pressure = "DOWN"
    elif structure_direction in {"UP", "DOWN"}:
        pressure = structure_direction
    else:
        pressure = "NEUTRAL"

    persistence = 0.0
    persistence_windows: dict[str, float] = {}
    if pressure in {"UP", "DOWN"}:
        thresholds = (("short", 5, 0.20), ("medium", 10, 0.30), ("long", 20, 0.45))
        aligned = 0
        for name, lb, threshold in thresholds:
            value = _slope_atr(closes, atr, lb)
            persistence_windows[name] = round(value, 4)
            aligned += int(value >= threshold if pressure == "UP" else value <= -threshold)
        persistence = aligned / 3.0

    efficiency10 = _efficiency(closes, 10)
    efficiency20 = _efficiency(closes, 20)
    signed10 = _signed_efficiency(closes, 10)
    signed20 = _signed_efficiency(closes, 20)

    ema_confirmed = pressure in {"UP", "DOWN"} and ema_relationship == pressure and (
        (pressure == "UP" and ema20_slope >= -0.05 and ema50_slope >= -0.10) or
        (pressure == "DOWN" and ema20_slope <= 0.05 and ema50_slope <= 0.10)
    )
    ema_conflict = pressure in {"UP", "DOWN"} and ema_relationship in {"UP", "DOWN"} and ema_relationship != pressure
    structural_conflict = pressure in {"UP", "DOWN"} and structure_direction in {"UP", "DOWN"} and structure_direction != pressure
    horizon_conflict = short_direction in {"UP", "DOWN"} and long_direction in {"UP", "DOWN"} and short_direction != long_direction

    prior_high, prior_low = max(highs[-21:-1]), min(lows[-21:-1])
    sweep_high = highs[-1] > prior_high and closes[-1] < prior_high
    sweep_low = lows[-1] < prior_low and closes[-1] > prior_low
    liquidity_event = sweep_high or sweep_low

    conflicts: list[str] = []
    if data_problems:
        conflicts.append("DATA_QUALITY_ANOMALIES")
    if structural_conflict:
        conflicts.append("directional_structure_conflict")
    if ema_conflict:
        conflicts.append("EMA_VS_PRICE_PRESSURE")
    if horizon_conflict:
        conflicts.append("SHORT_VS_LONG_HORIZON")
    if liquidity_event:
        conflicts.append("LIQUIDITY_SWEEP_OR_FAILED_BREAK")
    if pressure == "NEUTRAL":
        conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")

    strong_structure = structure_direction == pressure and structure_quality >= 0.55
    consensus_confirmed = (
        pressure in {"UP", "DOWN"}
        and up_count + down_count == 3
        and ((up_count == 3 and pressure == "UP") or (down_count == 3 and pressure == "DOWN"))
        and ema_relationship == pressure
    )

    # Professional classification: do not call a trend merely because EMA and
    # one short horizon agree. A named trend needs structure + persistence +
    # efficient directional behaviour. Conflicts are elevated to TRANSITION.
    transition_active = (
        structural_conflict
        or (horizon_conflict and persistence < 1.0)
        or (liquidity_event and persistence < 2 / 3)
    )
    trend_confirmed = (
        pressure in {"UP", "DOWN"}
        and strong_structure
        and persistence >= 2 / 3
        and efficiency20 >= 0.25
        and abs(ema_gap_atr) >= 0.12
        and ema_confirmed
        and not transition_active
    )

    if compression and efficiency20 < 0.45:
        market_state, final_pressure, classification_reason = "COMPRESSION", "NEUTRAL", "volatility_compression_dominates_direction"
    elif transition_active:
        market_state, final_pressure, classification_reason = "TRANSITION", pressure, "material_structure_horizon_or_liquidity_change"
    elif trend_confirmed:
        market_state, final_pressure, classification_reason = ("TREND_UP" if pressure == "UP" else "TREND_DOWN"), pressure, "structure_price_pressure_persistence_ema_aligned"
    elif expansion:
        market_state, final_pressure, classification_reason = "EXPANSION", pressure, "volatility_expanding_without_full_trend_confirmation"
    elif pressure == "NEUTRAL" and efficiency20 < 0.35:
        market_state, final_pressure, classification_reason = "RANGE", "NEUTRAL", "directional_efficiency_is_low"
    elif pressure in {"UP", "DOWN"} and strong_structure and persistence >= 1 / 3 and not ema_conflict:
        market_state, final_pressure, classification_reason = ("TREND_UP" if pressure == "UP" else "TREND_DOWN"), pressure, "directional_state_present_with_moderate_confirmation"
    else:
        market_state, final_pressure, classification_reason = "UNCLEAR", pressure, "evidence_not_coherent_enough_for_named_regime"

    transition = "PRESENT" if market_state == "TRANSITION" else "ABSENT"
    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"
    location_percentile = (closes[-1] - min(closes[-20:])) / max(max(closes[-20:]) - min(closes[-20:]), atr)
    data_quality = max(0.0, 1.0 - min(1.0, len(data_problems) / max(1, len(valid))))
    confidence = _confidence(market_state, structure_quality, persistence, efficiency20,
                             max(up_count, down_count), ema_confirmed, len(conflicts), data_quality)

    direction_word = "bullish" if final_pressure == "UP" else "bearish" if final_pressure == "DOWN" else "neutral"
    if market_state == "TREND_UP" or market_state == "TREND_DOWN":
        thesis = f"Market is {market_state}: structure, multi-horizon price behaviour and persistence support {direction_word}; EMA is confirmation, not the primary cause."
    elif market_state == "TRANSITION":
        thesis = f"Market is transitioning with {direction_word} pressure; conflicting or changing evidence prevents a clean trend label."
    elif market_state == "RANGE":
        thesis = "Market is rotational/ranging; directional efficiency is too low for a persistent directional state."
    elif market_state == "COMPRESSION":
        thesis = "Market is compressed; volatility contraction dominates and directional commitment is insufficient."
    elif market_state == "EXPANSION":
        thesis = f"Market is expanding with {direction_word} pressure, but trend confirmation is incomplete."
    else:
        thesis = "Market evidence is mixed; E1 withholds a stronger regime label rather than forcing a trend."

    independent_evidence = {
        "structure": structure,
        "structure_quality": round(structure_quality, 3),
        "ema_relationship": ema_relationship,
        "ema_gap_atr": round(ema_gap_atr, 4),
        "ema20_slope_atr": round(ema20_slope, 4),
        "ema50_slope_atr": round(ema50_slope, 4),
        "price_short_slope_atr": round(short_slope, 4),
        "price_medium_slope_atr": round(medium_slope, 4),
        "price_long_slope_atr": round(long_slope, 4),
        "price_efficiency_10": round(efficiency10, 4),
        "price_efficiency_20": round(efficiency20, 4),
        "signed_efficiency_10": round(signed10, 4),
        "signed_efficiency_20": round(signed20, 4),
        "volatility": volatility_state,
        "atr_short_long_ratio": round(volatility_detail["atr_short_long_ratio"], 4),
        "recent_vs_baseline_range": round(range_ratio, 4),
        "persistence": round(persistence, 4),
        "liquidity_sweep_high": sweep_high,
        "liquidity_sweep_low": sweep_low,
    }
    directional_consensus = {
        "ema": ema_relationship,
        "short": short_direction,
        "medium": medium_direction,
        "long": long_direction,
        "pressure": final_pressure,
        "confirmed": consensus_confirmed,
    }

    evidence = [
        f"ema20_vs_ema50={ema_relationship}", f"ema_gap_atr={ema_gap_atr:.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"price_slope_atr={short_slope:.3f}", f"price_medium_slope_atr={medium_slope:.3f}",
        f"price_long_slope_atr={long_slope:.3f}", f"structure={structure}",
        f"structure_quality={structure_quality:.3f}", f"directional_pressure={'UP' if final_pressure == 'UP' else 'DOWN' if final_pressure == 'DOWN' else 'NEUTRAL'}",
        f"price_consensus={max(up_count, down_count)}/3", f"trend_persistence={persistence:.3f}",
        f"price_efficiency_10={efficiency10:.3f}", f"price_efficiency_20={efficiency20:.3f}",
        f"signed_efficiency_10={signed10:.3f}", f"signed_efficiency_20={signed20:.3f}",
        f"recent_vs_baseline_range={range_ratio:.3f}", f"atr_short_long_ratio={volatility_detail['atr_short_long_ratio']:.3f}",
        f"ema_confirmed={ema_confirmed}", f"ema_conflict={ema_conflict}",
        f"structure_conflict={structural_conflict}", f"horizon_conflict={horizon_conflict}",
        f"sweep_high={sweep_high}", f"sweep_low={sweep_low}",
    ]
    reasoning_trace = [
        f"QUESTION -> {PROFESSIONAL_QUESTION}",
        f"DATA_QUALITY -> valid_candles={len(valid)} problems={len(data_problems)}",
        f"VOLATILITY -> {volatility_state} compression={compression} expansion={expansion}",
        f"STRUCTURE -> {structure} quality={structure_quality:.2f}",
        f"PRESSURE -> {final_pressure} short={short_direction} medium={medium_direction} long={long_direction}",
        f"PERSISTENCE -> {persistence:.2f} windows={persistence_windows}",
        f"STATE -> {market_state} because={classification_reason}",
        f"TRANSITION -> {transition} conflicts={','.join(conflicts) if conflicts else 'NONE'}",
        f"THESIS -> {thesis}",
    ]

    return {
        "question": PROFESSIONAL_QUESTION,
        "market_state": market_state,
        "directional_pressure": final_pressure,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure,
        "structure_quality": round(structure_quality, 3),
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": transition,
        "confidence": confidence,
        "evidence": evidence,
        "conflicts": conflicts,
        "reasoning_trace": reasoning_trace,
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION,
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": market_state,
            "market_state": market_state,
            "direction": final_pressure,
            "directional_pressure": final_pressure,
            "confidence": confidence,
            "trend_persistence": persistence,
            "next_question": (
                "IS_THIS_STATE_STABLE_OR_TRANSITIONING?" if market_state in {"TREND_UP", "TREND_DOWN", "TRANSITION"}
                else "IS_DIRECTIONAL_PRESSURE_STRONG_ENOUGH_TO_MATTER?" if final_pressure in {"UP", "DOWN"}
                else "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?"
            ),
            "evidence_hierarchy": EVIDENCE_HIERARCHY,
            "independent_evidence": independent_evidence,
            "directional_consensus": directional_consensus,
            "structure_detail": structure_detail,
            "volatility_detail": volatility_detail,
            "persistence_windows": persistence_windows,
            "ema": {"relationship": ema_relationship, "gap_atr": round(ema_gap_atr, 4), "confirmed": ema_confirmed, "conflict": ema_conflict},
            "conflict_detected": bool(conflicts),
            "conflict_count": len(conflicts),
            "trend_confirmed": trend_confirmed,
            "classification_reason": classification_reason,
            "location_percentile": round(location_percentile, 3),
            "data_quality": round(data_quality, 3),
        },
        "analysis_status": "COMPLETE",
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }
