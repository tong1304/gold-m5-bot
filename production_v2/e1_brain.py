from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any


MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What state is the market currently in, what is changing, and what type of opportunity environment does that create?"
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


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    trs: list[float] = []
    previous = None
    for bar in bars:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        trs.append(high - low if previous is None else max(high - low, abs(high - previous), abs(low - previous)))
        previous = close
    return trs


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    trs = _true_ranges(bars[-period:])
    return mean(trs) if trs else 0.0


def _atr_ratio(bars: list[dict[str, Any]], short: int = 14, long: int = 50) -> float:
    return _atr(bars, short) / max(_atr(bars, long), 1e-12)


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    if len(bars) < 2 * wing + 1:
        return highs, lows
    for index in range(wing, len(bars) - wing):
        high = float(bars[index]["high"])
        low = float(bars[index]["low"])
        window = bars[index - wing:index + wing + 1]
        if high >= max(float(x["high"]) for x in window):
            highs.append(high)
        if low <= min(float(x["low"]) for x in window):
            lows.append(low)
    return highs, lows


def _efficiency(closes: list[float], lookback: int) -> float:
    sample = closes[-lookback:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)


def _slope_atr(closes: list[float], atr: float, lookback: int) -> float:
    if len(closes) <= lookback or atr <= 0:
        return 0.0
    return (closes[-1] - closes[-1 - lookback]) / atr


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    highs, lows = _pivots(bars)
    rh, rl = highs[-5:], lows[-5:]
    hh = sum(rh[i] > rh[i - 1] for i in range(1, len(rh)))
    lh = sum(rh[i] < rh[i - 1] for i in range(1, len(rh)))
    hl = sum(rl[i] > rl[i - 1] for i in range(1, len(rl)))
    ll = sum(rl[i] < rl[i - 1] for i in range(1, len(rl)))
    bullish_pairs = min(hh, hl)
    bearish_pairs = min(lh, ll)
    if bullish_pairs >= 2 and bullish_pairs > bearish_pairs:
        state, quality = "BULLISH", min(1.0, 0.62 + 0.10 * bullish_pairs)
    elif bearish_pairs >= 2 and bearish_pairs > bullish_pairs:
        state, quality = "BEARISH", min(1.0, 0.62 + 0.10 * bearish_pairs)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.54
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.54
    else:
        state, quality = "MIXED", 0.30
    return state, quality, {"pivot_highs": rh, "pivot_lows": rl, "higher_highs": hh, "lower_highs": lh, "higher_lows": hl, "lower_lows": ll}


def _persistence(closes: list[float], atr: float, direction: str) -> tuple[float, dict[str, Any]]:
    if direction not in {"UP", "DOWN"}:
        return 0.0, {"aligned_windows": 0, "windows": {}}
    windows = ((5, 0.15), (10, 0.25), (20, 0.40))
    values = {}
    aligned = 0
    for lookback, threshold in windows:
        value = _slope_atr(closes, atr, lookback)
        values[str(lookback)] = round(value, 4)
        aligned += int(value >= threshold if direction == "UP" else value <= -threshold)
    return aligned / len(windows), {"aligned_windows": aligned, "windows": values}


def _volatility(bars: list[dict[str, Any]]) -> tuple[str, bool, bool, dict[str, Any]]:
    ranges = [float(b["high"]) - float(b["low"]) for b in bars]
    ratio = _atr_ratio(bars)
    recent = mean(ranges[-6:]) if ranges else 0.0
    baseline = mean(ranges[-26:-6]) if len(ranges) >= 26 else median(ranges[:-6] or ranges)
    range_ratio = recent / max(baseline, 1e-12)
    compression = ratio < 0.78 and range_ratio < 0.82
    expansion = ratio > 1.18 or range_ratio >= 1.35
    state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    return state, compression, expansion, {"atr_short_long_ratio": round(ratio, 4), "recent_vs_baseline_range": round(range_ratio, 4)}


def _range_analysis(bars: list[dict[str, Any]], atr: float, efficiency: float) -> tuple[float, dict[str, Any]]:
    closes = [float(b["close"]) for b in bars]
    sample = closes[-20:]
    if len(sample) < 5 or atr <= 0:
        return 0.0, {"channel_width_atr": 0.0, "boundary_rejections": 0, "efficiency": efficiency}
    width = (max(sample) - min(sample)) / atr
    near_high = sum(float(b["high"]) >= max(sample) - 0.35 * atr and float(b["close"]) < max(sample) - 0.10 * atr for b in bars[-20:])
    near_low = sum(float(b["low"]) <= min(sample) + 0.35 * atr and float(b["close"]) > min(sample) + 0.10 * atr for b in bars[-20:])
    containment = max(0.0, min(1.0, 1.0 - max(0.0, width - 5.0) / 5.0))
    chop = max(0.0, min(1.0, (0.55 - efficiency) / 0.55))
    rejection = min(1.0, (near_high + near_low) / 4.0)
    quality = 0.45 * containment + 0.35 * chop + 0.20 * rejection
    return quality, {"channel_width_atr": round(width, 4), "boundary_rejections": near_high + near_low, "efficiency": round(efficiency, 4)}


def _tf_context(bars: list[dict[str, Any]] | None, label: str) -> dict[str, Any]:
    valid, problems = _clean_bars(bars)
    if len(valid) < 60:
        return {"available": False, "state": "UNAVAILABLE", "direction": "NONE", "confidence": 0.0, "problems": problems or [f"{label}_insufficient_data"]}
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    slope = _slope_atr(closes, atr, 10)
    structure, sq, _ = _structure(valid)
    votes = (int(ema20 > ema50), int(slope > 0.15), int(structure == "BULLISH"))
    up, down = sum(votes), 3 - sum(votes)
    direction = "UP" if up >= 2 else "DOWN" if down >= 2 else "NONE"
    return {"available": True, "state": "DIRECTIONAL" if direction != "NONE" else "BALANCED", "direction": direction, "confidence": round((max(up, down) / 3.0) * 0.6 + sq * 0.4, 4), "structure": structure, "ema_direction": "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT", "slope_atr": round(slope, 4)}


def analyze_e1(bars: list[dict[str, Any]], *, m15_bars: list[dict[str, Any]] | None = None, h1_bars: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """E1: hierarchical market-state reasoning only.

    M5 is the primary state. M15/H1 are context and can never override M5.
    The brain describes market behavior; it never emits a trade decision.
    """
    valid, data_problems = _clean_bars(bars)
    if len(valid) < 60:
        return {"question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "BALANCED", "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0, "evidence": ["valid_candles_below_minimum", *data_problems[:6]], "conflicts": [], "reasoning_trace": ["QUESTION -> DATA_QUALITY -> insufficient valid M5 candles -> classification withheld"], "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "evidence_hierarchy": EVIDENCE_HIERARCHY, "evidence_dimensions": ["trend", "range", "compression", "expansion", "transition"], "trend_persistence": {"aligned_windows": 0, "windows": {}}, "conflict_detected": bool(data_problems), "confidence_meaning": "MARKET_STATE_CLASSIFICATION_ONLY", "opportunity_environment": "INSUFFICIENT_DATA", "uncertainties": ["insufficient_m5_data"]}, "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY"}

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    ema_gap_atr = abs(ema20 - ema50) / max(atr, 1e-12)
    ema_direction = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    short_slope = _slope_atr(closes, atr, 5)
    medium_slope = _slope_atr(closes, atr, 10)
    long_slope = _slope_atr(closes, atr, 20)
    slope_direction = "UP" if medium_slope > 0.15 else "DOWN" if medium_slope < -0.15 else "FLAT"
    structure, structure_quality, structure_detail = _structure(valid)
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "NONE"
    volatility_state, compression, expansion, volatility_detail = _volatility(valid)
    efficiency_10 = _efficiency(closes, 10)
    efficiency_20 = _efficiency(closes, 20)

    up = int(ema_direction == "UP") + int(slope_direction == "UP") + int(structure_direction == "UP")
    down = int(ema_direction == "DOWN") + int(slope_direction == "DOWN") + int(structure_direction == "DOWN")
    pressure = "UP" if up >= 2 and up > down else "DOWN" if down >= 2 and down > up else "BALANCED"
    persistence, persistence_detail = _persistence(closes, atr, pressure)
    range_quality, range_detail = _range_analysis(valid, atr, efficiency_20)

    ema_structure_conflict = (ema_direction == "UP" and structure == "BEARISH") or (ema_direction == "DOWN" and structure == "BULLISH")
    pressure_structure_conflict = (pressure == "UP" and structure == "BEARISH") or (pressure == "DOWN" and structure == "BULLISH")
    short_long_conflict = (long_slope > 0.45 and short_slope < -0.20) or (long_slope < -0.45 and short_slope > 0.20)
    slope_ema_conflict = (ema_direction == "UP" and medium_slope < -0.15) or (ema_direction == "DOWN" and medium_slope > 0.15)
    failed_high = highs[-1] > max(highs[-21:-1]) and closes[-1] < max(highs[-21:-1])
    failed_low = lows[-1] < min(lows[-21:-1]) and closes[-1] > min(lows[-21:-1])
    liquidity_event = failed_high or failed_low

    trend_quality = (
        0.30 * persistence
        + 0.25 * structure_quality
        + 0.20 * min(1.0, ema_gap_atr / 0.80)
        + 0.15 * min(1.0, abs(medium_slope) / 0.80)
        + 0.10 * min(1.0, efficiency_20 / 0.65)
    )
    if ema_structure_conflict:
        trend_quality -= 0.20
    if pressure_structure_conflict:
        trend_quality -= 0.15
    if short_long_conflict or slope_ema_conflict:
        trend_quality -= 0.10
    trend_quality = max(0.0, min(1.0, trend_quality))

    strong_trend = pressure in {"UP", "DOWN"} and persistence >= 2 / 3 and structure_quality >= 0.60 and trend_quality >= 0.65 and not pressure_structure_conflict
    transition = (
        pressure_structure_conflict
        or short_long_conflict
        or slope_ema_conflict
        or liquidity_event
        or (persistence < 1 / 3 and abs(medium_slope) >= 0.45)
        or (ema_gap_atr < 0.18 and abs(medium_slope) >= 0.70)
    )

    # Transition is a state of change, not merely a label for disagreement.
    if transition and not strong_trend:
        market_state = "TRANSITION"
    elif compression and not strong_trend:
        market_state = "COMPRESSION"
    elif strong_trend and pressure == "UP":
        market_state = "TREND_UP"
    elif strong_trend and pressure == "DOWN":
        market_state = "TREND_DOWN"
    elif range_quality >= 0.55 and pressure == "BALANCED" and not expansion:
        market_state = "RANGE"
    elif expansion:
        market_state = "EXPANSION"
    else:
        market_state = "UNCLEAR"

    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"
    m15 = _tf_context(m15_bars, "M15")
    h1 = _tf_context(h1_bars, "H1")
    mtf_available = bool(m15.get("available") and h1.get("available"))
    mtf_directions = [x.get("direction") for x in (m15, h1) if x.get("available") and x.get("direction") in {"UP", "DOWN"}]
    mtf_conflict = bool(mtf_directions and trend_state in {"UP", "DOWN"} and any(d != trend_state for d in mtf_directions))
    if mtf_available and not mtf_directions:
        mtf_conflict = True

    conflicts: list[str] = []
    if data_problems:
        conflicts.append("data_quality_anomalies_present")
    if ema_structure_conflict:
        conflicts.append("ema_structure_disagreement")
    if pressure_structure_conflict:
        conflicts.append(f"pressure_structure_disagreement:{pressure}:{structure}")
    if short_long_conflict:
        conflicts.append("short_long_slope_disagreement")
    if slope_ema_conflict:
        conflicts.append("ema_slope_disagreement")
    if liquidity_event:
        conflicts.append("failed_break_or_liquidity_event")
    if mtf_conflict:
        conflicts.append("mtf_context_conflict")

    confidence = (
        0.25 * structure_quality
        + 0.25 * persistence
        + 0.20 * min(1.0, abs(medium_slope) / 0.80)
        + 0.15 * min(1.0, ema_gap_atr / 0.80)
        + 0.15 * ({"TREND_UP": 0.95, "TREND_DOWN": 0.95, "RANGE": 0.80, "COMPRESSION": 0.82, "EXPANSION": 0.68, "TRANSITION": 0.55, "UNCLEAR": 0.35}[market_state])
    )
    confidence -= 0.10 * min(1.0, len(conflicts) / 3.0)
    if mtf_conflict:
        confidence -= 0.05
    confidence = max(0.0, min(1.0, confidence))

    if market_state in {"TRANSITION", "UNCLEAR"}:
        opportunity_environment = "CHANGING_OR_UNRESOLVED"
    elif market_state == "RANGE":
        opportunity_environment = "BALANCED_TWO_SIDED_ENVIRONMENT"
    elif market_state == "COMPRESSION":
        opportunity_environment = "CONTRACTING_ENVIRONMENT_AWAITING_EXPANSION"
    elif market_state == "EXPANSION":
        opportunity_environment = "VOLATILITY_EXPANSION_ENVIRONMENT_DIRECTION_NOT_YET_PRIMARY"
    else:
        opportunity_environment = "DIRECTIONAL_ENVIRONMENT_WITHOUT_ENTRY_AUTHORIZATION"

    uncertainties = []
    if ema_structure_conflict: uncertainties.append("ema_structure_disagreement")
    if short_long_conflict or slope_ema_conflict: uncertainties.append("multi_horizon_slope_disagreement")
    if mtf_conflict: uncertainties.append("mtf_context_conflict")
    if market_state == "TRANSITION": uncertainties.append("state_is_changing_not_stable")
    if market_state == "UNCLEAR": uncertainties.append("evidence_not_strong_enough_for_primary_state")
    if not mtf_available: uncertainties.append("mtf_context_unavailable")

    evidence = [
        f"ema20_vs_ema50={ema_direction}", f"ema_gap_atr={ema_gap_atr:.3f}",
        f"price_slope_short_atr={short_slope:.3f}", f"price_slope_medium_atr={medium_slope:.3f}", f"price_slope_long_atr={long_slope:.3f}",
        f"structure={structure}", f"structure_quality={structure_quality:.3f}", f"directional_pressure={pressure}", f"directional_consensus={max(up, down)}/3",
        f"trend_persistence={persistence:.3f}", f"price_efficiency_10={efficiency_10:.3f}", f"price_efficiency_20={efficiency_20:.3f}",
        f"range_quality={range_quality:.3f}", f"recent_vs_baseline_range={volatility_detail['recent_vs_baseline_range']:.3f}",
        f"atr_short_long_ratio={volatility_detail['atr_short_long_ratio']:.3f}", f"compression={compression}", f"expansion={expansion}",
        f"transition={transition}", f"mtf_available={mtf_available}",
    ]

    reasoning_trace = [
        f"QUESTION: {PROFESSIONAL_QUESTION}",
        f"1 DATA_QUALITY: valid_m5={len(valid)}; anomalies={len(data_problems)}.",
        f"2 VOLATILITY: state={volatility_state}; compression={compression}; expansion={expansion}.",
        f"3 STRUCTURE: {structure}; quality={structure_quality:.2f}; HH={structure_detail['higher_highs']}; HL={structure_detail['higher_lows']}; LH={structure_detail['lower_highs']}; LL={structure_detail['lower_lows']}.",
        f"4 PRESSURE: {pressure}; EMA={ema_direction}; slope={slope_direction}; votes={up}/{down}.",
        f"5 PERSISTENCE: {persistence:.2f}; windows={persistence_detail['windows']}.",
        f"6 STATE: trend_quality={trend_quality:.2f}; range_quality={range_quality:.2f}; primary={market_state}.",
        f"7 TRANSITION: {'PRESENT' if transition else 'ABSENT'}; conflicts={conflicts or ['none']}.",
        f"MTF_CONTEXT: M15={m15.get('direction','NONE')}; H1={h1.get('direction','NONE')}; conflict={mtf_conflict}; M5 remains primary.",
        f"CONFIDENCE: {confidence:.2f}; classification confidence only.",
        "BOUNDARY: E1 stops at market-state analysis; no setup, entry, risk, target, sizing, or execution decision.",
    ]

    return {
        "question": PROFESSIONAL_QUESTION,
        "market_state": market_state,
        "directional_pressure": pressure,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure,
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": "PRESENT" if transition else "ABSENT",
        "confidence": round(confidence, 4),
        "evidence": evidence,
        "conflicts": conflicts,
        "reasoning_trace": reasoning_trace,
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION,
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": market_state,
            "directional_pressure": pressure,
            "trend_state": trend_state,
            "volatility_state": volatility_state,
            "structure_state": structure,
            "evidence_dimensions": ["trend", "range", "compression", "expansion", "transition"],
            "trend_quality": round(trend_quality, 4),
            "range_quality": round(range_quality, 4),
            "trend_persistence": persistence_detail,
            "conflict_matrix": {
                "ema_vs_structure": ema_structure_conflict,
                "pressure_vs_structure": pressure_structure_conflict,
                "short_vs_long_slope": short_long_conflict,
                "ema_vs_slope": slope_ema_conflict,
                "mtf": mtf_conflict,
            },
            "conflict_detected": bool(conflicts),
            "confidence_meaning": "MARKET_STATE_CLASSIFICATION_ONLY",
            "opportunity_environment": opportunity_environment,
            "uncertainties": list(dict.fromkeys(uncertainties)),
            "mtf_context": {"available": mtf_available, "m5_primary": True, "override_m5": False, "conflict": mtf_conflict, "M15": m15, "H1": h1},
            "independent_evidence": {
                "ema_relationship": ema_direction,
                "ema_gap_atr": round(ema_gap_atr, 4),
                "price_slope_short_atr": round(short_slope, 4),
                "price_slope_medium_atr": round(medium_slope, 4),
                "price_slope_long_atr": round(long_slope, 4),
                "structure": structure,
                "structure_quality": round(structure_quality, 4),
                "range_quality": round(range_quality, 4),
                "price_efficiency_10": round(efficiency_10, 4),
                "price_efficiency_20": round(efficiency_20, 4),
                "atr_short_long_ratio": volatility_detail["atr_short_long_ratio"],
                "recent_vs_baseline_range": volatility_detail["recent_vs_baseline_range"],
            },
            "next_question": "WHAT_IS_CHANGING_NEXT_AND_IS_THE_CURRENT_STATE_STABLE?",
        },
        "analysis_status": "COMPLETE",
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }
