"""E1 Professional Market-State Brain V10.

V10 makes E1 a strict hierarchical market-state authority.  The dominant
regime is separated from short-term pressure, and a transition cannot be
committed from a single opposite move.  A structural flip must persist across
multiple structural windows and agree with the EMA regime, long-horizon
slopes, and recent pressure.

E1 remains market-state only: it has no setup, entry, risk, or trade authority.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_layer_v9 import analyze_e1_professional_v9
from .e1_professional_layer_v8 import _atr, _ema, _recent_pressure, _slope, _structure_direction

MIN_GAP_ATR = 0.50
MIN_SLOPE_ATR = 0.20
CONFIRM_GAP_ATR = 0.50


def _opposite(direction: str) -> str:
    return "DOWN" if direction == "UP" else "UP" if direction == "DOWN" else "NEUTRAL"


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
    """Classify transition without allowing counter-pressure to flip regime.

    CONFIRMED requires the opposite structure to persist in three structural
    views plus an EMA flip, both long-horizon slopes, a meaningful EMA gap and
    opposite recent pressure.  Anything weaker is WATCH/CANDIDATE, never a
    committed transition.
    """
    if dominant not in {"UP", "DOWN"}:
        return {
            "score": 0,
            "status": "UNRESOLVED",
            "watch": False,
            "committed": False,
            "evidence": [],
            "required": [],
        }

    opposite = _opposite(dominant)
    evidence: list[str] = []
    required: list[str] = []
    score = 0

    if structure == opposite:
        score += 2
        evidence.append("CURRENT_STRUCTURE_OPPOSITE")
    else:
        required.append("CURRENT_STRUCTURE_FLIP")

    if structure_recent == opposite:
        score += 1
        evidence.append("RECENT_STRUCTURE_OPPOSITE")
    else:
        required.append("RECENT_STRUCTURE_PERSISTENCE")

    if structure_lookback == opposite:
        score += 1
        evidence.append("LOOKBACK_STRUCTURE_OPPOSITE")
    else:
        required.append("LOOKBACK_STRUCTURE_PERSISTENCE")

    if ema == opposite:
        score += 2
        evidence.append("EMA_REGIME_FLIP")
    else:
        required.append("EMA_REGIME_FLIP")

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

    gap_opposite = (
        gap >= CONFIRM_GAP_ATR if opposite == "UP" else gap <= -CONFIRM_GAP_ATR
    )
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

    committed = (
        structure == opposite
        and structure_recent == opposite
        and structure_lookback == opposite
        and ema == opposite
        and slopes_opposite
        and gap_opposite
        and recent == opposite
    )

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


def _phase(dominant: str, recent: str) -> str:
    if dominant not in {"UP", "DOWN"}:
        return "UNRESOLVED"
    if recent == dominant:
        return "IMPULSE"
    if recent == _opposite(dominant):
        return "PULLBACK"
    return "CONSOLIDATION"


def analyze_e1_professional_v10(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """V10 E1: authoritative hierarchical market-state arbitration."""
    output = dict(analyze_e1_professional_v9(bars))
    if output.get("analysis_status") == "INCOMPLETE":
        return output

    clean = [
        b for b in (bars or [])
        if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))
    ]
    if len(clean) < 50:
        output["analysis_status"] = "INCOMPLETE"
        output["reasons"] = list(dict.fromkeys([*(output.get("reasons") or []), "INSUFFICIENT_CANDLES_FOR_V10"]))
        return output

    closes = [float(b["close"]) for b in clean]
    atr = _atr(clean)
    if atr <= 0:
        output["analysis_status"] = "INCOMPLETE"
        output["reasons"] = list(dict.fromkeys([*(output.get("reasons") or []), "INVALID_ATR_FOR_V10"]))
        return output

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    gap = (ema20 - ema50) / max(atr, 1e-12)
    ema = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "NEUTRAL"

    # Three structural horizons prevent one recent swing from becoming a
    # regime flip. The full window is the anchor; 80/40 bars test persistence.
    structure = _structure_direction(clean)
    structure_recent = _structure_direction(clean[-80:]) if len(clean) >= 80 else "NEUTRAL"
    structure_lookback = _structure_direction(clean[-40:]) if len(clean) >= 40 else "NEUTRAL"
    slope20 = _slope(closes, atr, 20)
    slope40 = _slope(closes, atr, 40)
    recent = _recent_pressure(clean, atr)

    # E1's dominant regime is intentionally conservative. Structure + EMA
    # agreement wins; otherwise both long-horizon slopes must agree with EMA.
    if ema in {"UP", "DOWN"} and structure == ema:
        dominant = ema
        dominant_basis = "STRUCTURE_EMA_ALIGNMENT"
    elif (
        ema in {"UP", "DOWN"}
        and abs(gap) >= MIN_GAP_ATR
        and (
            (ema == "UP" and slope20 >= MIN_SLOPE_ATR and slope40 >= MIN_SLOPE_ATR)
            or (ema == "DOWN" and slope20 <= -MIN_SLOPE_ATR and slope40 <= -MIN_SLOPE_ATR)
        )
    ):
        dominant = ema
        dominant_basis = "EMA_LONG_HORIZON_ALIGNMENT"
    elif (
        structure in {"UP", "DOWN"}
        and (
            (structure == "UP" and slope20 >= MIN_SLOPE_ATR and slope40 >= MIN_SLOPE_ATR)
            or (structure == "DOWN" and slope20 <= -MIN_SLOPE_ATR and slope40 <= -MIN_SLOPE_ATR)
        )
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
        market_state = "TRANSITION"
        trend_state = "NONE"
        transition_label = "CONFIRMED"
    elif dominant == "UP":
        market_state = "TREND_UP"
        trend_state = "UP"
        transition_label = "WATCH" if transition["watch"] else "ABSENT"
    elif dominant == "DOWN":
        market_state = "TREND_DOWN"
        trend_state = "DOWN"
        transition_label = "WATCH" if transition["watch"] else "ABSENT"
    else:
        market_state = base if base in {"RANGE", "COMPRESSION", "EXPANSION"} else "UNCLEAR"
        trend_state = "NONE"
        transition_label = "WATCH" if transition["watch"] else "ABSENT"

    phase = _phase(dominant, recent)
    current_pressure = "BULLISH" if recent == "UP" else "BEARISH" if recent == "DOWN" else "NEUTRAL"
    counter_pressure = "PULLBACK_WITHIN_TREND" if dominant in {"UP", "DOWN"} and recent == _opposite(dominant) else "NONE"

    # Explicit V10 contract: one dominant regime, separate current pressure,
    # and transition status that cannot be inferred from a short counter-move.
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
        "structural_persistence": structure == structure_recent == structure_lookback and structure in {"UP", "DOWN"},
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
            "structural_persistence": output["structural_persistence"],
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
        thesis["counter_evidence"] = list(dict.fromkeys([*(thesis.get("counter_evidence") or []), "COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL"]))

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
        "structural_persistence": output["structural_persistence"],
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
        "structural_persistence": output["structural_persistence"],
        "transition_status": transition["status"],
        "decision_boundary": "MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION",
        "e1_telemetry_authority": "TOP_LEVEL_E1_OUTPUT",
    })
    output["professional_reasoning"] = pr

    trace = list(output.get("reasoning_trace") or [])
    trace.extend([
        f"V10_DOMINANT_CONTEXT -> {dominant} basis={dominant_basis}",
        f"V10_STRUCTURE -> current={structure} recent={structure_recent} lookback={structure_lookback} persistent={output['structural_persistence']}",
        f"V10_PHASE -> {phase} recent_pressure={recent}",
        f"V10_TRANSITION -> {transition_label} status={transition['status']} score={transition['score']} committed={transition['committed']}",
        "V10_PRIORITY -> dominant regime > persistent structure > long-horizon context > short-term pressure",
        "V10_BOUNDARY -> counter-pressure cannot independently create a regime reversal",
        "V10_DECISION_BOUNDARY -> market-state only; no setup/entry/risk/trade authority",
    ])
    output["reasoning_trace"] = list(dict.fromkeys(trace))

    reasons = list(output.get("reasons") or [])
    reasons.extend(["V10_HIERARCHICAL_STATE_MACHINE", "V10_PERSISTENT_STRUCTURE_CONTRACT", "V10_TRANSITION_GUARD"])
    if counter_pressure == "PULLBACK_WITHIN_TREND":
        reasons.append("V10_COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    if transition["status"] == "CANDIDATE":
        reasons.append("V10_TRANSITION_CANDIDATE_REQUIRES_PERSISTENCE")
    if transition["committed"]:
        reasons.append("V10_TRANSITION_CONFIRMED_PERSISTENT_STRUCTURE")
    output["reasons"] = list(dict.fromkeys(str(x) for x in reasons))
    return output
