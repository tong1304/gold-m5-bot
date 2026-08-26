from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What is the market doing right now?"
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRICE_DIRECTION -> EMA_CONFIRMATION -> PERSISTENCE -> REGIME"


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
    net = abs(sample[-1] - sample[0])
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return net / max(path, 1e-12)


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


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    pivot_highs, pivot_lows = _pivots(bars)
    recent_highs = pivot_highs[-5:]
    recent_lows = pivot_lows[-5:]
    hh = sum(recent_highs[i] > recent_highs[i - 1] for i in range(1, len(recent_highs)))
    lh = sum(recent_highs[i] < recent_highs[i - 1] for i in range(1, len(recent_highs)))
    hl = sum(recent_lows[i] > recent_lows[i - 1] for i in range(1, len(recent_lows)))
    ll = sum(recent_lows[i] < recent_lows[i - 1] for i in range(1, len(recent_lows)))
    bullish = min(hh, hl)
    bearish = min(lh, ll)
    if bullish >= 2 and bullish > bearish:
        state, quality = "BULLISH", min(1.0, 0.65 + 0.10 * bullish)
    elif bearish >= 2 and bearish > bullish:
        state, quality = "BEARISH", min(1.0, 0.65 + 0.10 * bearish)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.55
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.55
    else:
        state, quality = "MIXED", 0.30
    return state, quality, {"pivot_highs": recent_highs, "pivot_lows": recent_lows, "higher_highs": hh, "lower_highs": lh, "higher_lows": hl, "lower_lows": ll}


def _persistence(closes: list[float], atr: float, direction: str) -> tuple[float, dict[str, Any]]:
    if direction not in {"UP", "DOWN"}:
        return 0.0, {"aligned_windows": 0, "windows": {}}
    windows: dict[str, float] = {}
    aligned = 0
    for name, lookback, threshold in (("short", 5, 0.20), ("medium", 10, 0.30), ("long", 20, 0.45)):
        value = _slope_atr(closes, atr, lookback)
        windows[name] = round(value, 4)
        aligned += int(value >= threshold if direction == "UP" else value <= -threshold)
    return aligned / 3.0, {"aligned_windows": aligned, "windows": windows}


def _range_quality(bars: list[dict[str, Any]], atr: float, efficiency: float) -> tuple[float, dict[str, Any]]:
    closes = [float(b["close"]) for b in bars]
    sample = closes[-20:]
    if not sample or atr <= 0:
        return 0.0, {"channel_width_atr": 0.0, "efficiency": efficiency}
    width = (max(sample) - min(sample)) / atr
    width_quality = max(0.0, min(1.0, 1.0 - max(0.0, width - 5.0) / 5.0))
    chop_quality = max(0.0, min(1.0, (0.50 - efficiency) / 0.50))
    return 0.5 * width_quality + 0.5 * chop_quality, {"channel_width_atr": round(width, 4), "efficiency": round(efficiency, 4)}


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


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """E1: professional market-state reasoning only.

    Decision order is deliberately hierarchical. Price structure and persistent
    price behaviour establish the thesis; EMAs confirm or contradict it. A single
    EMA relationship is never allowed to create a regime by itself. E1 has no
    authority over setup, entry, risk, target, sizing or execution.
    """
    valid, data_problems = _clean_bars(bars)
    if len(valid) < 60:
        return {
            "question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "BALANCED",
            "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR",
            "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0,
            "evidence": ["valid_candles_below_minimum", *data_problems[:6]], "conflicts": data_problems[:6],
            "reasoning_trace": ["QUESTION -> DATA_QUALITY -> insufficient valid candles -> classification withheld"],
            "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "evidence_hierarchy": EVIDENCE_HIERARCHY, "conflict_detected": bool(data_problems)},
            "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        }

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    if atr <= 0:
        return {"question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "BALANCED", "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0, "evidence": ["atr_invalid"], "conflicts": ["atr_invalid"], "reasoning_trace": ["QUESTION -> DATA_QUALITY -> ATR invalid -> classification withheld"], "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY"}

    ema20s = _ema_series(closes, 20)
    ema50s = _ema_series(closes, 50)
    ema20, ema50 = ema20s[-1], ema50s[-1]
    ema_relation = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    ema20_slope = _slope_atr(ema20s, atr, 5)
    ema50_slope = _slope_atr(ema50s, atr, 5)
    ema_gap = (ema20 - ema50) / atr

    structure, structure_quality, structure_detail = _structure(valid)
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "FLAT"
    volatility_state, compression, expansion, range_ratio, volatility_detail = _volatility(valid)
    efficiency10 = _efficiency(closes, 10)
    efficiency20 = _efficiency(closes, 20)

    short_slope = _slope_atr(closes, atr, 5)
    medium_slope = _slope_atr(closes, atr, 10)
    long_slope = _slope_atr(closes, atr, 20)
    short_direction = _direction(short_slope)
    medium_direction = _direction(medium_slope, 0.20)
    long_direction = _direction(long_slope, 0.30)

    # Professional directional reasoning: structure + multi-horizon price action
    # are primary. EMA is confirmation, not a vote equal to price structure.
    price_dirs = [short_direction, medium_direction, long_direction]
    up_price = price_dirs.count("UP")
    down_price = price_dirs.count("DOWN")
    if up_price >= 2 and up_price > down_price:
        pressure = "UP"
    elif down_price >= 2 and down_price > up_price:
        pressure = "DOWN"
    elif structure_direction in {"UP", "DOWN"} and structure_direction != ("UP" if up_price > down_price else "DOWN" if down_price > up_price else "FLAT"):
        pressure = structure_direction
    else:
        pressure = "BALANCED"

    persistence, persistence_detail = _persistence(closes, atr, pressure)
    price_consensus = max(up_price, down_price) >= 2 and persistence >= 2 / 3
    structure_aligned = structure_direction == pressure and structure_direction in {"UP", "DOWN"}
    ema_confirmed = (
        pressure in {"UP", "DOWN"}
        and ema_relation == pressure
        and ((pressure == "UP" and ema20_slope > -0.10) or (pressure == "DOWN" and ema20_slope < 0.10))
    )
    ema_conflict = pressure in {"UP", "DOWN"} and ema_relation in {"UP", "DOWN"} and ema_relation != pressure
    structural_conflict = pressure in {"UP", "DOWN"} and structure_direction in {"UP", "DOWN"} and structure_direction != pressure
    horizon_conflict = short_direction in {"UP", "DOWN"} and long_direction in {"UP", "DOWN"} and short_direction != long_direction

    prior_high = max(highs[-21:-1])
    prior_low = min(lows[-21:-1])
    swept_high = highs[-1] > prior_high and closes[-1] < prior_high
    swept_low = lows[-1] < prior_low and closes[-1] > prior_low
    liquidity_event = swept_high or swept_low

    conflicts: list[str] = []
    if data_problems: conflicts.append("data_quality_anomalies_present")
    if ema_conflict: conflicts.append("ema_confirmation_conflict")
    if structural_conflict: conflicts.append("structure_price_conflict")
    if horizon_conflict: conflicts.append("short_long_price_conflict")
    if liquidity_event: conflicts.append("liquidity_sweep_or_failed_break")
    if pressure == "BALANCED": conflicts.append("directional_pressure_balanced")

    # Transition is reserved for a genuine state change: structural disagreement,
    # persistent multi-horizon disagreement, or a liquidity event combined with
    # weakening directional persistence. A mere EMA lag is NOT transition.
    genuine_transition = (
        (structural_conflict and horizon_conflict)
        or (structural_conflict and persistence < 2 / 3)
        or (liquidity_event and persistence < 2 / 3)
        or (horizon_conflict and persistence < 1 / 3)
    )

    trend_confirmed = (
        pressure in {"UP", "DOWN"}
        and price_consensus
        and structure_aligned
        and persistence >= 2 / 3
        and not genuine_transition
    )

    range_quality, range_detail = _range_quality(valid, atr, efficiency20)
    balanced = pressure == "BALANCED" or persistence < 1 / 3

    if compression and not trend_confirmed:
        market_state = "COMPRESSION"
    elif trend_confirmed:
        market_state = "TREND_UP" if pressure == "UP" else "TREND_DOWN"
    elif genuine_transition:
        market_state = "TRANSITION"
    elif expansion and not trend_confirmed:
        market_state = "EXPANSION"
    elif range_quality >= 0.55 and balanced:
        market_state = "RANGE"
    else:
        market_state = "UNCLEAR"

    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"

    agreement = max(up_price, down_price) / 3.0
    confidence = (
        0.30 * structure_quality
        + 0.28 * persistence
        + 0.22 * agreement
        + 0.10 * min(1.0, abs(ema_gap) / 0.80)
        + 0.10 * min(1.0, efficiency20 / 0.65)
    )
    if market_state == "TRANSITION": confidence = min(confidence, 0.72)
    if market_state == "RANGE": confidence = min(confidence, 0.82)
    confidence -= min(0.20, 0.04 * len(conflicts))
    confidence = max(0.0, min(1.0, confidence))

    if market_state in {"TREND_UP", "TREND_DOWN"}:
        next_question = "IS_THE_ESTABLISHED_DIRECTION_PERSISTING_OR_BEING_STRUCTURALLY_REJECTED?"
    elif market_state == "TRANSITION":
        next_question = "WHICH_SIDE_IS_GAINING_STRUCTURAL_CONTROL?"
    elif market_state == "RANGE":
        next_question = "IS_PRICE_REJECTING_OR_ACCEPTING_THE_RANGE_BOUNDARIES?"
    elif market_state == "COMPRESSION":
        next_question = "IS_COMPRESSION_BUILDING_TOWARD_DIRECTIONAL_EXPANSION?"
    elif market_state == "EXPANSION":
        next_question = "IS_EXPANSION_DIRECTIONAL_AND_PERSISTENT_OR_TWO_SIDED?"
    else:
        next_question = "IS_THERE_ENOUGH_INDEPENDENT_EVIDENCE_TO_CLASSIFY_THE_REGIME?"

    evidence = [
        f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={abs(ema_gap):.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"price_slope_atr={short_slope:.3f}", f"price_medium_slope_atr={medium_slope:.3f}",
        f"price_long_slope_atr={long_slope:.3f}", f"structure={structure}",
        f"directional_pressure={pressure}", f"price_consensus={max(up_price, down_price)}/3",
        f"trend_persistence={persistence:.3f}", f"price_efficiency_10={efficiency10:.3f}",
        f"price_efficiency_20={efficiency20:.3f}", f"recent_vs_baseline_range={range_ratio:.3f}",
        f"atr_short_long_ratio={volatility_detail['atr_short_long_ratio']:.3f}",
        f"expansion={expansion}", f"compression={compression}", f"ema_confirmed={ema_confirmed}",
        f"genuine_transition={genuine_transition}", f"liquidity_event={liquidity_event}",
    ]

    reasoning = [
        f"QUESTION: {PROFESSIONAL_QUESTION}",
        f"DATA_QUALITY: valid_candles={len(valid)}; anomalies={len(data_problems)}.",
        f"VOLATILITY: {volatility_state}; ATR_ratio={volatility_detail['atr_short_long_ratio']:.3f}; range_ratio={range_ratio:.3f}.",
        f"STRUCTURE_PRIMARY: {structure}; quality={structure_quality:.2f}; HH={structure_detail['higher_highs']}; LH={structure_detail['lower_highs']}; HL={structure_detail['higher_lows']}; LL={structure_detail['lower_lows']}.",
        f"PRICE_BEHAVIOUR: short={short_direction}; medium={medium_direction}; long={long_direction}; persistence={persistence:.2f}.",
        f"DIRECTIONAL_THESIS: {pressure}; price_consensus={max(up_price, down_price)}/3; structure_aligned={structure_aligned}.",
        f"EMA_CONFIRMATION: relation={ema_relation}; confirmed={ema_confirmed}; conflict={ema_conflict}. EMA is confirmation, not the primary thesis.",
        f"CONFLICT_RESOLUTION: structural={structural_conflict}; horizon={horizon_conflict}; liquidity={liquidity_event}; genuine_transition={genuine_transition}.",
        f"REGIME: {market_state}; trend_state={trend_state}.",
        f"CONFIDENCE: {confidence:.2f}; classification confidence only, never trade probability.",
        "BOUNDARY: E1 stops at market-state analysis; setup, trigger, risk and execution remain downstream.",
    ]

    return {
        "question": PROFESSIONAL_QUESTION, "market_state": market_state, "directional_pressure": pressure,
        "trend_state": trend_state, "volatility_state": volatility_state, "structure_state": structure,
        "compression": "PRESENT" if compression else "ABSENT", "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": "PRESENT" if genuine_transition else "ABSENT", "confidence": round(confidence, 4),
        "evidence": evidence, "conflicts": conflicts, "reasoning_trace": reasoning,
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": market_state,
            "market_state": market_state, "directional_pressure": pressure, "trend_state": trend_state,
            "volatility_state": volatility_state, "structure_state": structure, "transition": "PRESENT" if genuine_transition else "ABSENT",
            "confidence": round(confidence, 4), "evidence_hierarchy": EVIDENCE_HIERARCHY,
            "trend_persistence": persistence_detail,
            "directional_consensus": {"short": short_direction, "medium": medium_direction, "long": long_direction, "structure": structure_direction, "up_votes": up_price, "down_votes": down_price, "confirmed": price_consensus},
            "ema_confirmation": {"relationship": ema_relation, "gap_atr": round(abs(ema_gap), 4), "confirmed": ema_confirmed, "conflict": ema_conflict},
            "conflict_resolution": {"structural_conflict": structural_conflict, "horizon_conflict": horizon_conflict, "liquidity_event": liquidity_event, "genuine_transition": genuine_transition},
            "independent_evidence": {"ema20_slope_atr": round(ema20_slope, 4), "ema50_slope_atr": round(ema50_slope, 4), "price_slope_short_atr": round(short_slope, 4), "price_slope_medium_atr": round(medium_slope, 4), "price_slope_long_atr": round(long_slope, 4), "structure": structure, "structure_quality": round(structure_quality, 4), "price_efficiency_10": round(efficiency10, 4), "price_efficiency_20": round(efficiency20, 4), "range_ratio": round(range_ratio, 4), "atr_short_long_ratio": volatility_detail["atr_short_long_ratio"], "liquidity_event": liquidity_event},
            "next_question": next_question,
        },
        "analysis_status": "COMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
    }
