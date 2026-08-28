"""E1 Professional Market-State Brain V7.

V7 separates the dominant market regime from current phase, directional
pressure and volatility. A short counter-move no longer downgrades a strong
trend context to UNCLEAR when EMA context and market structure remain aligned.
E1 remains strictly market-state only.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from .e1_professional_layer_v6 import analyze_e1_professional_v6

STRONG_EMA_GAP_ATR = 0.75
LONG_SLOPE_ATR = 0.35
PHASE_SLOPE_ATR = 0.20


def _direction(value: Any) -> str:
    value = str(value or "").upper()
    if value in {"UP", "BULLISH"}:
        return "UP"
    if value in {"DOWN", "BEARISH"}:
        return "DOWN"
    return "NEUTRAL"


def _opposite(direction: str) -> str:
    return "DOWN" if direction == "UP" else "UP" if direction == "DOWN" else "NEUTRAL"


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1.0 - alpha) * value
    return value


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    sample = bars[-period:]
    if not sample:
        return 0.0
    trs: list[float] = []
    prev = None
    for bar in sample:
        h, l, c = float(bar["high"]), float(bar["low"]), float(bar["close"])
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return mean(trs) if trs else 0.0


def _slope(closes: list[float], atr: float, bars: int) -> float:
    if atr <= 0 or len(closes) <= bars:
        return 0.0
    return (closes[-1] - closes[-1 - bars]) / atr


def _structure_direction(bars: list[dict[str, Any]], wing: int = 2) -> str:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        hi, lo = float(bars[i]["high"]), float(bars[i]["low"])
        if hi >= max(float(x["high"]) for x in window):
            highs.append(hi)
        if lo <= min(float(x["low"]) for x in window):
            lows.append(lo)
    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    if min(hh, hl) >= 2 and min(hh, hl) > min(lh, ll):
        return "UP"
    if min(lh, ll) >= 2 and min(lh, ll) > min(hh, hl):
        return "DOWN"
    return "NEUTRAL"


def _dominant_direction(
    *,
    ema_direction: str,
    structure_direction: str,
    slope20: float,
    slope40: float,
    ema_gap_atr: float,
) -> tuple[str, str]:
    """Choose dominant direction without allowing the latest candles to vote alone."""
    ema = _direction(ema_direction)
    structure = _direction(structure_direction)
    gap = float(ema_gap_atr or 0.0)

    if ema in {"UP", "DOWN"} and structure == ema:
        return ema, "STRUCTURE_EMA_ALIGNMENT"

    long_dir = (
        "UP" if slope20 >= LONG_SLOPE_ATR and slope40 >= LONG_SLOPE_ATR
        else "DOWN" if slope20 <= -LONG_SLOPE_ATR and slope40 <= -LONG_SLOPE_ATR
        else "NEUTRAL"
    )
    if ema == long_dir and abs(gap) >= STRONG_EMA_GAP_ATR:
        return ema, "EMA_LONG_HORIZON_ALIGNMENT"
    return "NEUTRAL", "NO_DOMINANT_DIRECTION"


def _phase(bars: list[dict[str, Any]], dominant: str, atr: float) -> tuple[str, str]:
    """Describe current phase without changing the dominant regime."""
    if dominant not in {"UP", "DOWN"} or atr <= 0 or len(bars) < 5:
        return "UNRESOLVED", "NO_DOMINANT_TREND"
    sample = bars[-5:]
    closes = [float(b["close"]) for b in sample if isinstance(b, dict) and "close" in b]
    bodies: list[str] = []
    for b in sample:
        try:
            o, c = float(b["open"]), float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        bodies.append("UP" if c > o else "DOWN" if c < o else "FLAT")
    if len(closes) < 2:
        return "UNRESOLVED", "INSUFFICIENT_RECENT_CANDLES"
    recent_slope = (closes[-1] - closes[0]) / atr
    aligned = recent_slope if dominant == "UP" else -recent_slope
    opposite_count = sum(x == _opposite(dominant) for x in bodies)
    dominant_count = sum(x == dominant for x in bodies)
    if aligned >= PHASE_SLOPE_ATR:
        return ("REACCELERATION" if dominant_count < opposite_count else "IMPULSE"), "RECENT_PRESSURE_ALIGNS_WITH_TREND"
    if aligned <= -PHASE_SLOPE_ATR:
        return "PULLBACK", "RECENT_PRESSURE_COUNTERS_DOMINANT_TREND"
    return "CONSOLIDATION", "RECENT_PRESSURE_BALANCED"


def analyze_e1_professional_v7(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V7: state, phase, dominant direction and current pressure are separate facts."""
    output = dict(analyze_e1_professional_v6(bars))
    if output.get("analysis_status") == "INCOMPLETE":
        return output

    clean = [b for b in (bars or []) if isinstance(b, dict)]
    pr = dict(output.get("professional_reasoning") or {})
    closes = [float(b["close"]) for b in clean if "close" in b]
    atr = _atr(clean)
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    ema_gap = (ema20 - ema50) / max(atr, 1e-12)
    ema_direction = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "NEUTRAL"
    structure_direction = _structure_direction(clean)
    slope20, slope40 = _slope(closes, atr, 20), _slope(closes, atr, 40)

    dominant, dominant_basis = _dominant_direction(
        ema_direction=ema_direction,
        structure_direction=structure_direction,
        slope20=slope20,
        slope40=slope40,
        ema_gap_atr=ema_gap,
    )
    phase, phase_basis = _phase(clean, dominant, atr)
    previous_state = str(output.get("market_state") or "UNCLEAR").upper()

    if dominant == "UP":
        market_state, trend_state = "TREND_UP", "UP"
    elif dominant == "DOWN":
        market_state, trend_state = "TREND_DOWN", "DOWN"
    else:
        market_state = previous_state if previous_state in {"RANGE", "COMPRESSION", "EXPANSION", "TRANSITION"} else "UNCLEAR"
        trend_state = "NONE"

    current_pressure = (
        "BULLISH" if phase == "PULLBACK" and dominant == "DOWN"
        else "BEARISH" if phase == "PULLBACK" and dominant == "UP"
        else "BULLISH" if dominant == "UP"
        else "BEARISH" if dominant == "DOWN"
        else "NEUTRAL"
    )
    counter_pressure = "PULLBACK_WITHIN_TREND" if phase == "PULLBACK" else "NONE"
    transition = "ABSENT" if dominant in {"UP", "DOWN"} else str(output.get("transition") or "ABSENT")

    # E2 consumes directional_pressure as the dominant market direction. Keep
    # current candle pressure in its own field so a pullback cannot masquerade
    # as a regime reversal to downstream engines.
    output.update({
        "market_state": market_state,
        "trend_state": trend_state,
        "directional_state": "CONFIRMED" if dominant in {"UP", "DOWN"} else output.get("directional_state", "UNRESOLVED"),
        "directional_state_v7": dominant,
        "dominant_direction": dominant,
        "market_phase": phase,
        "directional_pressure": dominant,
        "current_pressure": current_pressure,
        "counter_pressure": counter_pressure,
        "transition": transition,
        "transition_committed": False if dominant in {"UP", "DOWN"} and transition == "ABSENT" else bool(output.get("transition_committed")),
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V7",
        "e1_trade_authority": False,
        "trade_decision_authority": False,
    })

    thesis = dict(pr.get("primary_thesis") or {})
    thesis.update({
        "direction": dominant,
        "market_state": market_state,
        "phase": phase,
        "status": "CONFIRMED" if dominant in {"UP", "DOWN"} else thesis.get("status", "UNRESOLVED"),
    })
    if counter_pressure == "PULLBACK_WITHIN_TREND":
        thesis["counter_evidence"] = list(dict.fromkeys(list(thesis.get("counter_evidence") or []) + ["COUNTER_PRESSURE_CLASSIFIED_AS_PULLBACK_NOT_REVERSAL"]))

    state_machine = dict(pr.get("state_machine") or {})
    state_machine.update({
        "version": "V7",
        "market_state_before_v7": previous_state,
        "market_state_after_v7": market_state,
        "dominant_direction": dominant,
        "dominant_direction_basis": dominant_basis,
        "market_phase": phase,
        "phase_basis": phase_basis,
        "current_pressure": current_pressure,
        "counter_pressure": counter_pressure,
        "ema_direction": ema_direction,
        "structure_direction": structure_direction,
        "ema_gap_atr": round(ema_gap, 3),
        "slope20_atr": round(slope20, 3),
        "slope40_atr": round(slope40, 3),
        "rule": "Market state is determined by dominant context; current phase, counter-pressure and volatility cannot independently reverse the regime.",
    })
    pr.update({
        "state_machine": state_machine,
        "primary_thesis": thesis,
        "market_state": market_state,
        "trend_state": trend_state,
        "dominant_direction": dominant,
        "market_phase": phase,
        "current_pressure": current_pressure,
        "counter_pressure": counter_pressure,
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
    })

    trace = list(output.get("reasoning_trace") or [])
    trace.extend([
        f"V7_DOMINANT_CONTEXT -> {dominant} basis={dominant_basis}",
        f"V7_MARKET_PHASE -> {phase} basis={phase_basis}",
        f"V7_PRESSURE -> dominant={dominant} current={current_pressure} counter={counter_pressure}",
        "V7_VOLATILITY_BOUNDARY -> volatility describes intensity, not direction",
        "V7_E2_CONTRACT -> directional_pressure is dominant direction; current_pressure is separate",
        "V7_DECISION_BOUNDARY -> market-state only; no setup/entry/risk/trade authority",
    ])
    output["professional_reasoning"] = pr
    output["reasoning_trace"] = trace
    output["v7_arbitration"] = {
        "market_state": market_state,
        "dominant_direction": dominant,
        "dominant_basis": dominant_basis,
        "market_phase": phase,
        "phase_basis": phase_basis,
        "current_pressure": current_pressure,
        "counter_pressure": counter_pressure,
        "transition": transition,
    }
    output["reasons"] = list(dict.fromkeys(list(output.get("reasons") or [])))
    if previous_state != market_state:
        output["reasons"].append("V7_DOMINANT_CONTEXT_RECLASSIFIED")
    if counter_pressure == "PULLBACK_WITHIN_TREND":
        output["reasons"].append("V7_COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    return output
