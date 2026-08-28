"""E1 Professional Market-State Brain V10.

Strict market-state authority only. E1 describes the market and never owns
setup, entry, risk, execution, or the final trade decision.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_layer_v9 import analyze_e1_professional_v9
from .e1_professional_layer_v8 import (
    _atr,
    _ema,
    _recent_pressure,
    _slope,
    _structure_direction,
)

MIN_GAP_ATR = 0.50
MIN_SLOPE_ATR = 0.20
CONFIRM_GAP_ATR = 0.50


def _opposite(direction: str) -> str:
    return "DOWN" if direction == "UP" else "UP" if direction == "DOWN" else "NEUTRAL"


def _phase(dominant: str, recent: str) -> str:
    if dominant not in {"UP", "DOWN"}:
        return "UNRESOLVED"
    if recent == dominant:
        return "IMPULSE"
    if recent == _opposite(dominant):
        return "PULLBACK"
    return "CONSOLIDATION"


def _transition_v10(
    *,
    dominant: str,
    ema: str,
    structure: str,
    structure_recent: str,
    structure_lookback: str,
    slope20: float,
    slope40: float,
    gap: float,
    recent: str,
    base: str,
) -> dict[str, Any]:
    if dominant not in {"UP", "DOWN"}:
        return {
            "score": 0,
            "status": "UNRESOLVED",
            "watch": False,
            "committed": False,
            "evidence": [],
            "required": [],
            "opposite_direction": "NEUTRAL",
            "base_state": base,
        }

    opposite = _opposite(dominant)
    evidence: list[str] = []
    required: list[str] = []
    score = 0

    checks = [
        (structure == opposite, 2, "CURRENT_STRUCTURE_OPPOSITE", "CURRENT_STRUCTURE_FLIP"),
        (structure_recent == opposite, 1, "RECENT_STRUCTURE_OPPOSITE", "RECENT_STRUCTURE_PERSISTENCE"),
        (structure_lookback == opposite, 1, "LOOKBACK_STRUCTURE_OPPOSITE", "LOOKBACK_STRUCTURE_PERSISTENCE"),
        (ema == opposite, 2, "EMA_REGIME_FLIP", "EMA_REGIME_FLIP"),
    ]
    for ok, points, yes, no in checks:
        if ok:
            score += points
            evidence.append(yes)
        else:
            required.append(no)

    slopes_opposite = (
        slope20 >= MIN_SLOPE_ATR and slope40 >= MIN_SLOPE_ATR
        if opposite == "UP"
        else slope20 <= -MIN_SLOPE_ATR and slope40 <= -MIN_SLOPE_ATR
    )
    if slopes_opposite:
        score += 2
        evidence.append("LONG_HORIZON_SLOPES_OPPOSITE")
    else:
        required.append("LONG_HORIZON_SLOPE_CONFIRMATION")

    gap_opposite = gap >= CONFIRM_GAP_ATR if opposite == "UP" else gap <= -CONFIRM_GAP_ATR
    if gap_opposite:
        score += 1
        evidence.append("EMA_GAP_OPPOSITE")
    else:
        required.append("EMA_GAP_CONFIRMATION")

    if recent == opposite:
        score += 1
        evidence.append("RECENT_PRESSURE_OPPOSITE")
    else:
        required.append("RECENT_PRESSURE_CONFIRMATION")

    committed = all((
        structure == opposite,
        structure_recent == opposite,
        structure_lookback == opposite,
        ema == opposite,
        slopes_opposite,
        gap_opposite,
        recent == opposite,
    ))

    if committed:
        status = "CONFIRMED"
    elif structure == opposite and (structure_recent == opposite or recent == opposite):
        status = "CANDIDATE"
    elif recent == opposite:
        status = "COUNTER_PRESSURE"
    else:
        status = "ABSENT"

    return {
        "score": score,
        "status": status,
        "watch": status in {"CANDIDATE", "COUNTER_PRESSURE"},
        "committed": committed,
        "evidence": evidence,
        "required": required,
        "opposite_direction": opposite,
        "base_state": base,
    }


def analyze_e1_professional_v10(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V10 authoritative hierarchical arbitration with a stable output contract."""
    output = dict(analyze_e1_professional_v9(bars))
    if output.get("analysis_status") == "INCOMPLETE":
        return output

    clean = [
        b for b in (bars or [])
        if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))
    ]
    if len(clean) < 50:
        output["analysis_status"] = "INCOMPLETE"
        output["reasons"] = list(dict.fromkeys([
            *(output.get("reasons") or []),
            "INSUFFICIENT_CANDLES_FOR_V10",
        ]))
        return output

    try:
        closes = [float(b["close"]) for b in clean]
        atr = _atr(clean)
        if atr <= 0:
            raise ValueError("INVALID_ATR_FOR_V10")

        ema20s = _ema(closes, 20)
        ema50s = _ema(closes, 50)
        ema20, ema50 = ema20s[-1], ema50s[-1]
        gap = (ema20 - ema50) / max(atr, 1e-12)
        ema = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "NEUTRAL"

        structure = _structure_direction(clean)
        structure_recent = _structure_direction(clean[-80:]) if len(clean) >= 80 else "NEUTRAL"
        structure_lookback = _structure_direction(clean[-40:]) if len(clean) >= 40 else "NEUTRAL"
        slope20 = _slope(closes, atr, 20)
        slope40 = _slope(closes, atr, 40)
        recent = _recent_pressure(clean, atr)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        output["analysis_status"] = "INCOMPLETE"
        output["reasons"] = list(dict.fromkeys([
            *(output.get("reasons") or []),
            f"V10_DATA_ERROR:{type(exc).__name__}",
        ]))
        return output

    if ema in {"UP", "DOWN"} and structure == ema:
        dominant = ema
        dominant_basis = "STRUCTURE_EMA_ALIGNMENT"
    elif (
        ema in {"UP", "DOWN"}
        and abs(gap) >= MIN_GAP_ATR
        and ((ema == "UP" and slope20 >= MIN_SLOPE_ATR and slope40 >= MIN_SLOPE_ATR)
             or (ema == "DOWN" and slope20 <= -MIN_SLOPE_ATR and slope40 <= -MIN_SLOPE_ATR))
    ):
        dominant = ema
        dominant_basis = "EMA_LONG_HORIZON_ALIGNMENT"
    elif (
        structure in {"UP", "DOWN"}
        and ((structure == "UP" and slope20 >= MIN_SLOPE_ATR and slope40 >= MIN_SLOPE_ATR)
             or (structure == "DOWN" and slope20 <= -MIN_SLOPE_ATR and slope40 <= -MIN_SLOPE_ATR))
    ):
        dominant = structure
        dominant_basis = "STRUCTURE_LONG_HORIZON_ALIGNMENT"
    elif slope20 >= MIN_SLOPE_ATR and slope40 >= MIN_SLOPE_ATR:
        dominant = "UP"
        dominant_basis = "LONG_HORIZON_ALIGNMENT"
    elif slope20 <= -MIN_SLOPE_ATR and slope40 <= -MIN_SLOPE_ATR:
        dominant = "DOWN"
        dominant_basis = "LONG_HORIZON_ALIGNMENT"
    else:
        dominant = "NEUTRAL"
        dominant_basis = "NO_DOMINANT_CONTEXT"

    base = str(output.get("market_state") or "UNCLEAR").upper()
    transition = _transition_v10(
        dominant=dominant,
        ema=ema,
        structure=structure,
        structure_recent=structure_recent,
        structure_lookback=structure_lookback,
        slope20=slope20,
        slope40=slope40,
        gap=gap,
        recent=recent,
        base=base,
    )

    if transition["committed"]:
        market_state, trend_state, transition_label = "TRANSITION", "NONE", "CONFIRMED"
    elif dominant == "UP":
        market_state, trend_state = "TREND_UP", "UP"
        transition_label = "WATCH" if transition["watch"] else "ABSENT"
    elif dominant == "DOWN":
        market_state, trend_state = "TREND_DOWN", "DOWN"
        transition_label = "WATCH" if transition["watch"] else "ABSENT"
    else:
        market_state = base if base in {"RANGE", "COMPRESSION", "EXPANSION"} else "UNCLEAR"
        trend_state, transition_label = "NONE", "WATCH" if transition["watch"] else "ABSENT"

    phase = _phase(dominant, recent)
    current_pressure = "BULLISH" if recent == "UP" else "BEARISH" if recent == "DOWN" else "NEUTRAL"
    counter_pressure = (
        "PULLBACK_WITHIN_TREND"
        if dominant in {"UP", "DOWN"} and recent == _opposite(dominant)
        else "NONE"
    )
    structural_persistence = (
        structure == structure_recent == structure_lookback
        and structure in {"UP", "DOWN"}
    )

    # IMPORTANT: compute derived values before output.update(). Python evaluates
    # nested dictionary values before update(), so reading output[...] here used
    # to cause the production KeyError 'structural_persistence'.
    output.update({
        "market_state": market_state,
        "trend_state": trend_state,
        "dominant_direction": dominant,
        "directional_state": "CONFIRMED" if dominant in {"UP", "DOWN"} else "UNRESOLVED",
        "directional_pressure": dominant,
        "current_pressure": current_pressure,
        "counter_pressure": counter_pressure,
        "market_phase": phase,
        "structural_regime": structure,
        "structural_regime_recent": structure_recent,
        "structural_regime_lookback": structure_lookback,
        "structural_persistence": structural_persistence,
        "transition": transition_label,
        "transition_status": transition["status"],
        "transition_confirmed": transition["committed"],
        "transition_committed": transition["committed"],
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V10",
        "e1_trade_authority": False,
        "trade_decision_authority": False,
        "v10_arbitration": {
            "dominant_direction": dominant,
            "dominant_basis": dominant_basis,
            "market_state": market_state,
            "market_phase": phase,
            "current_pressure": current_pressure,
            "counter_pressure": counter_pressure,
            "ema_direction": ema,
            "ema_gap_atr": round(gap, 3),
            "slope20_atr": round(slope20, 3),
            "slope40_atr": round(slope40, 3),
            "structural_regime": structure,
            "structural_regime_recent": structure_recent,
            "structural_regime_lookback": structure_lookback,
            "structural_persistence": structural_persistence,
            "transition": transition,
            "rule": "Dominant regime > persistent structure > long-horizon context > short-term pressure; counter-pressure is phase evidence, not reversal evidence.",
        },
    })

    pr = dict(output.get("professional_reasoning") or {})
    thesis = dict(pr.get("primary_thesis") or {})
    thesis.update({
        "direction": dominant,
        "market_state": market_state,
        "phase": phase,
        "transition": transition_label,
        "transition_status": transition["status"],
        "status": "CONFIRMED" if dominant in {"UP", "DOWN"} else "UNRESOLVED",
    })
    if counter_pressure == "PULLBACK_WITHIN_TREND":
        thesis["counter_evidence"] = list(dict.fromkeys([
            *(thesis.get("counter_evidence") or []),
            "COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL",
        ]))

    state_machine = dict(pr.get("state_machine") or {})
    state_machine.update({
        "version": "V10",
        "dominant_direction": dominant,
        "dominant_basis": dominant_basis,
        "market_state": market_state,
        "market_phase": phase,
        "current_pressure": current_pressure,
        "counter_pressure": counter_pressure,
        "structural_regime": structure,
        "structural_regime_recent": structure_recent,
        "structural_regime_lookback": structure_lookback,
        "structural_persistence": structural_persistence,
        "transition": transition_label,
        "transition_status": transition["status"],
        "transition_confirmed": transition["committed"],
        "transition_evidence": transition,
        "rule": "A short counter-move cannot reverse the dominant regime. Transition requires persistent opposite structure plus EMA, long-horizon slope, gap and pressure confirmation.",
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
        "structural_regime": structure,
        "structural_persistence": structural_persistence,
        "transition_status": transition["status"],
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
        "e1_telemetry_authority": "TOP_LEVEL_E1_OUTPUT",
    })
    output["professional_reasoning"] = pr

    trace = list(output.get("reasoning_trace") or [])
    trace.extend([
        f"V10_DOMINANT_CONTEXT -> {dominant} basis={dominant_basis}",
        f"V10_STRUCTURE -> current={structure} recent={structure_recent} lookback={structure_lookback} persistent={structural_persistence}",
        f"V10_PHASE -> {phase} recent_pressure={recent}",
        f"V10_TRANSITION -> {transition_label} status={transition['status']} score={transition['score']} committed={transition['committed']}",
        "V10_PRIORITY -> dominant regime > persistent structure > long-horizon context > short-term pressure",
        "V10_BOUNDARY -> counter-pressure cannot independently create a regime reversal",
        "V10_DECISION_BOUNDARY -> market-state only; no setup/entry/risk/trade authority",
    ])
    output["reasoning_trace"] = list(dict.fromkeys(trace))

    reasons = list(output.get("reasons") or [])
    reasons.extend([
        "V10_HIERARCHICAL_STATE_MACHINE",
        "V10_PERSISTENT_STRUCTURE_CONTRACT",
        "V10_TRANSITION_GUARD",
    ])
    if counter_pressure == "PULLBACK_WITHIN_TREND":
        reasons.append("V10_COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    if transition["status"] == "CANDIDATE":
        reasons.append("V10_TRANSITION_CANDIDATE_REQUIRES_PERSISTENCE")
    if transition["committed"]:
        reasons.append("V10_TRANSITION_CONFIRMED_PERSISTENT_STRUCTURE")
    output["reasons"] = list(dict.fromkeys(str(x) for x in reasons))
    output["analysis_status"] = "COMPLETE"
    return output
