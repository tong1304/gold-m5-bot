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
    short_atr = _atr(bars, short)
    long_atr = _atr(bars, long)
    return short_atr / max(long_atr, 1e-12)


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
    net = abs(sample[-1] - sample[0])
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return net / max(path, 1e-12)


def _slope_atr(closes: list[float], atr: float, lookback: int) -> float:
    if len(closes) <= lookback or atr <= 0:
        return 0.0
    return (closes[-1] - closes[-1 - lookback]) / atr


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    pivot_highs, pivot_lows = _pivots(bars)
    recent_highs = pivot_highs[-4:]
    recent_lows = pivot_lows[-4:]
    hh = sum(recent_highs[i] > recent_highs[i - 1] for i in range(1, len(recent_highs)))
    lh = sum(recent_highs[i] < recent_highs[i - 1] for i in range(1, len(recent_highs)))
    hl = sum(recent_lows[i] > recent_lows[i - 1] for i in range(1, len(recent_lows)))
    ll = sum(recent_lows[i] < recent_lows[i - 1] for i in range(1, len(recent_lows)))

    bullish_pairs = min(hh, hl)
    bearish_pairs = min(lh, ll)
    if bullish_pairs >= 2 and bullish_pairs > bearish_pairs:
        state, quality = "BULLISH", min(1.0, 0.60 + 0.15 * bullish_pairs)
    elif bearish_pairs >= 2 and bearish_pairs > bullish_pairs:
        state, quality = "BEARISH", min(1.0, 0.60 + 0.15 * bearish_pairs)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.55
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.55
    else:
        state, quality = "MIXED", 0.35

    return state, quality, {
        "pivot_highs": recent_highs,
        "pivot_lows": recent_lows,
        "higher_highs": hh,
        "lower_highs": lh,
        "higher_lows": hl,
        "lower_lows": ll,
    }


def _persistence(closes: list[float], atr: float, direction: str) -> tuple[float, dict[str, Any]]:
    if direction not in {"UP", "DOWN"}:
        return 0.0, {"aligned_windows": 0, "windows": {}}
    signs: dict[str, float] = {}
    aligned = 0
    for name, lookback, threshold in (("short", 5, 0.20), ("medium", 10, 0.30), ("long", 20, 0.45)):
        value = _slope_atr(closes, atr, lookback)
        signs[name] = round(value, 4)
        same = value >= threshold if direction == "UP" else value <= -threshold
        aligned += int(same)
    return aligned / 3.0, {"aligned_windows": aligned, "windows": signs}


def _range_quality(bars: list[dict[str, Any]], atr: float, efficiency: float) -> tuple[float, dict[str, Any]]:
    closes = [float(b["close"]) for b in bars]
    sample = closes[-20:]
    if not sample or atr <= 0:
        return 0.0, {"channel_width_atr": 0.0, "efficiency": efficiency}
    width = (max(sample) - min(sample)) / atr
    # A genuine range is relatively contained and inefficient, not merely flat for one bar.
    width_quality = max(0.0, min(1.0, 1.0 - max(0.0, width - 5.0) / 5.0))
    chop_quality = max(0.0, min(1.0, (0.50 - efficiency) / 0.50))
    return 0.5 * width_quality + 0.5 * chop_quality, {
        "channel_width_atr": round(width, 4),
        "efficiency": round(efficiency, 4),
    }


