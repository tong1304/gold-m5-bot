from __future__ import annotations

from statistics import mean
from typing import Any


DIRECTIONAL_STATES = {"BULLISH", "BEARISH", "BALANCED"}
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What is the market doing right now?"


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    sample = bars[-period:]
    trs: list[float] = []
    previous = None
    for bar in sample:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        trs.append(high - low if previous is None else max(high - low, abs(high - previous), abs(low - previous)))
        previous = close
    return mean(trs) if trs else 0.0


def _pivots(bars: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for index in range(2, max(2, len(bars) - 2)):
        window = bars[index - 2:index + 3]
        high = float(bars[index]["high"])
        low = float(bars[index]["low"])
        if high >= max(float(x["high"]) for x in window):
            highs.append(high)
        if low <= min(float(x["low"]) for x in window):
            lows.append(low)
    return highs[-6:], lows[-6:]


def _efficiency(closes: list[float], lookback: int = 10) -> float:
    sample = closes[-lookback:]
    if len(sample) < 2:
        return 0.0
    net = abs(sample[-1] - sample[0])
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return net / max(path, 1e-12)


def _directional_consensus(ema20: float, ema50: float, slope: float, structure: str) -> tuple[str, int, int]:
    up_votes = int(ema20 > ema50) + int(slope > 0) + int(structure == "BULLISH")
    down_votes = int(ema20 < ema50) + int(slope < 0) + int(structure == "BEARISH")
    if up_votes >= 2 and up_votes > down_votes:
        return "BULLISH", up_votes, down_votes
    if down_votes >= 2 and down_votes > up_votes:
        return "BEARISH", up_votes, down_votes
    return "BALANCED", up_votes, down_votes


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """E1 Professional Market-State Brain.

    E1 answers one question only: what is the market doing right now?
    It deliberately stops before setup, entry, risk or trade decisions.
    The reasoning follows a professional hierarchy:
    data quality -> volatility -> structure -> directional pressure -> state -> transition.
    """
    valid = [b for b in (bars or []) if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]
    if len(valid) < 30:
        return {
            "question": PROFESSIONAL_QUESTION,
            "market_state": "UNCLEAR", "directional_pressure": "BALANCED", "trend_state": "NONE",
            "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "compression": "UNKNOWN",
            "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0,
            "evidence": ["valid_candles_below_minimum"], "conflicts": [],
            "reasoning_trace": ["OBSERVE_DATA -> insufficient valid candles -> UNCLEAR"],
            "professional_reasoning": {
                "question": PROFESSIONAL_QUESTION, "market_state": "UNCLEAR",
                "directional_pressure": "BALANCED", "confidence": 0.0,
                "evidence_hierarchy": "DATA_QUALITY_FIRST",
                "next_question": "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?",
            },
            "analysis_status": "INCOMPLETE",
            "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        }

    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    slope = closes[-1] - closes[-6]
    slope_atr = abs(slope) / max(atr, 1e-12)
    ema_gap_atr = abs(ema20 - ema50) / max(atr, 1e-12)
    efficiency = _efficiency(closes, 10)

    recent_ranges = [highs[i] - lows[i] for i in range(len(valid) - 6, len(valid))]
    baseline_ranges = [highs[i] - lows[i] for i in range(max(0, len(valid) - 26), len(valid) - 6)]
    baseline = mean(baseline_ranges) if baseline_ranges else max(atr, 1e-12)
    recent = mean(recent_ranges)
    range_ratio = recent / max(baseline, 1e-12)
    compression = range_ratio < 0.70
    expansion = (highs[-1] - lows[-1]) >= 1.35 * max(baseline, 1e-12)

    pivot_highs, pivot_lows = _pivots(valid)
    hh = len(pivot_highs) >= 2 and pivot_highs[-1] > pivot_highs[-2]
    lh = len(pivot_highs) >= 2 and pivot_highs[-1] < pivot_highs[-2]
    hl = len(pivot_lows) >= 2 and pivot_lows[-1] > pivot_lows[-2]
    ll = len(pivot_lows) >= 2 and pivot_lows[-1] < pivot_lows[-2]
    structure = "BULLISH" if hh and hl else "BEARISH" if lh and ll else "MIXED"

    pressure, up_votes, down_votes = _directional_consensus(ema20, ema50, slope, structure)
    directional = pressure != "BALANCED" and slope_atr >= 0.35
    conflict = (pressure == "BULLISH" and structure == "BEARISH") or (pressure == "BEARISH" and structure == "BULLISH")

    recent_high, recent_low = max(highs[-20:-1]), min(lows[-20:-1])
    close = closes[-1]
    sweep_high = highs[-1] > recent_high and close < recent_high
    sweep_low = lows[-1] < recent_low and close > recent_low
    transition = conflict or sweep_high or sweep_low or (pressure == "BALANCED" and slope_atr >= 0.45)

    # Professional interpretation: expansion is a volatility state, not a direction.
    # Direction comes from independent structural/price evidence.
    if transition and not (directional and not conflict):
        market_state = "TRANSITION"
    elif compression and not directional:
        market_state = "COMPRESSION"
    elif expansion:
        market_state = "EXPANSION"
    elif directional and pressure == "BULLISH":
        market_state = "TREND_UP"
    elif directional and pressure == "BEARISH":
        market_state = "TREND_DOWN"
    elif range_ratio < 0.90 and not transition:
        market_state = "RANGE"
    else:
        market_state = "UNCLEAR"

    volatility_state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    trend_state = "UP" if directional and pressure == "BULLISH" else "DOWN" if directional and pressure == "BEARISH" else "NONE"
    transition_state = "PRESENT" if transition else "ABSENT"

    evidence = [
        f"ema20_vs_ema50={'UP' if ema20 > ema50 else 'DOWN' if ema20 < ema50 else 'FLAT'}",
        f"ema_gap_atr={ema_gap_atr:.3f}", f"price_slope_atr={slope_atr:.3f}",
        f"structure={structure}", f"directional_pressure={pressure}",
        f"directional_consensus={max(up_votes, down_votes)}/3",
        f"price_efficiency={efficiency:.3f}", f"recent_vs_baseline_range={range_ratio:.3f}",
        f"expansion={expansion}", f"compression={compression}",
        f"sweep_high={sweep_high}", f"sweep_low={sweep_low}",
    ]
    conflicts: list[str] = []
    if conflict:
        conflicts.append(f"directional_pressure={pressure} conflicts with structure={structure}")
    if pressure == "BALANCED":
        conflicts.append("directional evidence is balanced; no dominant pressure")
    if sweep_high or sweep_low:
        conflicts.append("liquidity sweep detected; state may be transitioning")

    # Confidence reflects agreement between independent evidence, not trade probability.
    agreement = max(up_votes, down_votes) / 3.0
    structure_quality = 1.0 if structure in {"BULLISH", "BEARISH"} else 0.55
    momentum_quality = min(1.0, slope_atr / 0.90)
    efficiency_quality = min(1.0, efficiency / 0.65)
    confidence = 0.25 + 0.25 * agreement + 0.20 * structure_quality + 0.15 * momentum_quality + 0.15 * efficiency_quality
    if conflict:
        confidence -= 0.18
    if transition:
        confidence -= 0.05
    if market_state == "UNCLEAR":
        confidence -= 0.10
    confidence = max(0.0, min(1.0, confidence))

    if market_state in {"TRANSITION", "UNCLEAR"}:
        next_question = "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?"
    elif pressure == "BALANCED":
        next_question = "IS_DIRECTIONAL_PRESSURE_STRONG_ENOUGH_TO_MATTER?"
    else:
        next_question = "IS_THIS_STATE_STABLE_OR_TRANSITIONING?"

    reasoning = [
        f"QUESTION: {PROFESSIONAL_QUESTION}",
        f"OBSERVE: volatility={volatility_state.lower()}, range_ratio={range_ratio:.3f}.",
        f"READ_STRUCTURE: {structure.lower()} structure; EMA relationship and price slope imply {pressure.lower()} pressure.",
        f"CHECK_CONFLICT: {'conflict/sweep present' if (conflict or sweep_high or sweep_low) else 'no major structural conflict'}.",
        f"CLASSIFY: market_state={market_state}; trend_state={trend_state}; transition={transition_state}.",
        f"CONFIDENCE: {confidence:.2f} based on evidence agreement, not trade probability.",
        f"BOUNDARY: E1 describes the market state only; it does not choose setup, entry, SL/TP or BUY/SELL.",
    ]
    return {
        "question": PROFESSIONAL_QUESTION,
        "market_state": market_state, "directional_pressure": pressure, "trend_state": trend_state,
        "volatility_state": volatility_state, "structure_state": structure,
        "compression": "PRESENT" if compression else "ABSENT", "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": transition_state, "confidence": round(confidence, 4), "evidence": evidence,
        "conflicts": conflicts, "reasoning_trace": reasoning, "analysis_status": "COMPLETE",
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION,
            "market_state": market_state,
            "directional_pressure": pressure,
            "trend_state": trend_state,
            "volatility_state": volatility_state,
            "structure_state": structure,
            "transition": transition_state,
            "confidence": round(confidence, 4),
            "evidence_hierarchy": "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> DIRECTIONAL_PRESSURE -> STATE -> TRANSITION",
            "independent_evidence": {
                "ema_relationship": "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT",
                "price_slope_atr": round(slope_atr, 4),
                "structure": structure,
                "price_efficiency": round(efficiency, 4),
                "range_ratio": round(range_ratio, 4),
            },
            "conflict_detected": bool(conflict or sweep_high or sweep_low),
            "next_question": next_question,
        },
        "trade_decision_authority": False, "decision_authority": "E9_ONLY",
    }
