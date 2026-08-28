"""E1 — Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It classifies the closed-candle market regime and exposes evidence for the
next brain. It never selects a setup or authorizes a trade action.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

MARKET_STATES = {
    "TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION",
    "EXPANSION", "TRANSITION", "UNCLEAR",
}
QUESTION = "What is the market doing right now?"
MIN_BARS = 60
EVIDENCE_HIERARCHY = (
    "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> "
    "PERSISTENCE -> STATE -> TRANSITION"
)
OWNERSHIP = {
    "owns": [
        "data_integrity", "volatility_regime", "market_structure_context",
        "directional_pressure", "multi_horizon_alignment", "trend_persistence",
        "market_regime", "regime_transition",
    ],
    "does_not_own": [
        "opportunity_setup", "liquidity_auction", "trade_location",
        "trade_economics", "risk_management", "trade_action",
    ],
}


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    current = values[0]
    result = [current]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def _atr(bars: list[dict[str, Any]], period: int) -> float:
    sample = bars[-period:]
    trs: list[float] = []
    previous_close: float | None = None
    for bar in sample:
        high, low, close = bar["high"], bar["low"], bar["close"]
        tr = high - low if previous_close is None else max(
            high - low, abs(high - previous_close), abs(low - previous_close)
        )
        trs.append(max(0.0, tr))
        previous_close = close
    return mean(trs) if trs else 0.0


def _slope(values: list[float], atr: float, lookback: int) -> float:
    if atr <= 0 or len(values) <= lookback:
        return 0.0
    return (values[-1] - values[-1 - lookback]) / atr


def _efficiency(values: list[float], lookback: int) -> float:
    sample = values[-lookback:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)


def _pivot_structure(bars: list[dict[str, Any]], wing: int = 2) -> tuple[str, float, dict[str, int]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        high, low = bars[i]["high"], bars[i]["low"]
        if high >= max(x["high"] for x in window):
            highs.append(high)
        if low <= min(x["low"] for x in window):
            lows.append(low)
    highs, lows = highs[-6:], lows[-6:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    counts = {"HH": hh, "HL": hl, "LH": lh, "LL": ll}
    bull = min(hh, hl)
    bear = min(lh, ll)
    if bull >= 2 and bull > bear:
        return "BULLISH", min(1.0, 0.62 + 0.09 * bull), counts
    if bear >= 2 and bear > bull:
        return "BEARISH", min(1.0, 0.62 + 0.09 * bear), counts
    directional_bull, directional_bear = hh + hl, lh + ll
    if directional_bull >= 2 and directional_bull > directional_bear:
        return "BULLISH", 0.52, counts
    if directional_bear >= 2 and directional_bear > directional_bull:
        return "BEARISH", 0.52, counts
    return "MIXED", 0.30, counts


def _base_result() -> dict[str, Any]:
    return {
        "question": QUESTION,
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN",
    }


def _reasoning(
    *, state: str, direction: str, maturity: str, trend_confirmed: bool,
    transition: bool, regime_stress: bool, conflicts: list[str], reason: str,
    pressure_score: float, structure_alignment: float, trend_score: float,
    directional_consensus: dict[str, Any], regime_basis: str,
    independent_evidence: dict[str, Any], single_counter_candle: bool,
) -> dict[str, Any]:
    return {
        "task": "DESCRIBE_MARKET_STATE_ONLY",
        "primary_state": state,
        "market_state": state,
        "direction": direction,
        "directional_pressure": "BULLISH" if direction == "UP" else "BEARISH" if direction == "DOWN" else "NEUTRAL",
        "trend_maturity": maturity,
        "trend_confirmed": trend_confirmed,
        "regime_stress": regime_stress,
        "transition_confirmed": transition,
        "conflict_detected": bool(conflicts),
        "conflict_count": len(conflicts),
        "classification_reason": reason,
        "single_counter_candle": single_counter_candle,
        "pressure_score": round(pressure_score, 3),
        "structure_alignment": round(structure_alignment, 3),
        "trend_score": round(trend_score, 3),
        "directional_consensus": directional_consensus,
        "regime_basis": regime_basis,
        "independent_evidence": independent_evidence,
        "evidence_hierarchy": EVIDENCE_HIERARCHY,
        "ownership_boundaries": OWNERSHIP,
    }


def _incomplete(base: dict[str, Any], reason: str, evidence: list[str], conflicts: list[str] | None = None) -> dict[str, Any]:
    conflicts = conflicts or []
    return {
        **base,
        "market_state": "UNCLEAR",
        "directional_pressure": "NEUTRAL",
        "trend_state": "NONE",
        "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR",
        "structure_quality": 0.0,
        "range_state": "UNKNOWN",
        "compression": "UNKNOWN",
        "expansion": "UNKNOWN",
        "transition": "UNKNOWN",
        "regime_stress": "UNKNOWN",
        "confidence": 0.0,
        "evidence": evidence,
        "observations": evidence,
        "conflicts": conflicts,
        "reasons": [reason],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", "DATA -> insufficient reliable evidence", f"STATE -> UNCLEAR because={reason}"],
        "professional_reasoning": _reasoning(
            state="UNCLEAR", direction="NEUTRAL", maturity="UNAVAILABLE",
            trend_confirmed=False, transition=False, regime_stress=False,
            conflicts=conflicts, reason=reason, pressure_score=0.0,
            structure_alignment=0.0, trend_score=0.0,
            directional_consensus={"confirmed": False, "score": 0.0},
            regime_basis=reason, independent_evidence={"data_quality": evidence},
            single_counter_candle=False,
        ),
        "analysis_status": "INCOMPLETE",
    }


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Classify the market regime from closed candles; never choose a trade."""
    base = _base_result()
    valid: list[dict[str, Any]] = []
    invalid_count = 0
    for raw in bars or []:
        if not isinstance(raw, dict):
            invalid_count += 1
            continue
        values = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            invalid_count += 1
            continue
        o, h, l, c = values["open"], values["high"], values["low"], values["close"]
        if h < l or h < max(o, c) or l > min(o, c):
            invalid_count += 1
            continue
        valid.append({**raw, "open": o, "high": h, "low": l, "close": c})

    if len(valid) < MIN_BARS:
        return _incomplete(
            base, "insufficient reliable closed candles; classification withheld",
            [f"valid_candles={len(valid)}", f"minimum_required={MIN_BARS}"],
            ["DATA_QUALITY_ANOMALIES"] if invalid_count else [],
        )

    closes = [b["close"] for b in valid]
    atr14, atr50 = _atr(valid, 14), _atr(valid, 50)
    if atr14 <= 0 or atr50 <= 0:
        return _incomplete(base, "ATR invalid; classification withheld", ["ATR_INVALID"], ["ATR_INVALID"])

    ema20s, ema50s = _ema(closes, 20), _ema(closes, 50)
    ema20, ema50 = ema20s[-1], ema50s[-1]
    ema_relation = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    ema_gap = (ema20 - ema50) / atr14
    ema20_slope = _slope(ema20s, atr14, 5)
    ema50_slope = _slope(ema50s, atr14, 5)

    lookbacks = (5, 10, 20, 40)
    slopes = [_slope(closes, atr14, n) for n in lookbacks]
    thresholds = (0.15, 0.20, 0.30, 0.40)
    horizons = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s, t in zip(slopes, thresholds)]
    up, down = horizons.count("UP"), horizons.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "BALANCED"
    consensus = max(up, down) / 4

    if pressure == "UP":
        aligned = sum((slopes[0] >= .20, slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45))
    elif pressure == "DOWN":
        aligned = sum((slopes[0] <= -.20, slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45))
    else:
        aligned = 0
    persistence = aligned / 4
    eff10, eff20, eff40 = (_efficiency(closes, n) for n in (10, 20, 40))

    structure, structure_quality, pivot_counts = _pivot_structure(valid)
    structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "NEUTRAL"
    structure_alignment = 1.0 if pressure != "BALANCED" and structure_direction == pressure else 0.0
    if pressure == "BALANCED":
        structure_alignment = 0.5 if structure == "MIXED" else 0.0

    ema_alignment = 1.0 if pressure in {"UP", "DOWN"} and ema_relation == pressure else 0.0
    ema_conflict = pressure in {"UP", "DOWN"} and ema_relation in {"UP", "DOWN"} and ema_relation != pressure
    structure_conflict = pressure in {"UP", "DOWN"} and structure_direction in {"UP", "DOWN"} and structure_direction != pressure
    horizon_conflict = up > 0 and down > 0

    conflicts: list[str] = []
    if invalid_count:
        conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict:
        conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structure_conflict:
        conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict:
        conflicts.append("SHORT_VS_LONG_HORIZON")
    if pressure == "BALANCED":
        conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")

    volatility_ratio = atr14 / atr50
    compression = volatility_ratio < .78
    expansion = volatility_ratio > 1.18
    volatility = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"

    pressure_score = consensus * (0.65 + 0.35 * persistence)
    trend_score = (
        0.30 * consensus + 0.25 * persistence + 0.20 * structure_alignment
        + 0.15 * ema_alignment + 0.10 * max(eff20, eff40)
    )

    # A professional trend requires coherent evidence. EMA alignment alone is
    # never sufficient, and a mixed structure cannot be overridden merely by
    # a strong recent slope.
    trend_candidate = (
        pressure in {"UP", "DOWN"}
        and consensus >= .75
        and persistence >= .50
        and structure_alignment >= .50
        and ema_alignment == 1.0
        and max(eff20, eff40) >= .22
    )

    prior_context = _slope(closes, atr14, 30)
    recent_context = _slope(closes, atr14, 8)
    context_flip = (
        abs(prior_context) >= .45 and abs(recent_context) >= .65
        and (prior_context > 0) != (recent_context > 0)
    )
    structure_break_proxy = structure_conflict and persistence >= .75 and structure_quality >= .52
    persistent_horizon_flip = horizon_conflict and consensus >= .75 and persistence >= .75
    ema_context_flip = ema_conflict and context_flip and persistence >= .50
    ema_lag_transition = (
        ema_conflict and consensus >= .75 and persistence >= .75
        and (abs(slopes[1]) >= .20 or abs(slopes[2]) >= .30)
    )
    transition_evidence = [
        label for label, ok in (
            ("CONTEXT_FLIP", context_flip),
            ("STRUCTURE_BREAK_PROXY", structure_break_proxy),
            ("PERSISTENT_HORIZON_FLIP", persistent_horizon_flip),
            ("EMA_CONTEXT_FLIP", ema_context_flip),
            ("EMA_LAG_WITH_PERSISTENT_PRESSURE", ema_lag_transition),
        ) if ok
    ]
    hard_anchor = context_flip or structure_break_proxy
    corroboration = persistent_horizon_flip or ema_context_flip or structure_break_proxy
    transition = not trend_candidate and ((hard_anchor and corroboration) or ema_lag_transition)
    regime_stress = (
        not transition and not trend_candidate and pressure in {"UP", "DOWN"}
        and (ema_conflict or structure_conflict or horizon_conflict)
        and (consensus >= .50 or persistence >= .50)
    )
    if context_flip:
        conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")

    prior_pressure = (
        "UP" if _slope(closes[:-1], atr14, 5) > .20
        else "DOWN" if _slope(closes[:-1], atr14, 5) < -.20
        else "NEUTRAL"
    )
    last_candle_direction = "UP" if closes[-1] > valid[-1]["open"] else "DOWN" if closes[-1] < valid[-1]["open"] else "FLAT"
    single_counter_candle = (
        prior_pressure in {"UP", "DOWN"}
        and last_candle_direction in {"UP", "DOWN"}
        and last_candle_direction != prior_pressure
        and not transition
    )

    range_candidate = pressure == "BALANCED" and eff20 < .35 and eff40 < .40 and abs(ema_gap) < .85
    expansion_candidate = expansion and pressure in {"UP", "DOWN"} and eff10 >= .25 and abs(slopes[0]) >= .25

    if transition:
        state, reason, maturity = "TRANSITION", "persistent repricing is strong but conflicts with slower context", "TRANSITION"
    elif trend_candidate:
        state, reason, maturity = (
            "TREND_UP" if pressure == "UP" else "TREND_DOWN",
            "direction, persistence, structure, EMA context and efficiency are coherent",
            "ESTABLISHED",
        )
    elif expansion_candidate and pressure in {"UP", "DOWN"} and trend_score < .60:
        state, reason, maturity = "EXPANSION", "volatility expansion is accompanied by directional impulse without full regime coherence", "EXPANDING"
    elif compression and (pressure == "BALANCED" or eff20 < .30):
        state, reason, maturity = "COMPRESSION", "volatility contraction dominates directional evidence", "CONTRACTING"
    elif range_candidate:
        state, reason, maturity = "RANGE", "two-sided non-directional behavior dominates", "RANGE"
    elif pressure in {"UP", "DOWN"} and (persistence >= .25 or consensus >= .50):
        state, reason, maturity = "UNCLEAR", "directional pressure exists but regime confirmation is insufficient", "UNRESOLVED"
    else:
        state, reason, maturity = "UNCLEAR", "evidence does not establish a dominant regime", "UNRESOLVED"

    direction = "UP" if pressure == "UP" else "DOWN" if pressure == "DOWN" else "NEUTRAL"
    public_pressure = "BULLISH" if direction == "UP" else "BEARISH" if direction == "DOWN" else "NEUTRAL"
    directional_consensus = {
        "direction": direction,
        "confirmed": consensus >= .75,
        "score": round(consensus, 3),
        "horizons": horizons,
        "up_count": up,
        "down_count": down,
    }
    independent_evidence = {
        "data_quality": {"valid_candles": len(valid), "invalid_candles": invalid_count},
        "volatility": {"atr14": round(atr14, 6), "atr50": round(atr50, 6), "ratio": round(volatility_ratio, 3)},
        "structure": {"state": structure, "quality": round(structure_quality, 3), "counts": pivot_counts},
        "pressure": {"direction": direction, "score": round(pressure_score, 3)},
        "persistence": {"score": round(persistence, 3), "efficiency20": round(eff20, 3), "efficiency40": round(eff40, 3)},
        "ema_context": {"relation": ema_relation, "gap_atr": round(ema_gap, 3), "alignment": round(ema_alignment, 3)},
        "transition": {"confirmed": transition, "evidence": transition_evidence},
    }
    regime_basis = (
        f"pressure={direction}; consensus={consensus:.2f}; persistence={persistence:.2f}; "
        f"structure={structure}; ema={ema_relation}; volatility={volatility}; "
        f"trend_score={trend_score:.2f}"
    )
    reasons = list(conflicts)
    if transition:
        reasons.append("REGIME_TRANSITION_CONFIRMED")
    elif regime_stress:
        reasons.append("REGIME_STRESS_ACTIVE")
    elif state == "UNCLEAR":
        reasons.append("REGIME_CONFIRMATION_INSUFFICIENT")

    evidence = [
        f"valid_candles={len(valid)}",
        f"invalid_candles={invalid_count}",
        f"ema20_vs_ema50={ema_relation}",
        f"ema_gap_atr={ema_gap:.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}",
        f"ema50_slope_atr={ema50_slope:.3f}",
        *(f"price_slope_{n}_atr={s:.3f}" for n, s in zip(lookbacks, slopes)),
        f"multi_horizon={','.join(horizons)}",
        f"directional_consensus={consensus:.3f}",
        f"persistence={persistence:.3f}",
        f"efficiency20={eff20:.3f}",
        f"efficiency40={eff40:.3f}",
        f"structure_counts={pivot_counts}",
        f"structure_alignment={structure_alignment:.3f}",
        f"pressure_score={pressure_score:.3f}",
        f"trend_score={trend_score:.3f}",
        f"context_flip={context_flip}",
        f"transition_evidence={transition_evidence}",
        f"trend_candidate={trend_candidate}",
        f"regime_stress={regime_stress}",
        f"ema_lag_transition={ema_lag_transition}",
        f"single_counter_candle={single_counter_candle}",
    ]
    confidence = .30 + .25 * structure_quality + .20 * consensus + .15 * persistence + .10 * max(eff20, eff40)
    if state == "UNCLEAR":
        confidence = min(confidence, .65)
    if transition or regime_stress:
        confidence = min(confidence, .80)

    return {
        **base,
        "market_state": state,
        "directional_pressure": public_pressure,
        "trend_state": "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE",
        "volatility_state": volatility,
        "structure_state": structure,
        "structure_quality": round(structure_quality, 3),
        "range_state": "RANGE" if range_candidate else "NOT_RANGE",
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": "PRESENT" if transition else "ABSENT",
        "regime_stress": "PRESENT" if regime_stress else "ABSENT",
        "confidence": round(max(0.0, min(0.99, confidence)), 3),
        "evidence": evidence,
        "observations": evidence,
        "conflicts": conflicts,
        "reasons": reasons,
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            "EVIDENCE_HIERARCHY -> " + EVIDENCE_HIERARCHY,
            f"STRUCTURE -> {structure} quality={structure_quality:.2f} alignment={structure_alignment:.2f}",
            f"PRESSURE -> {direction} score={pressure_score:.2f}",
            f"VOLATILITY -> {volatility} ratio={volatility_ratio:.2f}",
            f"PERSISTENCE -> {persistence:.2f}",
            f"TREND_SCORE -> {trend_score:.2f}",
            f"REGIME_CONFIRMATION -> trend_confirmed={trend_candidate} maturity={maturity}",
            f"REGIME_STRESS -> {'PRESENT' if regime_stress else 'ABSENT'}",
            f"STATE -> {state} because={reason}",
            f"TRANSITION -> {'PRESENT' if transition else 'ABSENT'} evidence={transition_evidence}",
        ],
        "professional_reasoning": _reasoning(
            state=state, direction=direction, maturity=maturity,
            trend_confirmed=state in {"TREND_UP", "TREND_DOWN"},
            transition=transition, regime_stress=regime_stress,
            conflicts=conflicts, reason=reason,
            pressure_score=pressure_score, structure_alignment=structure_alignment,
            trend_score=trend_score, directional_consensus=directional_consensus,
            regime_basis=regime_basis, independent_evidence=independent_evidence,
            single_counter_candle=single_counter_candle,
        ),
        "analysis_status": "COMPLETE",
    }