def _volatility(bars: list[dict[str, Any]]) -> tuple[str, bool, bool, float, dict[str, Any]]:
    ratio = _atr_ratio(bars)
    ranges = [float(b["high"]) - float(b["low"]) for b in bars]
    recent = mean(ranges[-6:])
    baseline = mean(ranges[-26:-6]) if len(ranges) >= 26 else median(ranges[:-6] or ranges)
    range_ratio = recent / max(baseline, 1e-12)
    compression = ratio < 0.78 and range_ratio < 0.82
    expansion = ratio > 1.18 or range_ratio >= 1.35
    state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    return state, compression, expansion, range_ratio, {
        "atr_short_long_ratio": round(ratio, 4),
        "recent_vs_baseline_range": round(range_ratio, 4),
    }


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """E1 Professional Market-State Brain.

    The brain answers one question only: "What is the market doing right now?"
    It classifies behavior from independent evidence, preserves conflicts, and
    never makes a BUY/SELL, entry, stop, target, RR, sizing, or trade decision.
    """
    valid, data_problems = _clean_bars(bars)
    if len(valid) < 60:
        return {
            "question": PROFESSIONAL_QUESTION,
            "market_state": "UNCLEAR",
            "directional_pressure": "BALANCED",
            "trend_state": "NONE",
            "volatility_state": "UNKNOWN",
            "structure_state": "UNCLEAR",
            "compression": "UNKNOWN",
            "expansion": "UNKNOWN",
            "transition": "UNKNOWN",
            "confidence": 0.0,
            "evidence": ["valid_candles_below_minimum", *data_problems[:6]],
            "conflicts": [],
            "reasoning_trace": ["QUESTION -> data quality -> insufficient valid candles -> classification withheld"],
            "professional_reasoning": {
                "question": PROFESSIONAL_QUESTION,
                "task": "DESCRIBE_MARKET_STATE_ONLY",
                "primary_state": "UNCLEAR",
                "next_question": "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?",
                "evidence_hierarchy": EVIDENCE_HIERARCHY,
                "trend_persistence": {"aligned_windows": 0, "windows": {}},
                "conflict_detected": bool(data_problems),
            },
            "analysis_status": "INCOMPLETE",
            "reasoning_role": "MARKET_STATE_ANALYST",
            "trade_decision_authority": False,
            "decision_authority": "E9_ONLY",
        }

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    ema_fast_slope = _slope_atr(closes[-35:], atr, 10)
    ema_gap_atr = abs(ema20 - ema50) / max(atr, 1e-12)
    structure, structure_quality, structure_detail = _structure(valid)
    volatility_state, compression, expansion, range_ratio, volatility_detail = _volatility(valid)
    efficiency_10 = _efficiency(closes, 10)
    efficiency_20 = _efficiency(closes, 20)

    ema_direction = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    slope_direction = "UP" if ema_fast_slope > 0.15 else "DOWN" if ema_fast_slope < -0.15 else "FLAT"
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "FLAT"

    raw_up = int(ema_direction == "UP") + int(slope_direction == "UP") + int(structure_direction == "UP")
    raw_down = int(ema_direction == "DOWN") + int(slope_direction == "DOWN") + int(structure_direction == "DOWN")
    pressure = "UP" if raw_up >= 2 and raw_up > raw_down else "DOWN" if raw_down >= 2 and raw_down > raw_up else "BALANCED"
    persistence, persistence_detail = _persistence(closes, atr, pressure)

    # Professional distinction: direction is not enough; it must persist across horizons.
    directional_strength = (max(raw_up, raw_down) / 3.0) * 0.45 + persistence * 0.35 + min(1.0, ema_gap_atr / 1.0) * 0.20
    strong_direction = pressure in {"UP", "DOWN"} and persistence >= 2 / 3 and directional_strength >= 0.62

    # A short/long disagreement is more informative than a single opposite candle.
    long_slope = _slope_atr(closes, atr, 20)
    short_slope = _slope_atr(closes, atr, 5)
    slope_flip = (long_slope > 0.45 and short_slope < -0.20) or (long_slope < -0.45 and short_slope > 0.20)
    structural_conflict = (pressure == "UP" and structure == "BEARISH") or (pressure == "DOWN" and structure == "BULLISH")
    liquidity_break = highs[-1] > max(highs[-21:-1]) and closes[-1] < max(highs[-21:-1])
    liquidity_break |= lows[-1] < min(lows[-21:-1]) and closes[-1] > min(lows[-21:-1])
    transition = structural_conflict or slope_flip or liquidity_break

    range_quality, range_detail = _range_quality(valid, atr, efficiency_20)
    balanced_behavior = pressure == "BALANCED" or persistence < 1 / 3

    if transition and not strong_direction:
        market_state = "TRANSITION"
    elif compression and not strong_direction:
        market_state = "COMPRESSION"
    elif strong_direction and pressure == "UP":
        market_state = "TREND_UP"
    elif strong_direction and pressure == "DOWN":
        market_state = "TREND_DOWN"
    elif expansion and strong_direction:
        # Expansion is retained as volatility evidence, while the primary behavior remains trend.
        market_state = "TREND_UP" if pressure == "UP" else "TREND_DOWN"
    elif range_quality >= 0.55 and balanced_behavior:
        market_state = "RANGE"
    elif expansion:
        market_state = "EXPANSION"
    else:
        market_state = "UNCLEAR"

    if market_state == "TREND_UP": trend_state = "UP"
    elif market_state == "TREND_DOWN": trend_state = "DOWN"
    else: trend_state = "NONE"

    conflicts: list[str] = []
    if data_problems:
        conflicts.append("data_quality_anomalies_present")
    if structural_conflict:
        conflicts.append(f"direction={pressure} conflicts with structure={structure}")
    if slope_flip:
        conflicts.append("short_horizon_slope_conflicts_with_long_horizon_slope")
    if liquidity_break:
        conflicts.append("liquidity_sweep_or_failed_break_detected")
    if balanced_behavior and pressure == "BALANCED":
        conflicts.append("directional_pressure_is_balanced")

    # Confidence rewards independent agreement and penalizes unresolved conflict.
    agreement = max(raw_up, raw_down) / 3.0
    persistence_quality = persistence
    state_quality = {
        "TREND_UP": 0.92,
        "TREND_DOWN": 0.92,
        "RANGE": 0.78,
        "COMPRESSION": 0.82,
        "EXPANSION": 0.72,
        "TRANSITION": 0.58,
        "UNCLEAR": 0.35,
    }[market_state]
    confidence = (
        0.20 * agreement
        + 0.20 * structure_quality
        + 0.20 * persistence_quality
        + 0.15 * min(1.0, ema_gap_atr / 1.0)
        + 0.15 * min(1.0, efficiency_20 / 0.65)
        + 0.10 * state_quality
    )
    confidence -= 0.12 * min(1.0, len(conflicts) / 3.0)
    if data_problems:
        confidence -= 0.08
    confidence = max(0.0, min(1.0, confidence))

    if market_state in {"TRANSITION", "UNCLEAR"}:
        next_question = "IS_MARKET_TOO_BALANCED_OR_TRANSITIONAL_TO_CLASSIFY?"
    elif pressure == "BALANCED":
        next_question = "IS_DIRECTIONAL_PRESSURE_STRONG_ENOUGH_TO_CLASSIFY_STATE?"
    else:
        next_question = "IS_THIS_STATE_STABLE_OR_TRANSITIONING?"

    evidence = [
        f"ema20_vs_ema50={ema_direction}",
        f"ema_gap_atr={ema_gap_atr:.3f}",
        f"price_slope_atr={short_slope:.3f}",
        f"structure={structure}",
        f"directional_pressure={pressure}",
        f"directional_consensus={max(raw_up, raw_down)}/3",
        f"trend_persistence={persistence:.3f}",
        f"price_efficiency_10={efficiency_10:.3f}",
        f"price_efficiency_20={efficiency_20:.3f}",
        f"recent_vs_baseline_range={range_ratio:.3f}",
        f"atr_short_long_ratio={volatility_detail['atr_short_long_ratio']:.3f}",
        f"expansion={expansion}",
        f"compression={compression}",
        f"slope_flip={slope_flip}",
        f"liquidity_event={liquidity_break}",
    ]

    reasoning = [
        f"QUESTION: {PROFESSIONAL_QUESTION}",
        f"DATA_QUALITY: valid_candles={len(valid)}; anomalies={len(data_problems)}.",
        f"VOLATILITY: {volatility_state}; short_long_atr={volatility_detail['atr_short_long_ratio']:.3f}; range_ratio={range_ratio:.3f}.",
        f"STRUCTURE: {structure}; quality={structure_quality:.2f}; pivots={structure_detail['pivot_highs'][-2:]} / {structure_detail['pivot_lows'][-2:]}.",
        f"PRESSURE: {pressure}; EMA={ema_direction}; slope={slope_direction}; structure={structure_direction}; votes={raw_up}/{raw_down}.",
        f"PERSISTENCE: {persistence:.2f}; windows={persistence_detail['windows']}.",
        f"CONFLICT_CHECK: {'; '.join(conflicts) if conflicts else 'no major unresolved conflict'}.",
        f"STATE: {market_state}; primary_behavior={'DIRECTIONAL' if trend_state != 'NONE' else 'NON_DIRECTIONAL'}.",
        f"CONFIDENCE: {confidence:.2f}; classification confidence only, never trade probability.",
        "BOUNDARY: E1 stops at market-state analysis; setup, confirmation, risk and execution remain downstream.",
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
        "reasoning_trace": reasoning,
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION,
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": market_state,
            "market_state": market_state,
            "directional_pressure": pressure,
            "trend_state": trend_state,
            "volatility_state": volatility_state,
            "structure_state": structure,
            "transition": "PRESENT" if transition else "ABSENT",
            "confidence": round(confidence, 4),
            "evidence_hierarchy": EVIDENCE_HIERARCHY,
            "trend_persistence": persistence_detail,
            "conflict_detected": bool(conflicts),
            "independent_evidence": {
                "ema_relationship": ema_direction,
                "ema_gap_atr": round(ema_gap_atr, 4),
                "price_slope_short_atr": round(short_slope, 4),
                "price_slope_long_atr": round(long_slope, 4),
                "structure": structure,
                "structure_quality": round(structure_quality, 4),
                "price_efficiency_10": round(efficiency_10, 4),
                "price_efficiency_20": round(efficiency_20, 4),
                "range_ratio": round(range_ratio, 4),
                "atr_short_long_ratio": volatility_detail["atr_short_long_ratio"],
            },
            "next_question": next_question,
        },
        "analysis_status": "COMPLETE",
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }
