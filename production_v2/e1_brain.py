from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What is the market doing right now?"
EVIDENCE_HIERARCHY = "DATA_QUALITY -> MARKET_STRUCTURE -> PRICE_BEHAVIOR -> PRESSURE -> VOLATILITY -> EMA_CONFIRMATION -> PERSISTENCE -> REGIME"


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


def _direction(value: float, threshold: float = 0.15) -> str:
    if value > threshold:
        return "UP"
    if value < -threshold:
        return "DOWN"
    return "FLAT"


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    pivot_highs, pivot_lows = _pivots(bars)
    recent_highs = pivot_highs[-6:]
    recent_lows = pivot_lows[-6:]
    hh = sum(recent_highs[i] > recent_highs[i - 1] for i in range(1, len(recent_highs)))
    lh = sum(recent_highs[i] < recent_highs[i - 1] for i in range(1, len(recent_highs)))
    hl = sum(recent_lows[i] > recent_lows[i - 1] for i in range(1, len(recent_lows)))
    ll = sum(recent_lows[i] < recent_lows[i - 1] for i in range(1, len(recent_lows)))
    bullish = min(hh, hl)
    bearish = min(lh, ll)
    if bullish >= 2 and bullish > bearish:
        state, quality = "BULLISH", min(1.0, 0.65 + 0.08 * bullish)
    elif bearish >= 2 and bearish > bullish:
        state, quality = "BEARISH", min(1.0, 0.65 + 0.08 * bearish)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.55
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.55
    else:
        state, quality = "MIXED", 0.30
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
    windows: dict[str, float] = {}
    aligned = 0
    for name, lookback, threshold in (("short", 5, 0.20), ("medium", 10, 0.30), ("long", 20, 0.45)):
        value = _slope_atr(closes, atr, lookback)
        windows[name] = round(value, 4)
        aligned += int(value >= threshold if direction == "UP" else value <= -threshold)
    return aligned / 3.0, {"aligned_windows": aligned, "windows": windows}


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
    base = {"TREND_UP": 0.58, "TREND_DOWN": 0.58, "RANGE": 0.56, "COMPRESSION": 0.62, "EXPANSION": 0.55, "TRANSITION": 0.64, "UNCLEAR": 0.28}.get(state, 0.25)
    quality = 0.22 * structure_quality + 0.20 * persistence + 0.18 * min(1.0, efficiency10 / 0.70) + 0.18 * min(1.0, efficiency20 / 0.70) + 0.10 * float(ema_confirmed) + 0.12 * data_quality
    penalty = min(0.28, 0.07 * conflicts)
    return round(max(0.0, min(0.99, base + 0.35 * quality - penalty)), 3)


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """E1 — professional Market-State Analyst only.

    E1 answers one question: "What is the market doing right now?"
    It may describe regime, direction, structure, pressure, momentum,
    volatility, persistence and conflicts. It must never decide setup,
    entry, risk, target, sizing or execution.

    The core rule is evidence reconciliation, not indicator voting:
    structure + price behaviour establish the state; EMA confirms or contradicts.
    """
    valid, data_problems = _clean_bars(bars)
    if len(valid) < 60:
        return {
            "question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL",
            "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR",
            "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0,
            "evidence": ["valid_candles_below_minimum", *data_problems[:6]], "conflicts": data_problems[:6],
            "reasoning_trace": ["QUESTION -> DATA_QUALITY -> insufficient valid candles -> classification withheld"],
            "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "thesis": "Insufficient reliable data; no regime invented.", "evidence_hierarchy": EVIDENCE_HIERARCHY},
            "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        }

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    if atr <= 0:
        return {
            "question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL",
            "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR",
            "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0,
            "evidence": ["atr_invalid"], "conflicts": ["atr_invalid"], "reasoning_trace": ["QUESTION -> DATA_QUALITY -> ATR invalid -> classification withheld"],
            "analysis_status": "INCOMPLETE", "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        }

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
    signed_eff10 = _signed_efficiency(closes, 10)
    signed_eff20 = _signed_efficiency(closes, 20)

    short_slope = _slope_atr(closes, atr, 5)
    medium_slope = _slope_atr(closes, atr, 10)
    long_slope = _slope_atr(closes, atr, 20)
    short_direction = _direction(short_slope, 0.15)
    medium_direction = _direction(medium_slope, 0.20)
    long_direction = _direction(long_slope, 0.30)
    price_dirs = [short_direction, medium_direction, long_direction]
    up_price, down_price = price_dirs.count("UP"), price_dirs.count("DOWN")

    # Price behaviour establishes pressure. Structure is the tiebreaker.
    if up_price >= 2 and up_price > down_price:
        pressure = "UP"
    elif down_price >= 2 and down_price > up_price:
        pressure = "DOWN"
    elif structure_direction in {"UP", "DOWN"}:
        pressure = structure_direction
    else:
        pressure = "BALANCED"

    persistence, persistence_detail = _persistence(closes, atr, pressure)
    ema_confirmed = (
        pressure in {"UP", "DOWN"}
        and ema_relation == pressure
        and ((pressure == "UP" and ema20_slope >= -0.05 and ema50_slope >= -0.10) or (pressure == "DOWN" and ema20_slope <= 0.05 and ema50_slope <= 0.10))
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
    if data_problems: conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict: conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structural_conflict: conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict: conflicts.append("SHORT_VS_LONG_HORIZON")
    if liquidity_event: conflicts.append("LIQUIDITY_SWEEP_OR_FAILED_BREAK")
    if pressure == "BALANCED": conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")

    # A professional transition means the market state is changing or materially
    # conflicting. EMA lag alone is never enough to label TRANSITION.
    genuine_transition = (
        (structural_conflict and persistence < 2 / 3)
        or (horizon_conflict and persistence < 1 / 3)
        or (liquidity_event and persistence < 2 / 3)
        or (structural_conflict and expansion)
    )

    strong_structure = structure_direction == pressure and structure_quality >= 0.55
    trend_confirmed = (
        pressure in {"UP", "DOWN"}
        and persistence >= 2 / 3
        and efficiency20 >= 0.25
        and strong_structure
        and abs(ema_gap) >= 0.12
        and ema_confirmed
    )

    if compression and efficiency20 < 0.45:
        market_state = "COMPRESSION"
        final_pressure = "NEUTRAL"
        reason = "volatility_compression_dominates_direction"
    elif not (pressure in {"UP", "DOWN"}) and efficiency20 < 0.35:
        market_state = "RANGE"
        final_pressure = "NEUTRAL"
        reason = "directional_efficiency_is_low"
    elif genuine_transition:
        market_state = "TRANSITION"
        final_pressure = pressure
        reason = "state_conflict_or_change_is_active"
    elif trend_confirmed:
        market_state = "TREND_UP" if pressure == "UP" else "TREND_DOWN"
        final_pressure = pressure
        reason = "structure_price_pressure_ema_persistence_aligned"
    elif expansion:
        market_state = "EXPANSION"
        final_pressure = pressure if pressure in {"UP", "DOWN"} else "BALANCED"
        reason = "volatility_expanding_without_full_trend_confirmation"
    elif pressure in {"UP", "DOWN"} and strong_structure and persistence >= 1 / 3:
        market_state = "TREND_UP" if pressure == "UP" else "TREND_DOWN"
        final_pressure = pressure
        reason = "directional_state_present_but_confirmation_is_moderate"
    else:
        market_state = "UNCLEAR"
        final_pressure = pressure if pressure in {"UP", "DOWN"} else "BALANCED"
        reason = "evidence_is_not_coherent_enough_for_named_regime"

    transition = "PRESENT" if market_state == "TRANSITION" or (market_state == "EXPANSION" and (structural_conflict or horizon_conflict)) else "ABSENT"
    trend_state = "UP" if market_state == "TREND_UP" else "DOWN" if market_state == "TREND_DOWN" else "NONE"
    pressure_label = "UP" if final_pressure == "UP" else "DOWN" if final_pressure == "DOWN" else "NEUTRAL"
    location, location_percentile = _location(closes, atr)
    data_quality = max(0.0, 1.0 - min(1.0, len(data_problems) / max(1, len(valid))))
    confidence = _confidence(market_state, structure_quality, persistence, efficiency10, efficiency20, ema_confirmed, len(conflicts), data_quality)

    direction_word = "bullish" if final_pressure == "UP" else "bearish" if final_pressure == "DOWN" else "neutral"
    if market_state == "TRANSITION":
        thesis = f"Market is in TRANSITION with {direction_word} pressure; evidence is materially conflicting or changing ({', '.join(conflicts[:3]) or 'state change'})."
    elif market_state in {"TREND_UP", "TREND_DOWN"}:
        thesis = f"Market is in {market_state}; structure, multi-horizon price behaviour and persistence align, while EMA evidence {'confirms' if ema_confirmed else 'does not materially contradict'} the state."
    elif market_state == "RANGE":
        thesis = "Market is rotational/ranging; directional efficiency is low and no persistent directional structure dominates."
    elif market_state == "COMPRESSION":
        thesis = "Market is compressed; volatility is contracting and directional movement is insufficient to establish a trend."
    elif market_state == "EXPANSION":
        thesis = f"Market is expanding in volatility with {direction_word} pressure, but full trend confirmation is not established."
    else:
        thesis = "Market evidence is mixed; E1 withholds a stronger regime label rather than forcing a trend."

    evidence = [
        f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={ema_gap:.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        f"price_slope_atr={short_slope:.3f}", f"price_medium_slope_atr={medium_slope:.3f}",
        f"price_long_slope_atr={long_slope:.3f}", f"structure={structure}",
        f"structure_quality={structure_quality:.3f}", f"directional_pressure={pressure_label}",
        f"price_consensus={max(up_price, down_price)}/3", f"trend_persistence={persistence:.3f}",
        f"price_efficiency_10={efficiency10:.3f}", f"price_efficiency_20={efficiency20:.3f}",
        f"signed_efficiency_10={signed_eff10:.3f}", f"signed_efficiency_20={signed_eff20:.3f}",
        f"recent_vs_baseline_range={range_ratio:.3f}", f"atr_short_long_ratio={volatility_detail['atr_short_long_ratio']:.3f}",
        f"location={location}", f"location_percentile={location_percentile:.3f}",
        f"ema_confirmed={ema_confirmed}", f"ema_conflict={ema_conflict}",
        f"structure_conflict={structural_conflict}", f"horizon_conflict={horizon_conflict}",
        f"sweep_high={swept_high}", f"sweep_low={swept_low}",
    ]

    reasoning_trace = [
        f"QUESTION -> {PROFESSIONAL_QUESTION}",
        f"DATA_QUALITY -> valid_candles={len(valid)} problems={len(data_problems)}",
        f"STRUCTURE -> {structure} quality={structure_quality:.2f}",
        f"PRICE_BEHAVIOR -> short={short_direction} medium={medium_direction} long={long_direction}",
        f"PRESSURE -> {pressure_label} persistence={persistence:.2f} efficiency20={efficiency20:.2f}",
        f"VOLATILITY -> {volatility_state} compression={compression} expansion={expansion}",
        f"EMA_CONFIRMATION -> relation={ema_relation} confirmed={ema_confirmed} conflict={ema_conflict}",
        f"CONFLICT_RECONCILIATION -> {', '.join(conflicts) if conflicts else 'NONE'}",
        f"REGIME -> {market_state} because={reason}",
        f"THESIS -> {thesis}",
    ]

    return {
        "question": PROFESSIONAL_QUESTION,
        "market_state": market_state,
        "directional_pressure": pressure_label,
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
            "direction": final_pressure,
            "thesis": thesis,
            "evidence_hierarchy": EVIDENCE_HIERARCHY,
            "structure_detail": structure_detail,
            "persistence_detail": persistence_detail,
            "volatility_detail": volatility_detail,
            "price_horizons": {"short": short_direction, "medium": medium_direction, "long": long_direction},
            "ema": {
                "relation": ema_relation, "gap_atr": round(ema_gap, 4),
                "ema20_slope_atr": round(ema20_slope, 4), "ema50_slope_atr": round(ema50_slope, 4),
                "confirmed": ema_confirmed, "conflict": ema_conflict,
            },
            "conflict_detected": bool(conflicts),
            "conflict_count": len(conflicts),
            "trend_confirmed": trend_confirmed,
            "classification_reason": reason,
            "data_quality": round(data_quality, 3),
        },
        "analysis_status": "COMPLETE",
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }
