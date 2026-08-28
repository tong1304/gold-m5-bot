"""E1 Professional Market-State Brain V7.

V7 separates the dominant market regime from current phase, directional
pressure and volatility. A short counter-move no longer downgrades a strong
trend context to UNCLEAR when EMA context and market structure remain aligned.
E1 remains strictly market-state only.
"""
from __future__ import annotations

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

    # Structure + EMA agreement is the strongest directional context. A large
    # EMA separation makes the context resilient to a short counter-move.
    if ema in {"UP", "DOWN"} and structure == ema:
        return ema, "STRUCTURE_EMA_ALIGNMENT"

    # If structure is unavailable/mixed, require both longer slopes to agree
    # before declaring a directional regime.
    long_dir = "UP" if slope20 >= LONG_SLOPE_ATR and slope40 >= LONG_SLOPE_ATR else "DOWN" if slope20 <= -LONG_SLOPE_ATR and slope40 <= -LONG_SLOPE_ATR else "NEUTRAL"
    if ema == long_dir and abs(gap) >= STRONG_EMA_GAP_ATR:
        return ema, "EMA_LONG_HORIZON_ALIGNMENT"

    return "NEUTRAL", "NO_DOMINANT_DIRECTION"


def _phase(bars: list[dict[str, Any]], dominant: str, atr: float) -> tuple[str, str]:
    """Describe the current phase without changing the dominant regime."""
    if dominant not in {"UP", "DOWN"} or atr <= 0 or len(bars) < 5:
        return "UNRESOLVED", "NO_DOMINANT_TREND"
    sample = bars[-5:]
    closes = [float(b["close"]) for b in sample if isinstance(b, dict) and "close" in b]
    bodies = []
    for b in sample:
        if not isinstance(b, dict):
            continue
        try:
            o, c = float(b["open"]), float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        bodies.append("UP" if c > o else "DOWN" if c < o else "FLAT")
    if len(closes) < 2:
        return "UNRESOLVED", "INSUFFICIENT_RECENT_CANDLES"
    recent_slope = (closes[-1] - closes[0]) / atr
    opposite = _opposite(dominant)
    opposite_count = sum(x == opposite for x in bodies)
    dominant_count = sum(x == dominant for x in bodies)

    if recent_slope * (1 if dominant == "UP" else -1) >= PHASE_SLOPE_ATR:
        return "IMPULSE" if dominant_count >= opposite_count else "REACCELERATION", "RECENT_PRESSURE_ALIGNS_WITH_TREND"
    if recent_slope * (1 if dominant == "UP" else -1) <= -PHASE_SLOPE_ATR:
        return "PULLBACK", "RECENT_PRESSURE_COUNTERS_DOMINANT_TREND"
    return "CONSOLIDATION", "RECENT_PRESSURE_BALANCED"


def analyze_e1_professional_v7(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V7: state, phase, pressure and volatility are separate market facts."""
    output = dict(analyze_e1_professional_v6(bars))
    if output.get("analysis_status") == "INCOMPLETE":
        return output

    clean = [b for b in (bars or []) if isinstance(b, dict)]
    pr = dict(output.get("professional_reasoning") or {})
    independent = dict(pr.get("independent_evidence") or {})
    ema_data = independent.get("ema_context") if isinstance(independent.get("ema_context"), dict) else {}
    structure_data = independent.get("structure") if isinstance(independent.get("structure"), dict) else {}
    volatility_data = independent.get("volatility") if isinstance(independent.get("volatility"), dict) else {}

    ema_direction = _direction(ema_data.get("relation"))
    structure_direction = _direction(structure_data.get("state"))
    ema_gap = float(ema_data.get("gap_atr", 0.0) or 0.0)
    atr = float(volatility_data.get("atr14", 0.0) or 0.0)
    slopes = independent.get("price_slopes") if isinstance(independent.get("price_slopes"), dict) else {}
    slope20 = float(slopes.get("20", slopes.get(20, 0.0)) or 0.0)
    slope40 = float(slopes.get("40", slopes.get(40, 0.0)) or 0.0)

    # Fall back to the visible V6 observations if the V5 evidence object uses
    # a different key shape.
    observations = dict(output.get("observations") or {}) if isinstance(output.get("observations"), dict) else {}
    slope20 = float(observations.get("price_slope_20_atr", slope20) or slope20)
    slope40 = float(observations.get("price_slope_40_atr", slope40) or slope40)

    dominant, dominant_basis = _dominant_direction(
        ema_direction=ema_direction,
        structure_direction=structure_direction,
        slope20=slope20,
        slope40=slope40,
        ema_gap_atr=ema_gap,
    )

    phase, phase_basis = _phase(clean, dominant, atr)
    previous_state = str(output.get("market_state") or "UNCLEAR")
    if dominant == "UP":
        market_state = "TREND_UP"
        trend_state = "UP"
    elif dominant == "DOWN":
        market_state = "TREND_DOWN"
        trend_state = "DOWN"
    else:
        market_state = previous_state if previous_state in {"RANGE", "COMPRESSION", "EXPANSION", "TRANSITION"} else "UNCLEAR"
        trend_state = "NONE"

    recent_pressure = "BULLISH" if phase == "PULLBACK" and dominant == "DOWN" else "BEARISH" if phase == "PULLBACK" and dominant == "UP" else "BULLISH" if dominant == "UP" else "BEARISH" if dominant == "DOWN" else "NEUTRAL"
    counter_pressure = "PULLBACK_WITHIN_TREND" if phase == "PULLBACK" else "NONE"
    transition = "ABSENT" if dominant in {"UP", "DOWN"} else output.get("transition", "ABSENT")

    output.update({
        "market_state": market_state,
        "trend_state": trend_state,
        "directional_state": "CONFIRMED" if dominant in {"UP", "DOWN"} else output.get("directional_state", "UNRESOLVED"),
        "directional_state_v7": dominant,
        "market_phase": phase,
        "directional_pressure": recent_pressure,
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
        "ema_direction": ema_direction,
        "structure_direction": structure_direction,
        "ema_gap_atr": round(ema_gap, 3),
        "slope20_atr": round(slope20, 3),
        "slope40_atr": round(slope40, 3),
        "rule": "Market state is determined by dominant context; current phase and counter-pressure cannot independently reverse the regime.",
    })
    pr.update({
        "state_machine": state_machine,
        "primary_thesis": thesis,
        "market_state": market_state,
        "trend_state": trend_state,
        "market_phase": phase,
        "dominant_direction": dominant,
        "counter_pressure": counter_pressure,
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
    })

    trace = list(output.get("reasoning_trace") or [])
    trace.extend([
        f"V7_DOMINANT_CONTEXT -> {dominant} basis={dominant_basis}",
        f"V7_MARKET_PHASE -> {phase} basis={phase_basis}",
        f"V7_PRESSURE -> {recent_pressure} counter_pressure={counter_pressure}",
        "V7_VOLATILITY_BOUNDARY -> volatility describes intensity, not direction",
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
        "pressure": recent_pressure,
        "counter_pressure": counter_pressure,
        "transition": transition,
    }
    output["reasons"] = list(dict.fromkeys(list(output.get("reasons") or [])))
    if previous_state != market_state:
        output["reasons"].append("V7_DOMINANT_CONTEXT_RECLASSIFIED")
    if counter_pressure == "PULLBACK_WITHIN_TREND":
        output["reasons"].append("V7_COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    return output
