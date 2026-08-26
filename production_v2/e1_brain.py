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


def _direction(value: float, threshold: float = 0.15) -> str:
    if value > threshold:
        return "UP"
    if value < -threshold:
        return "DOWN"
    return "FLAT"


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
    """E1 professional market-state analyst.

    E1 answers one question only: "What is the market doing right now?"
    It must first establish data quality, then volatility, structure, directional
    pressure, persistence and conflicts. It may describe a market state, but it
    has no authority over setup, entry, risk, target, sizing or execution.
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
            "reasoning_trace": ["QUESTION -> DATA_QUALITY -> insufficient valid candles -> classification withheld"],
            "professional_reasoning": {
                "question": PROFESSIONAL_QUESTION,
                "task": "DESCRIBE_MARKET_STATE_ONLY",
                "primary_state": "UNCLEAR",
                "next_question": "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?",
                "evidence_hierarchy": EVIDENCE_HIERARCHY,
                "trend_persistence": {"aligned_windows": 0, "windows": {}},
                "directional_consensus": {"confirmed": False},
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
    ema20_series = _ema_series(closes, 20)
    ema50_series = _ema_series(closes, 50)
    ema20, ema50 = ema20_series[-1], ema50_series[-1]
    ema20_slope = _slope_atr(ema20_series, atr, 5)
    ema50_slope = _slope_atr(ema50_series, atr, 5)
    ema_gap_signed = (ema20 - ema50) / max(atr, 1e-12)
    ema_gap_atr = abs(ema_gap_signed)

    structure, structure_quality, structure_detail = _structure(valid)
    volatility_state, compression, expansion, range_ratio, volatility_detail = _volatility(valid)
    efficiency_10 = _efficiency(closes, 10)
    efficiency_20 = _efficiency(closes, 20)

    ema_direction = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    short_slope = _slope_atr(closes, atr, 5)
    medium_slope = _slope_atr(closes, atr, 10)
    long_slope = _slope_atr(closes, atr, 20)
    short_direction = _direction(short_slope)
    medium_direction = _direction(medium_slope, 0.20)
    long_direction = _direction(long_slope, 0.30)
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "FLAT"

    votes = {
        "ema": ema_direction,
        "short": short_direction,
        "medium": medium_direction,
        "long": long_direction,
        "structure": structure_direction,
    }
    up_votes = sum(v == "UP" for v in votes.values())
    down_votes = sum(v == "DOWN" for v in votes.values())
    pressure = "UP" if up_votes >= 3 and up_votes > down_votes else "DOWN" if down_votes >= 3 and down_votes > up_votes else "BALANCED"

    persistence, persistence_detail = _persistence(closes, atr, pressure)
    trend_persistence_confirmed = persistence >= 2 / 3
    directional_consensus_confirmed = (
        pressure in {"UP", "DOWN"}
        and max(up_votes, down_votes) >= 4
        and trend_persistence_confirmed
    )

    # Professional state analysis gives more weight to regime-changing conflicts
    # than to a single fast move. EMA regime, structure and long horizon must not
    # silently disagree while E1 calls the market a confirmed trend.
    directional_structure_conflict = (
        ema_direction in {"UP", "DOWN"}
        and structure_direction in {"UP", "DOWN"}
        and ema_direction != structure_direction
    )
    horizon_conflict = (
        long_direction in {"UP", "DOWN"}
        and short_direction in {"UP", "DOWN"}
        and long_direction != short_direction
    )
    ema_slope_conflict = (
        ema_direction in {"UP", "DOWN"}
        and ((ema_direction == "UP" and (ema20_slope < -0.10 or ema50_slope < -0.10))
             or (ema_direction == "DOWN" and (ema20_slope > 0.10 or ema50_slope > 0.10)))
    )

    # A failed break/sweep is state information, not an entry trigger. It matters
    # because it can mark a transition even when the older trend remains intact.
    prior_high = max(highs[-21:-1])
    prior_low = min(lows[-21:-1])
    swept_high = highs[-1] > prior_high and closes[-1] < prior_high
    swept_low = lows[-1] < prior_low and closes[-1] > prior_low
    liquidity_event = swept_high or swept_low

    transition_reasons: list[str] = []
    if directional_structure_conflict:
        transition_reasons.append("directional_structure_conflict")
    if horizon_conflict:
        transition_reasons.append("short_long_horizon_conflict")
    if ema_slope_conflict:
        transition_reasons.append("ema_slope_conflict")
    if liquidity_event:
        transition_reasons.append("liquidity_sweep_or_failed_break")

    # Do not label a market TREND_UP/DOWN merely because price moved quickly.
    # A confirmed trend needs multi-horizon consensus and persistence. A meaningful
    # disagreement between regime-level evidence is explicitly classified as TRANSITION.
    transition = bool(transition_reasons)
    strong_direction = directional_consensus_confirmed and not directional_structure_conflict and not ema_slope_conflict
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
    elif range_quality >= 0.55 and balanced_behavior:
        market_state = "RANGE"
    elif expansion:
        market_state = "EXPANSION"
    else:
        market_state = "UNCLEAR"

    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"

    conflicts: list[str] = []
    if data_problems:
        conflicts.append("data_quality_anomalies_present")
    conflicts.extend(transition_reasons)
    if pressure == "BALANCED":
        conflicts.append("directional_pressure_is_balanced")

    agreement = max(up_votes, down_votes) / 5.0
    persistence_quality = persistence
    state_quality = {
        "TREND_UP": 0.94,
        "TREND_DOWN": 0.94,
        "RANGE": 0.80,
        "COMPRESSION": 0.82,
        "EXPANSION": 0.72,
        "TRANSITION": 0.58,
        "UNCLEAR": 0.35,
    }[market_state]
    conflict_penalty = min(0.28, 0.08 * len(conflicts))
    confidence = (
        0.22 * agreement
        + 0.18 * structure_quality
        + 0.22 * persistence_quality
        + 0.13 * min(1.0, ema_gap_atr)
        + 0.15 * min(1.0, efficiency_20 / 0.65)
        + 0.10 * state_quality
        - conflict_penalty
    )
    if data_problems:
        confidence -= 0.08
    if market_state == "TRANSITION":
        confidence = min(confidence, 0.72)
    confidence = max(0.0, min(1.0, confidence))

    if market_state == "TRANSITION":
        next_question = "WHICH_SIDE_IS_GAINING_CONTROL_AFTER_THE_TRANSITION?"
    elif market_state == "RANGE":
        next_question = "IS_PRICE_ACCEPTING_OR_REJECTING_THE_RANGE_BOUNDARIES?"
    elif market_state == "COMPRESSION":
        next_question = "IS_COMPRESSION_BUILDING_TOWARD_EXPANSION_OR_REMAINING_BALANCED?"
    elif market_state in {"TREND_UP", "TREND_DOWN"}:
        next_question = "IS_THE_ESTABLISHED_DIRECTION_PERSISTING_WITHOUT_STRUCTURAL_BREAK?"
    elif market_state == "EXPANSION":
        next_question = "IS_EXPANSION_DIRECTIONAL_OR_TWO_SIDED?"
    else:
        next_question = "IS_THERE_ENOUGH_INDEPENDENT_EVIDENCE_TO_CLASSIFY_THE_REGIME?"

    evidence = [
        f"ema20_vs_ema50={ema_direction}",
        f"ema_gap_atr={ema_gap_atr:.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}",
        f"ema50_slope_atr={ema50_slope:.3f}",
        f"price_slope_atr={short_slope:.3f}",
        f"structure={structure}",
        f"directional_pressure={pressure}",
        f"directional_consensus={max(up_votes, down_votes)}/5",
        f"trend_persistence={persistence:.3f}",
        f"price_efficiency_10={efficiency_10:.3f}",
        f"price_efficiency_20={efficiency_20:.3f}",
        f"recent_vs_baseline_range={range_ratio:.3f}",
        f"atr_short_long_ratio={volatility_detail['atr_short_long_ratio']:.3f}",
        f"expansion={expansion}",
        f"compression={compression}",
        f"transition={transition}",
        f"liquidity_event={liquidity_event}",
    ]

    reasoning = [
        f"QUESTION: {PROFESSIONAL_QUESTION}",
        f"DATA_QUALITY: valid_candles={len(valid)}; anomalies={len(data_problems)}.",
        f"VOLATILITY: {volatility_state}; short_long_atr={volatility_detail['atr_short_long_ratio']:.3f}; range_ratio={range_ratio:.3f}.",
        f"STRUCTURE: {structure}; quality={structure_quality:.2f}; HH={structure_detail['higher_highs']}; LH={structure_detail['lower_highs']}; HL={structure_detail['higher_lows']}; LL={structure_detail['lower_lows']}.",
        f"PRESSURE: {pressure}; votes={up_votes}UP/{down_votes}DOWN; EMA={ema_direction}; structure={structure_direction}.",
        f"PERSISTENCE: {persistence:.2f}; windows={persistence_detail['windows']}; confirmed={trend_persistence_confirmed}.",
        f"CONSENSUS: {votes}; confirmed={directional_consensus_confirmed}.",
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
            "directional_consensus": {
                "ema": ema_direction,
                "short": short_direction,
                "medium": medium_direction,
                "long": long_direction,
                "structure": structure_direction,
                "up_votes": up_votes,
                "down_votes": down_votes,
                "confirmed": directional_consensus_confirmed,
            },
            "conflict_detected": bool(conflicts),
            "independent_evidence": {
                "ema_relationship": ema_direction,
                "ema_gap_atr": round(ema_gap_atr, 4),
                "ema20_slope_atr": round(ema20_slope, 4),
                "ema50_slope_atr": round(ema50_slope, 4),
                "price_slope_short_atr": round(short_slope, 4),
                "price_slope_medium_atr": round(medium_slope, 4),
                "price_slope_long_atr": round(long_slope, 4),
                "structure": structure,
                "structure_quality": round(structure_quality, 4),
                "price_efficiency_10": round(efficiency_10, 4),
                "price_efficiency_20": round(efficiency_20, 4),
                "range_ratio": round(range_ratio, 4),
                "atr_short_long_ratio": volatility_detail["atr_short_long_ratio"],
                "liquidity_event": liquidity_event,
            },
            "next_question": next_question,
        },
        "analysis_status": "COMPLETE",
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }
