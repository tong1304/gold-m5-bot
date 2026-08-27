"""E1 — Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It classifies market state from closed-candle OHLC evidence and never
authorizes a trade or calls E2-E9.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
QUESTION = "What is the market doing right now?"
MIN_BARS = 60
OWNERSHIP = {"owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "market_regime", "regime_transition"], "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution"]}

def _num(value: Any) -> float | None:
    try: value = float(value)
    except (TypeError, ValueError): return None
    return value if isfinite(value) else None

def _ema(values: list[float], period: int) -> list[float]:
    if not values: return []
    alpha = 2.0 / (period + 1.0); current = values[0]; result = [current]
    for value in values[1:]: current = alpha * value + (1.0 - alpha) * current; result.append(current)
    return result

def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    sample = bars[-period:]; trs: list[float] = []; previous_close: float | None = None
    for bar in sample:
        high, low, close = bar["high"], bar["low"], bar["close"]
        trs.append(max(0.0, high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))))
        previous_close = close
    return mean(trs) if trs else 0.0

def _slope(values: list[float], atr: float, lookback: int) -> float:
    if atr <= 0 or len(values) <= lookback: return 0.0
    return (values[-1] - values[-1 - lookback]) / atr

def _efficiency(values: list[float], lookback: int) -> float:
    sample = values[-lookback:]
    if len(sample) < 2: return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)

def _pivot_structure(bars: list[dict[str, Any]], wing: int = 2) -> tuple[str, float, dict[str, int]]:
    highs: list[float] = []; lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i-wing:i+wing+1]; high, low = bars[i]["high"], bars[i]["low"]
        if high >= max(x["high"] for x in window): highs.append(high)
        if low <= min(x["low"] for x in window): lows.append(low)
    highs, lows = highs[-6:], lows[-6:]
    hh = sum(highs[i] > highs[i-1] for i in range(1, len(highs))); lh = sum(highs[i] < highs[i-1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i-1] for i in range(1, len(lows))); ll = sum(lows[i] < lows[i-1] for i in range(1, len(lows)))
    bull, bear = min(hh, hl), min(lh, ll); counts = {"HH": hh, "HL": hl, "LH": lh, "LL": ll}
    if bull >= 2 and bull > bear: return "BULLISH", min(1.0, 0.62 + 0.09 * bull), counts
    if bear >= 2 and bear > bull: return "BEARISH", min(1.0, 0.62 + 0.09 * bear), counts
    directional_bull, directional_bear = hh + hl, lh + ll
    if directional_bull >= 2 and directional_bull > directional_bear: return "BULLISH", 0.52, counts
    if directional_bear >= 2 and directional_bear > directional_bull: return "BEARISH", 0.52, counts
    return "MIXED", 0.30, counts

def _base_result() -> dict[str, Any]:
    return {"question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY", "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN"}

def _incomplete(base: dict[str, Any], reason: str, evidence: list[str], conflicts: list[str] | None = None) -> dict[str, Any]:
    return {**base, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "structure_quality": 0.0, "range_state": "UNKNOWN", "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "regime_stress": "UNKNOWN", "confidence": 0.0, "evidence": evidence, "observations": evidence, "conflicts": conflicts or [], "reasons": [reason], "reasoning_trace": [f"QUESTION -> {QUESTION}", "DATA -> insufficient reliable evidence", f"STATE -> UNCLEAR because={reason}"], "professional_reasoning": {"task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "market_state": "UNCLEAR", "direction": "NEUTRAL", "directional_pressure": "NEUTRAL", "trend_maturity": "UNAVAILABLE", "trend_confirmed": False, "conflict_detected": bool(conflicts), "conflict_count": len(conflicts or []), "classification_reason": reason, "ownership_boundaries": OWNERSHIP}, "analysis_status": "INCOMPLETE"}

def _result(base: dict[str, Any], *, state: str, pressure: str, volatility: str, structure: str, structure_quality: float, compression: bool, expansion: bool, transition: bool, regime_stress: bool, confidence: float, evidence: list[str], conflicts: list[str], reason: str, maturity: str, trend_confirmed: bool, range_state: str) -> dict[str, Any]:
    direction = "UP" if pressure == "UP" else "DOWN" if pressure == "DOWN" else "NEUTRAL"; reasons = list(conflicts)
    if transition: reasons.append("REGIME_TRANSITION_CONFIRMED")
    elif regime_stress: reasons.append("REGIME_STRESS_ACTIVE")
    elif state == "UNCLEAR": reasons.append("REGIME_CONFIRMATION_INSUFFICIENT")
    return {**base, "market_state": state, "directional_pressure": direction, "trend_state": "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE", "volatility_state": volatility, "structure_state": structure, "structure_quality": round(structure_quality, 3), "range_state": range_state, "compression": "PRESENT" if compression else "ABSENT", "expansion": "PRESENT" if expansion else "ABSENT", "transition": "PRESENT" if transition else "ABSENT", "regime_stress": "PRESENT" if regime_stress else "ABSENT", "confidence": round(max(0.0, min(0.99, confidence)), 3), "evidence": evidence, "observations": evidence, "conflicts": conflicts, "reasons": reasons, "reasoning_trace": [f"QUESTION -> {QUESTION}", f"STRUCTURE -> {structure} quality={structure_quality:.2f}", f"PRESSURE -> {direction}", f"VOLATILITY -> {volatility}", f"REGIME_CONFIRMATION -> trend_confirmed={trend_confirmed} maturity={maturity}", f"REGIME_STRESS -> {'PRESENT' if regime_stress else 'ABSENT'}", f"STATE -> {state} because={reason}", f"TRANSITION -> {'PRESENT' if transition else 'ABSENT'}"], "professional_reasoning": {"task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": state, "market_state": state, "direction": direction, "directional_pressure": direction, "trend_maturity": maturity, "trend_confirmed": trend_confirmed, "regime_stress": regime_stress, "transition_confirmed": transition, "conflict_detected": bool(conflicts), "conflict_count": len(conflicts), "classification_reason": reason, "ownership_boundaries": OWNERSHIP}, "analysis_status": "COMPLETE"}

def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    base = _base_result(); valid: list[dict[str, Any]] = []; invalid_count = 0
    for raw in bars or []:
        if not isinstance(raw, dict): invalid_count += 1; continue
        values = {key: _num(raw.get(key)) for key in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()): invalid_count += 1; continue
        o, h, l, c = values["open"], values["high"], values["low"], values["close"]
        if h < l or h < max(o, c) or l > min(o, c): invalid_count += 1; continue
        valid.append({**raw, "open": o, "high": h, "low": l, "close": c})
    if len(valid) < MIN_BARS: return _incomplete(base, "insufficient reliable closed candles; classification withheld", [f"valid_candles={len(valid)}", f"minimum_required={MIN_BARS}"], ["DATA_QUALITY_ANOMALIES"] if invalid_count else [])
    closes = [b["close"] for b in valid]; atr14, atr50 = _atr(valid, 14), _atr(valid, 50)
    if atr14 <= 0 or atr50 <= 0: return _incomplete(base, "ATR invalid; classification withheld", ["ATR_INVALID"], ["ATR_INVALID"])
    ema20s, ema50s = _ema(closes, 20), _ema(closes, 50); ema20, ema50 = ema20s[-1], ema50s[-1]
    ema_relation = "UP" if ema20 > ema50 else "DOWN" if ema20 < ema50 else "FLAT"; ema_gap = (ema20 - ema50) / atr14
    ema20_slope, ema50_slope = _slope(ema20s, atr14, 5), _slope(ema50s, atr14, 5)
    slopes = [_slope(closes, atr14, n) for n in (5, 10, 20, 40)]; thresholds = [0.15, 0.20, 0.30, 0.40]
    horizons = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s, t in zip(slopes, thresholds)]; up, down = horizons.count("UP"), horizons.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "BALANCED"; consensus = max(up, down) / 4
    if pressure == "UP": aligned = sum((slopes[0] >= .20, slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45))
    elif pressure == "DOWN": aligned = sum((slopes[0] <= -.20, slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45))
    else: aligned = 0
    persistence = aligned / 4; eff10, eff20, eff40 = (_efficiency(closes, n) for n in (10, 20, 40))
    structure, structure_quality, pivot_counts = _pivot_structure(valid); structure_direction = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "NEUTRAL"
    ema_ok = pressure in {"UP", "DOWN"} and ema_relation == pressure and ((pressure == "UP" and ema20_slope >= -.05 and ema50_slope >= -.10) or (pressure == "DOWN" and ema20_slope <= .05 and ema50_slope <= .10))
    ema_conflict = pressure in {"UP", "DOWN"} and ema_relation in {"UP", "DOWN"} and ema_relation != pressure
    structure_conflict = pressure in {"UP", "DOWN"} and structure_direction in {"UP", "DOWN"} and structure_direction != pressure
    horizon_conflict = up > 0 and down > 0
    conflicts: list[str] = []
    if invalid_count: conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict: conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structure_conflict: conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict: conflicts.append("MULTI_HORIZON_DISAGREEMENT")
    if pressure == "BALANCED": conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")
    volatility_ratio = atr14 / atr50; compression, expansion = volatility_ratio < .78, volatility_ratio > 1.18; volatility = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"

    # Professional hierarchy: pressure is not a trend; disagreement is not a transition.
    trend_candidate = pressure in {"UP", "DOWN"} and consensus >= .75 and persistence >= .50 and ema_ok and abs(ema_gap) >= .10 and eff20 >= .22 and not ema_conflict and not structure_conflict and (structure_direction == pressure or persistence >= .75)
    prior_context = _slope(closes, atr14, 30); recent_context = _slope(closes, atr14, 8)
    context_flip = abs(prior_context) >= .45 and abs(recent_context) >= .65 and (prior_context > 0) != (recent_context > 0)
    structure_break_proxy = structure_conflict and persistence >= .75 and structure_quality >= .52
    persistent_horizon_flip = horizon_conflict and consensus >= .75 and persistence >= .75
    ema_context_flip = ema_conflict and context_flip and persistence >= .50
    transition_evidence = [x for x, ok in (("CONTEXT_FLIP", context_flip), ("STRUCTURE_BREAK_PROXY", structure_break_proxy), ("PERSISTENT_HORIZON_FLIP", persistent_horizon_flip), ("EMA_CONTEXT_FLIP", ema_context_flip)) if ok]
    hard_anchor = context_flip or structure_break_proxy; corroboration = persistent_horizon_flip or ema_context_flip or structure_break_proxy
    transition = not trend_candidate and hard_anchor and corroboration
    regime_stress = not transition and not trend_candidate and pressure in {"UP", "DOWN"} and (ema_conflict or structure_conflict or horizon_conflict) and (consensus >= .50 or persistence >= .50)
    if context_flip: conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")

    range_candidate = pressure == "BALANCED" and eff20 < .35 and eff40 < .40 and abs(ema_gap) < .85
    expansion_candidate = expansion and pressure in {"UP", "DOWN"} and eff10 >= .25 and abs(slopes[0]) >= .25
    if transition: state, reason, maturity = "TRANSITION", "prior regime is demonstrably breaking with corroborating evidence", "TRANSITION"
    elif trend_candidate: state, reason, maturity = ("TREND_UP" if pressure == "UP" else "TREND_DOWN"), "direction, persistence, EMA context and structure are coherent", "ESTABLISHED"
    elif compression and (pressure == "BALANCED" or eff20 < .30): state, reason, maturity = "COMPRESSION", "volatility contraction dominates directional evidence", "CONTRACTING"
    elif expansion_candidate: state, reason, maturity = "EXPANSION", "volatility is expanding with directional impulse", "EXPANDING"
    elif range_candidate: state, reason, maturity = "RANGE", "two-sided non-directional behavior dominates", "RANGE"
    elif pressure in {"UP", "DOWN"} and (persistence >= .25 or consensus >= .50): state, reason, maturity = "UNCLEAR", "directional pressure exists but regime confirmation is insufficient", "DEVELOPING"
    else: state, reason, maturity = "UNCLEAR", "evidence does not establish a dominant regime", "UNRESOLVED"
    evidence = [f"valid_candles={len(valid)}", f"invalid_candles={invalid_count}", f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={ema_gap:.3f}", f"ema20_slope_atr={ema20_slope:.3f}", f"ema50_slope_atr={ema50_slope:.3f}", *(f"price_slope_{n}_atr={s:.3f}" for n, s in zip((5,10,20,40), slopes)), f"multi_horizon={','.join(horizons)}", f"directional_consensus={consensus:.3f}", f"persistence={persistence:.3f}", f"efficiency20={eff20:.3f}", f"structure_counts={pivot_counts}", f"context_flip={context_flip}", f"transition_evidence={transition_evidence}", f"trend_candidate={trend_candidate}", f"regime_stress={regime_stress}"]
    confidence = .35 + .25 * structure_quality + .20 * consensus + .20 * persistence
    if state == "UNCLEAR": confidence = min(confidence, .65)
    return _result(base, state=state, pressure=pressure, volatility=volatility, structure=structure, structure_quality=structure_quality, compression=compression, expansion=expansion, transition=transition, regime_stress=regime_stress, confidence=confidence, evidence=evidence, conflicts=conflicts, reason=reason, maturity=maturity, trend_confirmed=state in {"TREND_UP", "TREND_DOWN"}, range_state="RANGE" if range_candidate else "NOT_RANGE")
