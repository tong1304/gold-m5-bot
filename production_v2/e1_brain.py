from __future__ import annotations

from statistics import mean
from typing import Any


DIRECTIONAL_STATES = {"BULLISH", "BEARISH", "BALANCED"}
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}


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


def analyze_e1(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Professional market-state synthesis for E1 only.

    E1 describes the market. It never creates a trade decision or execution gate.
    """
    valid = [b for b in (bars or []) if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]
    if len(valid) < 30:
        return {
            "market_state": "UNCLEAR",
            "directional_pressure": "BALANCED",
            "trend_state": "NONE",
            "volatility_state": "UNKNOWN",
            "structure_state": "UNCLEAR",
            "compression": "UNKNOWN",
            "expansion": "UNKNOWN",
            "transition": "UNKNOWN",
            "confidence": 0.0,
            "evidence": ["valid_candles_below_minimum"],
            "conflicts": [],
            "reasoning_trace": ["INSUFFICIENT_DATA -> UNCLEAR"],
            "analysis_status": "INCOMPLETE",
            "trade_decision_authority": False,
            "decision_authority": "E9_ONLY",
        }

    opens = [float(b["open"]) for b in valid]
    highs = [float(b["high"]) for b in valid]
    lows = [float(b["low"]) for b in valid]
    closes = [float(b["close"]) for b in valid]
    atr = _atr(valid)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    slope = closes[-1] - closes[-6]
    slope_atr = abs(slope) / max(atr, 1e-12)

    recent_ranges = [highs[i] - lows[i] for i in range(max(0, len(valid) - 6), len(valid))]
    baseline_ranges = [highs[i] - lows[i] for i in range(max(0, len(valid) - 26), len(valid) - 6)]
    baseline = mean(baseline_ranges) if baseline_ranges else max(atr, 1e-12)
    recent = mean(recent_ranges) if recent_ranges else 0.0
    compression = recent < 0.70 * max(baseline, 1e-12)
    expansion = (highs[-1] - lows[-1]) >= 1.35 * max(baseline, 1e-12)

    pivot_highs, pivot_lows = _pivots(valid)
    hh = len(pivot_highs) >= 2 and pivot_highs[-1] > pivot_highs[-2]
    lh = len(pivot_highs) >= 2 and pivot_highs[-1] < pivot_highs[-2]
    hl = len(pivot_lows) >= 2 and pivot_lows[-1] > pivot_lows[-2]
    ll = len(pivot_lows) >= 2 and pivot_lows[-1] < pivot_lows[-2]
    structure = "BULLISH" if hh and hl else "BEARISH" if lh and ll else "MIXED"

    up_votes = int(ema20 > ema50) + int(slope > 0) + int(closes[-1] >= ema20) + int(structure == "BULLISH")
    down_votes = int(ema20 < ema50) + int(slope < 0) + int(closes[-1] <= ema20) + int(structure == "BEARISH")
    if up_votes >= 3 and up_votes > down_votes:
        pressure = "BULLISH"
    elif down_votes >= 3 and down_votes > up_votes:
        pressure = "BEARISH"
    else:
        pressure = "BALANCED"

    aligned_up = pressure == "BULLISH" and structure in {"BULLISH", "MIXED"} and slope_atr >= 0.45
    aligned_down = pressure == "BEARISH" and structure in {"BEARISH", "MIXED"} and slope_atr >= 0.45
    directional = aligned_up or aligned_down
    conflict = (pressure == "BULLISH" and structure == "BEARISH") or (pressure == "BEARISH" and structure == "BULLISH")

    recent_high = max(highs[-20:-1])
    recent_low = min(lows[-20:-1])
    close = closes[-1]
    sweep_high = highs[-1] > recent_high and close < recent_high
    sweep_low = lows[-1] < recent_low and close > recent_low
    transition = conflict or sweep_high or sweep_low or (pressure == "BALANCED" and slope_atr >= 0.45)

    if expansion:
        market_state = "EXPANSION"
    elif compression and not directional:
        market_state = "COMPRESSION"
    elif transition and not directional:
        market_state = "TRANSITION"
    elif directional and pressure == "BULLISH":
        market_state = "TREND_UP"
    elif directional and pressure == "BEARISH":
        market_state = "TREND_DOWN"
    elif not directional and (recent / max(baseline, 1e-12)) < 0.90:
        market_state = "RANGE"
    else:
        market_state = "UNCLEAR"

    volatility_state = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    trend_state = "UP" if aligned_up else "DOWN" if aligned_down else "NONE"
    transition_state = "PRESENT" if transition else "ABSENT"

    evidence = [
        f"ema20_vs_ema50={'UP' if ema20 > ema50 else 'DOWN' if ema20 < ema50 else 'FLAT'}",
        f"price_slope_atr={slope_atr:.3f}",
        f"structure={structure}",
        f"directional_pressure={pressure}",
        f"recent_vs_baseline_range={recent / max(baseline, 1e-12):.3f}",
        f"expansion={expansion}",
        f"compression={compression}
",
        f"sweep_high={sweep_high}",
        f"sweep_low={sweep_low}",
    ]
    conflicts: list[str] = []
    if conflict:
        conflicts.append(f"directional_pressure={pressure} conflicts with structure={structure}")
    if market_state == "UNCLEAR":
        conflicts.append("no dominant state has sufficient independent evidence")

    agreement = max(up_votes, down_votes) / 4.0
    confidence = 0.45 + 0.45 * agreement
    if market_state in {"TRANSITION", "UNCLEAR"}:
        confidence -= 0.10 if conflicts else 0.0
    if len(valid) < 50:
        confidence -= 0.03
    confidence = max(0.0, min(1.0, confidence))

    reasoning = [
        f"OBSERVATION: EMA20/EMA50 and recent price slope imply {pressure.lower()} pressure.",
        f"INTERPRETATION: structure is {structure.lower()} and {'aligned' if not conflict else 'conflicted'} with directional pressure.",
        f"VOLATILITY: {'expansion' if expansion else 'compression' if compression else 'normal volatility'}.",
        f"TRANSITION: {'present' if transition else 'not dominant'}.",
        f"CONCLUSION: market_state={market_state}; directional_pressure={pressure}; confidence={confidence:.2f}.",
        "BOUNDARY: E1 describes market state only; E9 retains trade-decision authority.",
    ]

    return {
        "market_state": market_state,
        "directional_pressure": pressure,
        "trend_state": trend_state,
        "volatility_state": volatility_state,
        "structure_state": structure,
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": transition_state,
        "confidence": round(confidence, 4),
        "evidence": evidence,
        "conflicts": conflicts,
        "reasoning_trace": reasoning,
        "analysis_status": "COMPLETE",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
    }
