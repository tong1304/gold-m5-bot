"""E1 — Professional Market-State Brain.

E1 answers one question only: What is the market doing right now?
It analyses CLOSED candles only and owns market-state classification.
It must never create a setup, entry, stop, target, risk plan, or trade decision.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
DIRECTIONAL_STATES = {"CONFIRMED", "DEVELOPING", "NEUTRAL", "CONFLICTED", "UNRESOLVED"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> VOLATILITY -> STABILITY -> COUNTER_EVIDENCE -> STATE -> TRANSITION"
OWNERSHIP = {
    "owns": [
        "data_integrity", "volatility_regime", "market_structure_context",
        "directional_pressure", "multi_horizon_alignment", "trend_persistence",
        "market_regime", "regime_transition", "state_stability", "counter_evidence",
        "market_state_thesis", "market_state_invalidation",
    ],
    "does_not_own": [
        "opportunity_setup", "liquidity_auction", "trade_location",
        "entry_confirmation", "trade_economics", "risk_management", "trade_execution",
    ],
}


def _num(x: Any) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    cur = values[0]
    out = [cur]
    for value in values[1:]:
        cur = alpha * value + (1.0 - alpha) * cur
        out.append(cur)
    return out


def _atr(bars: list[dict[str, Any]], period: int, start: int | None = None, end: int | None = None) -> float:
    segment = bars[start:end] if start is not None or end is not None else bars
    segment = segment[-period:]
    trs: list[float] = []
    previous_close: float | None = None
    for bar in segment:
        high, low, close = bar["high"], bar["low"], bar["close"]
        tr = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
        trs.append(tr)
        previous_close = close
    return mean(trs) if trs else 0.0


def _slope(values: list[float], atr: float, bars: int) -> float:
    if atr <= 0 or len(values) <= bars:
        return 0.0
    return (values[-1] - values[-1 - bars]) / atr


def _efficiency(values: list[float], bars: int) -> float:
    sample = values[-bars:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)


def _structure(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING : i + PIVOT_WING + 1]
        high, low = bars[i]["high"], bars[i]["low"]
        if high >= max(x["high"] for x in window):
            highs.append((i, high))
        if low <= min(x["low"] for x in window):
            lows.append((i, low))

    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i][1] > highs[i - 1][1] for i in range(1, len(highs)))
    lh = sum(highs[i][1] < highs[i - 1][1] for i in range(1, len(highs)))
    hl = sum(lows[i][1] > lows[i - 1][1] for i in range(1, len(lows)))
    ll = sum(lows[i][1] < lows[i - 1][1] for i in range(1, len(lows)))

    bullish_score = min(hh, hl)
    bearish_score = min(lh, ll)
    if bullish_score >= 2 and bullish_score > bearish_score:
        state, quality = "BULLISH", min(1.0, 0.62 + 0.07 * bullish_score)
    elif bearish_score >= 2 and bearish_score > bullish_score:
        state, quality = "BEARISH", min(1.0, 0.62 + 0.07 * bearish_score)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", 0.52
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", 0.52
    else:
        state, quality = "MIXED", 0.30

    last = bars[-1]["close"]
    recent_high = max((x[1] for x in highs), default=last)
    recent_low = min((x[1] for x in lows), default=last)
    buffer = max(0.10 * atr, 1e-12)
    bos_up = last > recent_high + buffer
    bos_down = last < recent_low - buffer
    bos = "CONFIRMED_BOS" if bos_up or bos_down else "NO_BOS"
    return {
        "state": state,
        "quality": quality,
        "counts": {"HH": hh, "HL": hl, "LH": lh, "LL": ll},
        "external_bos": bos,
        "bos_direction": "UP" if bos_up else "DOWN" if bos_down else "NONE",
        "recent_swing_high": recent_high,
        "recent_swing_low": recent_low,
    }


def _base() -> dict[str, Any]:
    return {
        "question": QUESTION,
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN",
    }


def _incomplete(reason: str, evidence: list[str], conflicts: list[str]) -> dict[str, Any]:
    professional = {
        "task": "DESCRIBE_MARKET_STATE_ONLY",
        "primary_state": "UNCLEAR",
        "market_state": "UNCLEAR",
        "direction": "NEUTRAL",
        "directional_pressure": "NEUTRAL",
        "directional_state": "UNRESOLVED",
        "trend_maturity": "UNRESOLVED",
        "trend_confirmed": False,
        "regime_stress": False,
        "transition_confirmed": False,
        "conflict_detected": bool(conflicts),
        "conflict_count": len(conflicts),
        "classification_reason": reason,
        "single_counter_candle": False,
        "pressure_score": 0.0,
        "structure_alignment": 0.0,
        "trend_score": 0.0,
        "directional_consensus": {"confirmed": False, "score": 0.0},
        "regime_basis": reason,
        "primary_thesis": {"direction": "NEUTRAL", "status": "UNRESOLVED", "supporting_evidence": [], "counter_evidence": [reason]},
        "counter_evidence": [reason],
        "invalidation": {"conditions": ["Reliable closed-candle data becomes insufficient"], "primary": "DATA_QUALITY_FAILURE"},
        "confidence_model": {"support": 0.0, "counter_evidence": 1.0, "structure": 0.0, "persistence": 0.0, "stability": 0.0},
        "state_stability": {"status": "UNRESOLVED", "score": 0.0},
        "independent_evidence": {"data_quality": evidence},
        "evidence_hierarchy": EVIDENCE_HIERARCHY,
        "ownership_boundaries": OWNERSHIP,
    }
    return {
        **_base(), "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL",
        "directional_state": "UNRESOLVED", "trend_state": "NONE", "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR", "structure_quality": 0.0, "range_state": "UNKNOWN",
        "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN",
        "regime_stress": "UNKNOWN", "confidence": 0.0, "evidence": evidence,
        "observations": evidence, "conflicts": conflicts, "reasons": [reason],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", "DATA -> insufficient reliable closed candles", f"STATE -> UNCLEAR because={reason}"],
        "professional_reasoning": professional, "analysis_status": "INCOMPLETE",
    }


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Classify market state from closed candles; never issue a trade action."""
    valid: list[dict[str, Any]] = []
    invalid = 0
    for raw in bars or []:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        values = {key: _num(raw.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            invalid += 1
            continue
        o, h, l, c = values["open"], values["high"], values["low"], values["close"]
        if h < l or h < max(o, c) or l > min(o, c):
            invalid += 1
            continue
        valid.append({**raw, **values})

    if len(valid) < MIN_BARS:
        return _incomplete(
            "insufficient reliable closed candles; classification withheld",
            [f"valid_candles={len(valid)}", f"minimum_required={MIN_BARS}"],
            ["DATA_QUALITY_ANOMALIES"] if invalid else [],
        )

    closes = [bar["close"] for bar in valid]
    atr14, atr50 = _atr(valid, 14), _atr(valid, 50)
    if atr14 <= 0 or atr50 <= 0:
        return _incomplete("ATR invalid; classification withheld", ["ATR_INVALID"], ["ATR_INVALID"])

    ema20_series, ema50_series = _ema(closes, 20), _ema(closes, 50)
    ema20, ema50 = ema20_series[-1], ema50_series[-1]
    ema_relation = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"
    ema_gap = (ema20 - ema50) / atr14
    ema20_slope, ema50_slope = _slope(ema20_series, atr14, 5), _slope(ema50_series, atr14, 5)

    horizons = (5, 10, 20, 40)
    thresholds = (0.15, 0.20, 0.30, 0.40)
    slopes = [_slope(closes, atr14, n) for n in horizons]
    horizon_states = ["UP" if slope >= threshold else "DOWN" if slope <= -threshold else "FLAT" for slope, threshold in zip(slopes, thresholds)]
    up_count, down_count = horizon_states.count("UP"), horizon_states.count("DOWN")
    long_states = horizon_states[1:]
    long_up, long_down = long_states.count("UP"), long_states.count("DOWN")

    if up_count == 4:
        pressure = "UP"
    elif down_count == 4:
        pressure = "DOWN"
    elif long_up > long_down:
        pressure = "UP"
    elif long_down > long_up:
        pressure = "DOWN"
    else:
        pressure = "BALANCED"

    consensus = max(up_count, down_count) / 4.0
    long_consensus = max(long_up, long_down) / 3.0
    if pressure == "UP":
        persistence = sum((slopes[0] >= .20, slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45)) / 4.0
        long_persistence = sum((slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45)) / 3.0
    elif pressure == "DOWN":
        persistence = sum((slopes[0] <= -.20, slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45)) / 4.0
        long_persistence = sum((slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45)) / 3.0
    else:
        persistence = long_persistence = 0.0

    eff10, eff20, eff40 = (_efficiency(closes, n) for n in (10, 20, 40))
    structure = _structure(valid, atr14)
    structure_direction = "UP" if structure["state"] == "BULLISH" else "DOWN" if structure["state"] == "BEARISH" else "NEUTRAL"
    structure_alignment = 1.0 if structure_direction == pressure and pressure != "BALANCED" else 0.75 if structure["state"] == "MIXED" and long_consensus >= .667 and long_persistence >= .667 else 0.5 if pressure == "BALANCED" and structure["state"] == "MIXED" else 0.0
    ema_alignment = 1.0 if pressure in {"UP", "DOWN"} and ema_relation == pressure else 0.0

    prior_atr = _atr(valid, 50, -64, -14) if len(valid) >= 64 else atr50
    volatility_ratio = atr14 / max(prior_atr, 1e-12)
    compression = volatility_ratio < 0.78
    expansion = volatility_ratio > 1.10
    volatility = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"

    pressure_score = consensus * (0.65 + 0.35 * persistence)
    trend_score = 0.25 * consensus + 0.25 * persistence + 0.20 * structure_alignment + 0.15 * ema_alignment + 0.10 * long_consensus + 0.05 * max(eff20, eff40)
    established_trend = pressure in {"UP", "DOWN"} and consensus >= .75 and persistence >= .50 and structure_alignment >= .75 and ema_alignment == 1.0 and max(eff20, eff40) >= .22
    contextual_trend = pressure in {"UP", "DOWN"} and long_consensus >= .667 and long_persistence >= .667 and structure_alignment >= .75 and ema_alignment == 1.0
    trend_candidate = established_trend or contextual_trend

    context_slope = _slope(closes, atr14, 30)
    recent_slope = _slope(closes, atr14, 8)
    context_flip = abs(context_slope) >= .45 and abs(recent_slope) >= .65 and (context_slope > 0) != (recent_slope > 0)
    structure_break = structure["external_bos"] == "CONFIRMED_BOS"
    bos_against_pressure = structure_break and pressure in {"UP", "DOWN"} and structure["bos_direction"] != pressure
    horizon_flip = up_count > 0 and down_count > 0 and consensus >= .75 and persistence >= .75
    ema_context_flip = ema_relation in {"UP", "DOWN"} and pressure in {"UP", "DOWN"} and ema_relation != pressure and context_flip
    ema_lag = ema_relation in {"UP", "DOWN"} and pressure in {"UP", "DOWN"} and ema_relation != pressure and consensus >= .75 and persistence >= .75 and (abs(slopes[1]) >= .20 or abs(slopes[2]) >= .30)

    transition_evidence = []
    if context_flip:
        transition_evidence.append("CONTEXT_FLIP")
    if structure_break:
        transition_evidence.append("STRUCTURE_BREAK")
    if bos_against_pressure:
        transition_evidence.append("STRUCTURE_BREAK_AGAINST_PRESSURE")
    if horizon_flip:
        transition_evidence.append("PERSISTENT_HORIZON_CONFLICT")
    if ema_context_flip:
        transition_evidence.append("EMA_CONTEXT_FLIP")
    if ema_lag:
        transition_evidence.append("EMA_LAG_WITH_PERSISTENT_PRESSURE")
    transition = not trend_candidate and (bos_against_pressure or ((context_flip or structure_break) and (horizon_flip or ema_context_flip)) or ema_lag)

    conflicts: list[str] = []
    if invalid:
        conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_relation in {"UP", "DOWN"} and pressure in {"UP", "DOWN"} and ema_relation != pressure:
        conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structure_direction in {"UP", "DOWN"} and pressure in {"UP", "DOWN"} and structure_direction != pressure:
        conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if up_count > 0 and down_count > 0:
        conflicts.append("SHORT_VS_LONG_HORIZON")
    if pressure == "BALANCED":
        conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")
    if context_flip:
        conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")
    if bos_against_pressure:
        conflicts.append("STRUCTURE_BREAK_VS_PRESSURE")

    single_counter_candle = False
    prior_pressure = "UP" if _slope(closes[:-1], atr14, 5) > .20 else "DOWN" if _slope(closes[:-1], atr14, 5) < -.20 else "NEUTRAL"
    last_direction = "UP" if valid[-1]["close"] > valid[-1]["open"] else "DOWN" if valid[-1]["close"] < valid[-1]["open"] else "FLAT"
    if prior_pressure in {"UP", "DOWN"} and last_direction in {"UP", "DOWN"} and last_direction != prior_pressure and not transition:
        single_counter_candle = True

    range_candidate = pressure == "BALANCED" and eff20 < .35 and eff40 < .40 and abs(ema_gap) < .85
    expansion_candidate = expansion and pressure in {"UP", "DOWN"} and eff10 >= .25 and abs(slopes[0]) >= .25

    if transition:
        state, reason, maturity = "TRANSITION", "repricing conflicts with the established market context", "TRANSITION"
    elif trend_candidate:
        state = "TREND_UP" if pressure == "UP" else "TREND_DOWN"
        reason = "structure, pressure, persistence, EMA context and efficiency are coherent" if established_trend else "slower-horizon structure and directional context are coherent"
        maturity = "ESTABLISHED" if established_trend else "DEVELOPING"
    elif compression and (pressure == "BALANCED" or eff20 < .30):
        state, reason, maturity = "COMPRESSION", "volatility contraction dominates directional evidence", "CONTRACTING"
    elif expansion_candidate:
        state, reason, maturity = "EXPANSION", "volatility is expanding with directional impulse", "EXPANDING"
    elif range_candidate:
        state, reason, maturity = "RANGE", "two-sided non-directional behavior dominates", "RANGE"
    elif pressure in {"UP", "DOWN"} and (persistence >= .25 or consensus >= .50):
        state, reason, maturity = "UNCLEAR", "directional pressure exists but independent regime confirmation is insufficient", "DIRECTIONAL_DEVELOPING"
    else:
        state, reason, maturity = "UNCLEAR", "evidence does not establish a dominant regime", "UNRESOLVED"

    direction = "UP" if pressure == "UP" else "DOWN" if pressure == "DOWN" else "NEUTRAL"
    label = "BULLISH" if direction == "UP" else "BEARISH" if direction == "DOWN" else "NEUTRAL"
    directional_state = (
        "CONFIRMED" if state in {"TREND_UP", "TREND_DOWN"}
        else "CONFLICTED" if transition
        else "DEVELOPING" if direction in {"UP", "DOWN"} and (consensus >= .50 or persistence >= .25)
        else "NEUTRAL" if direction == "NEUTRAL" else "UNRESOLVED"
    )

    # Professional reasoning: thesis first, then support, then disconfirming evidence.
    supporting: list[str] = []
    if direction != "NEUTRAL":
        if structure_direction == direction:
            supporting.append("STRUCTURE_ALIGNS")
        if ema_relation == direction:
            supporting.append("EMA_CONTEXT_ALIGNS")
        if long_consensus >= .667:
            supporting.append("LONG_HORIZONS_ALIGN")
        if long_persistence >= .667:
            supporting.append("LONG_HORIZON_PERSISTENCE")
        if max(eff20, eff40) >= .22:
            supporting.append("PRICE_EFFICIENCY_SUPPORTS_DIRECTION")
        if expansion:
            supporting.append("VOLATILITY_EXPANSION_SUPPORTS_REPRICING")

    counter: list[str] = []
    if structure_direction in {"UP", "DOWN"} and structure_direction != direction:
        counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if ema_relation in {"UP", "DOWN"} and ema_relation != direction:
        counter.append("EMA_DISAGREES_WITH_PRESSURE")
    if up_count > 0 and down_count > 0:
        counter.append("HORIZON_DISAGREEMENT")
    if context_flip:
        counter.append("RECENT_CONTEXT_FLIP")
    if structure_break and structure["bos_direction"] != direction and direction != "NEUTRAL":
        counter.append("STRUCTURE_BREAK_AGAINST_THESIS")
    if single_counter_candle:
        counter.append("SINGLE_COUNTER_CANDLE")
    if not counter:
        counter.append("NO_MATERIAL_COUNTER_EVIDENCE")

    # A state is stable only when multiple independent horizons agree and no strong disconfirming event exists.
    stability_support = (long_consensus + long_persistence + structure_alignment + ema_alignment) / 4.0
    stability_penalty = min(0.75, 0.15 * len([x for x in counter if x != "NO_MATERIAL_COUNTER_EVIDENCE"]))
    stability_score = max(0.0, min(1.0, stability_support - stability_penalty))
    stability_status = "STABLE" if stability_score >= .70 and not transition else "UNSTABLE" if stability_score < .45 or transition else "WATCH"

    support_score = max(0.0, min(1.0, (consensus + persistence + structure_alignment + ema_alignment + long_consensus) / 5.0))
    counter_score = max(0.0, min(1.0, len([x for x in counter if x != "NO_MATERIAL_COUNTER_EVIDENCE"]) / 5.0))
    confidence = 0.45 * support_score + 0.20 * structure["quality"] + 0.15 * stability_score + 0.10 * persistence + 0.10 * max(eff20, eff40) - 0.20 * counter_score
    if state == "UNCLEAR":
        confidence = min(confidence, .65)
    if transition:
        confidence = min(confidence, .80)
    confidence = max(0.0, min(.99, confidence))

    if direction == "UP":
        primary_invalidation = "PRICE_ACCEPTS_BELOW_THE_PROTECTED_BULLISH_STRUCTURE_OR_PRESSURE_REMAINS_PERSISTENTLY_DOWN"
        invalid_conditions = [
            "STRUCTURE_TURNS_BEARISH",
            "MULTI_HORIZON_PRESSURE_TURNS_DOWN_AND_PERSISTS",
            "EMA_CONTEXT_FLIPS_DOWN_WITH_CONFIRMING_STRUCTURE",
        ]
    elif direction == "DOWN":
        primary_invalidation = "PRICE_ACCEPTS_ABOVE_THE_PROTECTED_BEARISH_STRUCTURE_OR_PRESSURE_REMAINS_PERSISTENTLY_UP"
        invalid_conditions = [
            "STRUCTURE_TURNS_BULLISH",
            "MULTI_HORIZON_PRESSURE_TURNS_UP_AND_PERSISTS",
            "EMA_CONTEXT_FLIPS_UP_WITH_CONFIRMING_STRUCTURE",
        ]
    else:
        primary_invalidation = "A_DOMINANT_REGIME_IS_ESTABLISHED_BY_INDEPENDENT_EVIDENCE"
        invalid_conditions = [
            "PERSISTENT_MULTI_HORIZON_DIRECTIONAL_PRESSURE",
            "CONFIRMED_STRUCTURE_BREAK_WITH_ACCEPTANCE",
        ]

    thesis_status = "CONFIRMED" if state in {"TREND_UP", "TREND_DOWN"} and stability_status == "STABLE" else "DEVELOPING" if direction != "NEUTRAL" else "UNRESOLVED"
    thesis = {
        "direction": direction,
        "label": label,
        "status": thesis_status,
        "supporting_evidence": supporting,
        "counter_evidence": counter,
        "support_score": round(support_score, 3),
        "counter_score": round(counter_score, 3),
    }
    invalidation = {
        "primary": primary_invalidation,
        "conditions": invalid_conditions,
        "current_status": "VALID" if not transition else "UNDER_THREAT",
    }
    confidence_model = {
        "support": round(support_score, 3),
        "counter_evidence": round(counter_score, 3),
        "structure": round(structure_alignment, 3),
        "persistence": round(persistence, 3),
        "stability": round(stability_score, 3),
    }

    directional_consensus = {
        "direction": direction,
        "confirmed": consensus >= .75,
        "score": round(consensus, 3),
        "long_horizon_score": round(long_consensus, 3),
        "horizons": horizon_states,
        "up_count": up_count,
        "down_count": down_count,
        "state": directional_state,
    }
    independent_evidence = {
        "data_quality": {"valid_candles": len(valid), "invalid_candles": invalid},
        "structure": {**structure, "quality": round(structure["quality"], 3), "alignment": round(structure_alignment, 3)},
        "pressure": {"direction": direction, "score": round(pressure_score, 3), "state": directional_state},
        "persistence": {"score": round(persistence, 3), "long_horizon_score": round(long_persistence, 3), "efficiency20": round(eff20, 3), "efficiency40": round(eff40, 3)},
        "ema_context": {"relation": ema_relation, "gap_atr": round(ema_gap, 3), "ema20_slope_atr": round(ema20_slope, 3), "ema50_slope_atr": round(ema50_slope, 3), "alignment": round(ema_alignment, 3)},
        "volatility": {"atr14": round(atr14, 6), "prior_atr": round(prior_atr, 6), "ratio": round(volatility_ratio, 3)},
        "stability": {"score": round(stability_score, 3), "status": stability_status},
        "counter_evidence": counter,
        "invalidation": invalidation,
    }

    evidence = [
        f"valid_candles={len(valid)}", f"invalid_candles={invalid}",
        f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={ema_gap:.3f}",
        f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}",
        *(f"price_slope_{n}_atr={s:.3f}" for n, s in zip(horizons, slopes)),
        f"multi_horizon={','.join(horizon_states)}", f"directional_consensus={consensus:.3f}",
        f"long_horizon_consensus={long_consensus:.3f}", f"directional_state={directional_state}",
        f"persistence={persistence:.3f}", f"long_horizon_persistence={long_persistence:.3f}",
        f"efficiency20={eff20:.3f}", f"efficiency40={eff40:.3f}",
        f"structure_counts={structure['counts']}", f"structure_state={structure['state']}",
        f"structure_alignment={structure_alignment:.3f}", f"external_bos={structure['external_bos']}",
        f"pressure_score={pressure_score:.3f}", f"trend_score={trend_score:.3f}",
        f"volatility_ratio={volatility_ratio:.3f}", f"stability={stability_status}:{stability_score:.3f}",
        f"counter_evidence={counter}", f"invalidation={invalid_conditions}",
        f"transition_evidence={transition_evidence}", f"established_trend={established_trend}",
        f"contextual_trend={contextual_trend}", f"trend_candidate={trend_candidate}",
        f"regime_stress={'PRESENT' if (not transition and not trend_candidate and direction != 'NEUTRAL' and conflicts) else 'ABSENT'}",
        f"single_counter_candle={single_counter_candle}",
    ]

    regime_stress = not transition and not trend_candidate and direction in {"UP", "DOWN"} and bool(conflicts) and (consensus >= .50 or persistence >= .50)
    reasons = list(dict.fromkeys(conflicts))
    if transition:
        reasons.append("REGIME_TRANSITION_CONFIRMED")
    elif regime_stress:
        reasons.append("REGIME_STRESS_ACTIVE")
    elif directional_state == "DEVELOPING":
        reasons.append("DIRECTIONAL_STATE_DEVELOPING")
    elif state == "UNCLEAR":
        reasons.append("REGIME_CONFIRMATION_INSUFFICIENT")

    professional = {
        "task": "DESCRIBE_MARKET_STATE_ONLY",
        "primary_state": state,
        "market_state": state,
        "direction": direction,
        "directional_pressure": label,
        "directional_state": directional_state,
        "trend_maturity": maturity,
        "trend_confirmed": state in {"TREND_UP", "TREND_DOWN"},
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
        "primary_thesis": thesis,
        "counter_evidence": counter,
        "invalidation": invalidation,
        "confidence_model": confidence_model,
        "state_stability": {"status": stability_status, "score": round(stability_score, 3)},
        "regime_basis": f"pressure={direction}; consensus={consensus:.2f}; long_consensus={long_consensus:.2f}; persistence={persistence:.2f}; long_persistence={long_persistence:.2f}; structure={structure['state']}; ema={ema_relation}; volatility={volatility}; stability={stability_status}",
        "independent_evidence": independent_evidence,
        "evidence_hierarchy": EVIDENCE_HIERARCHY,
        "ownership_boundaries": OWNERSHIP,
    }

    trace = [
        f"QUESTION -> {QUESTION}",
        f"EVIDENCE_HIERARCHY -> {EVIDENCE_HIERARCHY}",
        f"STRUCTURE -> {structure['state']} quality={structure['quality']:.2f} alignment={structure_alignment:.2f}",
        f"PRESSURE -> {direction} score={pressure_score:.2f} state={directional_state}",
        f"PERSISTENCE -> {persistence:.2f} long={long_persistence:.2f}",
        f"VOLATILITY -> {volatility} ratio={volatility_ratio:.2f}",
        f"STABILITY -> {stability_status} score={stability_score:.2f}",
        f"THESIS -> {direction} status={thesis_status} support={support_score:.2f} counter={counter_score:.2f}",
        f"INVALIDATION -> {primary_invalidation}",
        f"REGIME_RECONCILIATION -> established={established_trend} contextual={contextual_trend}",
        f"STATE -> {state} because={reason}",
        f"TRANSITION -> {'PRESENT' if transition else 'ABSENT'} evidence={transition_evidence}",
    ]

    return {
        **_base(),
        "market_state": state,
        "directional_pressure": direction if contextual_trend and not established_trend else label,
        "directional_pressure_label": label,
        "directional_state": directional_state,
        "trend_state": "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE",
        "volatility_state": volatility,
        "structure_state": structure["state"],
        "structure_quality": round(structure["quality"], 3),
        "range_state": "RANGE" if range_candidate else "NOT_RANGE",
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": "PRESENT" if transition else "ABSENT",
        "regime_stress": "PRESENT" if regime_stress else "ABSENT",
        "confidence": round(confidence, 3),
        "evidence": evidence,
        "observations": evidence,
        "conflicts": conflicts,
        "reasons": reasons,
        "reasoning_trace": trace,
        "professional_reasoning": professional,
        "analysis_status": "COMPLETE",
    }
