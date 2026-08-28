"""E1 Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It uses closed-candle OHLC evidence, reconciles independent evidence,
and never authorizes a trade or calls E2-E9.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> VOLATILITY -> STABILITY -> COUNTER_EVIDENCE -> STATE -> TRANSITION"
OWNERSHIP = {
    "owns": [
        "data_integrity", "volatility_regime", "market_structure_context",
        "directional_pressure", "multi_horizon_alignment", "trend_persistence",
        "market_regime", "regime_transition", "state_stability", "counter_evidence",
        "market_state_thesis", "market_state_invalidation",
    ],
    "does_not_own": [
        "opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation",
        "trade_economics", "risk_management", "trade_execution",
    ],
}


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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


def _atr(bars: list[dict[str, Any]], period: int, start: int | None = None, end: int | None = None) -> float:
    sample = bars[start:end] if start is not None or end is not None else bars
    sample = sample[-period:]
    trs: list[float] = []
    previous_close: float | None = None
    for bar in sample:
        high, low, close = bar["high"], bar["low"], bar["close"]
        tr = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
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


def _base_result() -> dict[str, Any]:
    return {
        "question": QUESTION,
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN",
    }


def _incomplete(reason: str, evidence: list[str], conflicts: list[str] | None = None) -> dict[str, Any]:
    conflicts = conflicts or []
    return {
        **_base_result(),
        "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "directional_pressure_label": "NEUTRAL",
        "directional_state": "UNRESOLVED", "trend_state": "NONE", "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR", "structure_quality": 0.0, "range_state": "UNKNOWN",
        "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "regime_stress": "UNKNOWN",
        "confidence": 0.0, "evidence": evidence, "observations": evidence, "conflicts": conflicts,
        "reasons": [reason],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", "1A DATA_QUALITY -> insufficient", "STATE -> UNCLEAR"],
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "market_state": "UNCLEAR",
            "direction": "NEUTRAL", "directional_pressure": "NEUTRAL", "directional_state": "UNRESOLVED",
            "trend_maturity": "UNAVAILABLE", "trend_confirmed": False, "transition_confirmed": False,
            "conflict_detected": bool(conflicts), "conflict_count": len(conflicts),
            "classification_reason": reason, "counter_evidence": [reason],
            "confidence_model": {"evidence_strength": 0.0, "evidence_agreement": 0.0, "counter_evidence": 1.0, "stability": 0.0},
            "ownership_boundaries": OWNERSHIP,
        },
        "analysis_status": "INCOMPLETE",
    }


def _data_quality(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
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
        valid.append({**raw, "open": o, "high": h, "low": l, "close": c})
    return {"valid": valid, "valid_candles": len(valid), "invalid_candles": invalid,
            "sufficient": len(valid) >= MIN_BARS, "quality": _clamp(len(valid) / max(len(valid) + invalid, 1))}


def _measure(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [bar["close"] for bar in bars]
    atr14, atr50 = _atr(bars, 14), _atr(bars, 50)
    ema20s, ema50s = _ema(closes, 20), _ema(closes, 50)
    ema_relation = "UP" if ema20s[-1] > ema50s[-1] else "DOWN" if ema20s[-1] < ema50s[-1] else "FLAT"
    ema_gap = (ema20s[-1] - ema50s[-1]) / max(atr14, 1e-12)
    horizons = (5, 10, 20, 40)
    thresholds = (0.15, 0.20, 0.30, 0.40)
    slopes = [_slope(closes, atr14, n) for n in horizons]
    states = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s, t in zip(slopes, thresholds)]
    up, down = states.count("UP"), states.count("DOWN")
    long_states = states[1:]
    long_up, long_down = long_states.count("UP"), long_states.count("DOWN")
    if up > down:
        pressure = "UP"
    elif down > up:
        pressure = "DOWN"
    else:
        pressure = "BALANCED"
    consensus = max(up, down) / 4.0
    long_consensus = max(long_up, long_down) / 3.0
    if pressure == "UP":
        persistence = sum((slopes[0] >= .20, slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45)) / 4.0
        long_persistence = sum((slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45)) / 3.0
    elif pressure == "DOWN":
        persistence = sum((slopes[0] <= -.20, slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45)) / 4.0
        long_persistence = sum((slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45)) / 3.0
    else:
        persistence = long_persistence = 0.0
    prior_atr = _atr(bars, 50, -64, -14) if len(bars) >= 64 else atr50
    volatility_ratio = atr14 / max(prior_atr, 1e-12)
    context_slope, recent_slope = _slope(closes, atr14, 30), _slope(closes, atr14, 8)
    context_flip = abs(context_slope) >= .45 and abs(recent_slope) >= .65 and (context_slope > 0) != (recent_slope > 0)
    prior_pressure_slope = _slope(closes[:-1], atr14, 5)
    prior_pressure = "UP" if prior_pressure_slope > .20 else "DOWN" if prior_pressure_slope < -.20 else "NEUTRAL"
    last_candle = "UP" if bars[-1]["close"] > bars[-1]["open"] else "DOWN" if bars[-1]["close"] < bars[-1]["open"] else "FLAT"
    return {
        "closes": closes, "atr14": atr14, "atr50": atr50, "ema20": ema20s, "ema50": ema50s,
        "ema_relation": ema_relation, "ema_gap": ema_gap, "ema20_slope": _slope(ema20s, atr14, 5),
        "ema50_slope": _slope(ema50s, atr14, 5), "horizons": horizons, "slopes": slopes,
        "horizon_states": states, "up": up, "down": down, "long_up": long_up, "long_down": long_down,
        "pressure": pressure, "consensus": consensus, "long_consensus": long_consensus,
        "persistence": persistence, "long_persistence": long_persistence,
        "eff10": _efficiency(closes, 10), "eff20": _efficiency(closes, 20), "eff40": _efficiency(closes, 40),
        "prior_atr": prior_atr, "volatility_ratio": volatility_ratio, "context_slope": context_slope,
        "recent_slope": recent_slope, "context_flip": context_flip, "prior_pressure": prior_pressure,
        "single_counter_candle": prior_pressure in {"UP", "DOWN"} and last_candle in {"UP", "DOWN"} and prior_pressure != last_candle,
    }


def _structure(bars: list[dict[str, Any]], m: dict[str, Any]) -> dict[str, Any]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING:i + PIVOT_WING + 1]
        if bars[i]["high"] >= max(x["high"] for x in window): highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window): lows.append((i, bars[i]["low"]))
    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i][1] > highs[i - 1][1] for i in range(1, len(highs)))
    lh = sum(highs[i][1] < highs[i - 1][1] for i in range(1, len(highs)))
    hl = sum(lows[i][1] > lows[i - 1][1] for i in range(1, len(lows)))
    ll = sum(lows[i][1] < lows[i - 1][1] for i in range(1, len(lows)))
    bullish_pairs, bearish_pairs = min(hh, hl), min(lh, ll)
    if bullish_pairs >= 2 and bullish_pairs > bearish_pairs:
        state, quality = "BULLISH", min(1.0, .62 + .07 * bullish_pairs)
    elif bearish_pairs >= 2 and bearish_pairs > bullish_pairs:
        state, quality = "BEARISH", min(1.0, .62 + .07 * bearish_pairs)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", .52
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", .52
    else:
        state, quality = "MIXED", .30
    direction = "UP" if state == "BULLISH" else "DOWN" if state == "BEARISH" else "NEUTRAL"
    last = bars[-1]["close"]
    recent_high = max((x[1] for x in highs), default=last)
    recent_low = min((x[1] for x in lows), default=last)
    buffer = max(.15 * m["atr14"], 1e-12)
    above = last > recent_high + buffer
    below = last < recent_low - buffer
    # A structural break is confirmed only after acceptance: two closed candles
    # beyond the protected swing. One close is treated as a probe, not repricing.
    prior_close = bars[-2]["close"] if len(bars) >= 2 else last
    accepted_up = above and prior_close > recent_high + buffer
    accepted_down = below and prior_close < recent_low - buffer
    probe_up = above and not accepted_up
    probe_down = below and not accepted_down
    failed_up = probe_up and last <= recent_high
    failed_down = probe_down and last >= recent_low
    bos_direction = "UP" if accepted_up else "DOWN" if accepted_down else "NONE"
    return {
        "state": state, "direction": direction, "quality": quality,
        "counts": {"HH": hh, "HL": hl, "LH": lh, "LL": ll},
        "external_bos": "CONFIRMED_BOS" if bos_direction != "NONE" else "NO_BOS",
        "bos_direction": bos_direction, "recent_swing_high": recent_high, "recent_swing_low": recent_low,
        "protected_high": recent_high, "protected_low": recent_low, "break_buffer_atr": .15,
        "acceptance": "UP" if accepted_up else "DOWN" if accepted_down else "NONE",
        "break_probe": "UP" if probe_up else "DOWN" if probe_down else "NONE",
        "failed_break": "UP" if failed_up else "DOWN" if failed_down else "NONE",
        "structure_quality": quality,
    }


def _volatility(m: dict[str, Any]) -> dict[str, Any]:
    ratio = m["volatility_ratio"]
    state = "EXPANDING" if ratio > 1.10 else "CONTRACTING" if ratio < .78 else "NORMAL"
    return {"state": state, "ratio": ratio, "atr14": m["atr14"], "prior_atr": m["prior_atr"]}


def _range(m: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    balance = 1.0 if m["pressure"] == "BALANCED" else 0.0
    efficiency = 1.0 - _clamp((m["eff20"] + m["eff40"]) / .90)
    structure_weak = 1.0 - _clamp(t["quality"] / .70)
    ema_neutral = 1.0 - _clamp(abs(m["ema_gap"]) / 1.20)
    score = _clamp(.35 * balance + .30 * efficiency + .20 * structure_weak + .15 * ema_neutral)
    confirmed = score >= .62 and m["eff20"] < .40 and m["eff40"] < .45 and abs(m["ema_gap"]) < 1.0
    return {"state": "RANGE" if confirmed else "NOT_RANGE", "score": score,
            "behavior": "BALANCED_ROTATION" if confirmed else "NOT_CONFIRMED"}


def _compression(m: dict[str, Any], v: dict[str, Any]) -> dict[str, Any]:
    atr_contraction = _clamp((.90 - m["volatility_ratio"]) / .20)
    efficiency_contraction = _clamp((.55 - max(m["eff20"], m["eff40"])) / .55)
    directional_balance = 1.0 if m["pressure"] == "BALANCED" else 1.0 - m["consensus"]
    confirmed = v["state"] == "CONTRACTING" and m["volatility_ratio"] < .82 and directional_balance >= .25 and max(m["eff20"], m["eff40"]) < .55
    score = _clamp(.55 * atr_contraction + .25 * efficiency_contraction + .20 * directional_balance)
    return {"state": "CONFIRMED" if confirmed else "ABSENT", "score": score,
            "behavior": "ENERGY_BUILD" if confirmed else "NONE"}


def _expansion(m: dict[str, Any], v: dict[str, Any], compression: dict[str, Any]) -> dict[str, Any]:
    displacement = _clamp(abs(m["slopes"][0]) / .80)
    efficiency = _clamp(m["eff10"] / .45)
    directional = m["consensus"] if m["pressure"] in {"UP", "DOWN"} else 0.0
    directional_confirmed = v["state"] == "EXPANDING" and m["eff10"] >= .25 and abs(m["slopes"][0]) >= .25 and directional >= .50
    shock = v["state"] == "EXPANDING" and not directional_confirmed
    score = _clamp(.40 * _clamp((m["volatility_ratio"] - 1.05) / .35) + .25 * displacement + .20 * efficiency + .15 * directional)
    origin = "AFTER_COMPRESSION" if compression["state"] == "CONFIRMED" else "UNCONFIRMED_ORIGIN"
    return {"state": "CONFIRMED" if directional_confirmed else "ABSENT", "score": score,
            "behavior": "DIRECTIONAL_EXPANSION" if directional_confirmed else "VOLATILITY_SHOCK" if shock else "NONE",
            "directional": directional_confirmed, "shock": shock, "origin": origin}


def _transition(m: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    pressure, structure = m["pressure"], t["direction"]
    structural_repricing = t["external_bos"] == "CONFIRMED_BOS" and structure in {"UP", "DOWN"} and pressure in {"UP", "DOWN"} and structure != pressure
    context_flip = m["context_flip"]
    persistent_flip = m["consensus"] >= .75 and m["persistence"] >= .75 and m["long_consensus"] >= .667
    ema_lag = (m["ema_relation"] in {"UP", "DOWN"} and pressure in {"UP", "DOWN"}
               and m["ema_relation"] != pressure and m["persistence"] >= .75
               and (abs(m["slopes"][1]) >= .20 or abs(m["slopes"][2]) >= .30))
    early = context_flip and persistent_flip
    confirmed = structural_repricing and persistent_flip and context_flip
    if confirmed:
        stage = "CONFIRMED"
    elif early or ema_lag:
        stage = "DEVELOPING"
    else:
        stage = "ABSENT"
    evidence = []
    if context_flip: evidence.append("CONTEXT_FLIP")
    if t["external_bos"] == "CONFIRMED_BOS": evidence.append("STRUCTURE_BREAK_ACCEPTED")
    if t["break_probe"] != "NONE": evidence.append("STRUCTURE_BREAK_PROBE")
    if t["failed_break"] != "NONE": evidence.append("FAILED_BREAK")
    if persistent_flip: evidence.append("PERSISTENT_MULTI_HORIZON_REPRICING")
    if ema_lag: evidence.append("EMA_LAG_WITH_PERSISTENT_PRESSURE")
    if confirmed: evidence.append("STRUCTURAL_REPRICING_CONFIRMED")
    return {"state": "CONFIRMED" if confirmed else "DEVELOPING" if stage == "DEVELOPING" else "ABSENT",
            "confirmed": confirmed, "stage": stage, "structural_repricing": structural_repricing,
            "context_flip": context_flip, "persistent_flip": persistent_flip,
            "evidence": evidence, "direction": pressure if pressure in {"UP", "DOWN"} else structure}


def _reconcile(m: dict[str, Any], t: dict[str, Any], v: dict[str, Any], r: dict[str, Any], c: dict[str, Any], e: dict[str, Any], tr: dict[str, Any]) -> dict[str, Any]:
    pressure, structure = m["pressure"], t["direction"]
    conflicts: list[str] = []
    counter: list[str] = []
    if pressure in {"UP", "DOWN"} and structure in {"UP", "DOWN"} and pressure != structure:
        conflicts.append("STRUCTURE_VS_PRESSURE")
        counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if pressure in {"UP", "DOWN"} and m["ema_relation"] in {"UP", "DOWN"} and m["ema_relation"] != pressure:
        conflicts.append("EMA_VS_PRESSURE")
        counter.append("EMA_DISAGREES_WITH_PRESSURE")
    if m["up"] > 0 and m["down"] > 0:
        conflicts.append("MULTI_HORIZON_DISAGREEMENT")
        counter.append("MULTI_HORIZON_NOT_FULLY_ALIGNED")
    if m["context_flip"]:
        conflicts.append("RECENT_CONTEXT_FLIP")
        counter.append("RECENT_CONTEXT_FLIP")
    if t["failed_break"] != "NONE":
        conflicts.append("FAILED_STRUCTURE_BREAK")
        counter.append("FAILED_STRUCTURE_BREAK")
    if m["single_counter_candle"]:
        counter.append("SINGLE_COUNTER_CANDLE")
    if not counter:
        counter = ["NO_MATERIAL_COUNTER_EVIDENCE"]

    # Structure is the anchor for trend identity; pressure describes current force.
    # A trend is established only when structure, long-horizon direction and persistence agree.
    structural_direction = structure if structure in {"UP", "DOWN"} else "NEUTRAL"
    trend_aligned = (
        structural_direction in {"UP", "DOWN"}
        and pressure == structural_direction
        and m["long_consensus"] >= .667
        and m["long_persistence"] >= .667
        and t["quality"] >= .52
    )
    trend_developing = (
        structural_direction in {"UP", "DOWN"}
        and pressure == structural_direction
        and m["consensus"] >= .50
        and m["persistence"] >= .50
    )

    if tr["confirmed"]:
        state, maturity, reason = "TRANSITION", "TRANSITION", "accepted structural repricing is confirmed against prior context"
    elif e["state"] == "CONFIRMED" and not trend_aligned:
        state, maturity, reason = "EXPANSION", "directional volatility expansion has displacement and multi-horizon support"
    elif c["state"] == "CONFIRMED" and not trend_aligned:
        state, maturity, reason = "COMPRESSION", "volatility is contracting while directional travel is inefficient"
    elif r["state"] == "RANGE" and not trend_aligned:
        state, maturity, reason = "RANGE", "price is rotating with balanced pressure and weak directional efficiency"
    elif trend_aligned:
        state, maturity, reason = ("TREND_UP" if structural_direction == "UP" else "TREND_DOWN"), "ESTABLISHED", "structure, pressure, long-horizon alignment and persistence agree"
    elif trend_developing:
        state, maturity, reason = ("TREND_UP" if structural_direction == "UP" else "TREND_DOWN"), "DEVELOPING", "directional structure and pressure agree but confirmation is incomplete"
    else:
        state, maturity, reason = "UNCLEAR", "UNRESOLVED", "independent evidence does not establish a dominant market state"

    dominant_direction = structural_direction if structural_direction in {"UP", "DOWN"} and (trend_developing or trend_aligned) else pressure if pressure in {"UP", "DOWN"} else "NEUTRAL"
    evidence_strength = _clamp(.35 * t["quality"] + .25 * m["long_persistence"] + .20 * m["long_consensus"] + .20 * max(m["eff20"], m["eff40"]))
    agreement = _clamp(.35 * (1.0 if pressure == structural_direction and pressure != "BALANCED" else 0.0) + .30 * m["long_consensus"] + .35 * m["long_persistence"])
    counter_score = _clamp(len([x for x in counter if x != "NO_MATERIAL_COUNTER_EVIDENCE"]) / 5.0)
    conflict_penalty = _clamp(len(conflicts) / 5.0)
    stability = _clamp(.45 * m["long_consensus"] + .40 * m["long_persistence"] + .15 * (1.0 - conflict_penalty))
    stability_status = "STABLE" if stability >= .70 and not tr["confirmed"] else "UNSTABLE" if stability < .45 or tr["confirmed"] else "WATCH"
    fit = {"TREND_UP": 1.0 if dominant_direction == "UP" else 0.0, "TREND_DOWN": 1.0 if dominant_direction == "DOWN" else 0.0,
           "RANGE": r["score"], "COMPRESSION": c["score"], "EXPANSION": e["score"],
           "TRANSITION": .85 if tr["confirmed"] else 0.0, "UNCLEAR": .40}[state]
    confidence = _clamp(.35 * evidence_strength + .25 * agreement + .20 * stability + .20 * fit - .25 * counter_score - .15 * conflict_penalty)
    if state == "UNCLEAR": confidence = min(confidence, .60)
    if tr["confirmed"]: confidence = min(confidence, .80)
    directional_state = "CONFIRMED" if maturity == "ESTABLISHED" else "DEVELOPING" if dominant_direction in {"UP", "DOWN"} else "NEUTRAL"
    return {
        "state": state, "direction": dominant_direction, "maturity": maturity, "directional_state": directional_state,
        "reason": reason, "counter": counter, "conflicts": list(dict.fromkeys(conflicts + [x for x in counter if x != "NO_MATERIAL_COUNTER_EVIDENCE"])),
        "support": round(evidence_strength, 3), "agreement": round(agreement, 3), "counter_score": round(counter_score, 3),
        "stability": round(stability, 3), "stability_status": stability_status, "confidence": round(confidence, 3),
    }


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Run the complete E1 reasoning chain on closed-candle data only."""
    quality = _data_quality(bars)
    if not quality["sufficient"]:
        return _incomplete(
            "insufficient reliable closed candles; classification withheld",
            [f"valid_candles={quality['valid_candles']}", f"invalid_candles={quality['invalid_candles']}", f"minimum_required={MIN_BARS}"],
            ["DATA_QUALITY_ANOMALIES"] if quality["invalid_candles"] else [],
        )
    valid = quality["valid"]
    m = _measure(valid)
    if m["atr14"] <= 0 or m["atr50"] <= 0:
        return _incomplete("ATR invalid; classification withheld", ["ATR_INVALID"], ["ATR_INVALID"])

    v = _volatility(m)
    t = _structure(valid, m)
    r = _range(m, t)
    c = _compression(m, v)
    e = _expansion(m, v, c)
    tr = _transition(m, t)
    q = _reconcile(m, t, v, r, c, e, tr)

    state, direction = q["state"], q["direction"]
    label = "BULLISH" if direction == "UP" else "BEARISH" if direction == "DOWN" else "NEUTRAL"
    structure_alignment = 1.0 if t["direction"] == direction and direction != "NEUTRAL" else 0.0
    ema_alignment = 1.0 if direction in {"UP", "DOWN"} and m["ema_relation"] == direction else 0.0
    pressure_score = round(m["consensus"] * (.65 + .35 * m["persistence"]), 3)
    trend_score = round(.30 * m["consensus"] + .25 * m["persistence"] + .25 * structure_alignment + .10 * ema_alignment + .10 * m["long_consensus"], 3)
    invalidation = (
        "PRICE_ACCEPTS_BELOW_PROTECTED_BULLISH_STRUCTURE_OR_PRESSURE_REMAINS_PERSISTENTLY_DOWN" if direction == "UP"
        else "PRICE_ACCEPTS_ABOVE_PROTECTED_BEARISH_STRUCTURE_OR_PRESSURE_REMAINS_PERSISTENTLY_UP" if direction == "DOWN"
        else "A_DOMINANT_REGIME_IS_ESTABLISHED_BY_INDEPENDENT_EVIDENCE"
    )
    invalidation_conditions = (
        ["STRUCTURE_TURNS_BEARISH", "MULTI_HORIZON_PRESSURE_TURNS_DOWN_AND_PERSISTS", "EMA_CONTEXT_FLIPS_DOWN_WITH_CONFIRMING_STRUCTURE"] if direction == "UP"
        else ["STRUCTURE_TURNS_BULLISH", "MULTI_HORIZON_PRESSURE_TURNS_UP_AND_PERSISTS", "EMA_CONTEXT_FLIPS_UP_WITH_CONFIRMING_STRUCTURE"] if direction == "DOWN"
        else ["PERSISTENT_MULTI_HORIZON_DIRECTIONAL_PRESSURE", "CONFIRMED_STRUCTURE_BREAK_WITH_ACCEPTANCE"]
    )
    thesis = {
        "direction": direction, "label": label,
        "status": "CONFIRMED" if state in {"TREND_UP", "TREND_DOWN"} and q["maturity"] == "ESTABLISHED" else "DEVELOPING" if direction != "NEUTRAL" else "UNRESOLVED",
        "supporting_evidence": ["STRUCTURE_ALIGNS", "PRESSURE_ALIGNS", "LONG_HORIZON_PERSISTENCE"] if structure_alignment else [],
        "counter_evidence": q["counter"], "support_score": q["support"], "counter_score": q["counter_score"],
    }
    evidence = [
        f"valid_candles={quality['valid_candles']}", f"invalid_candles={quality['invalid_candles']}",
        f"ema20_vs_ema50={m['ema_relation']}", f"ema_gap_atr={m['ema_gap']:.3f}",
        *(f"price_slope_{n}_atr={s:.3f}" for n, s in zip(m["horizons"], m["slopes"])),
        f"multi_horizon={','.join(m['horizon_states'])}", f"directional_consensus={m['consensus']:.3f}",
        f"long_horizon_consensus={m['long_consensus']:.3f}", f"persistence={m['persistence']:.3f}",
        f"long_horizon_persistence={m['long_persistence']:.3f}", f"structure_state={t['state']}",
        f"structure_quality={t['quality']:.3f}", f"external_bos={t['external_bos']}",
        f"acceptance={t['acceptance']}", f"break_probe={t['break_probe']}", f"failed_break={t['failed_break']}",
        f"volatility_ratio={m['volatility_ratio']:.3f}", f"compression={c['state']}:{c['score']:.3f}",
        f"expansion={e['behavior']}:{e['score']:.3f}", f"transition={tr['state']}",
        f"stability={q['stability_status']}:{q['stability']:.3f}", f"counter_evidence={q['counter']}",
    ]
    independent = {
        "1A_data_quality": {"valid_candles": quality["valid_candles"], "invalid_candles": quality["invalid_candles"], "quality": round(quality["quality"], 3)},
        "1B_volatility": v, "1C_trend": t, "1D_range": r, "1E_compression": c, "1F_expansion": e, "1G_transition": tr,
        "data_quality": {"valid_candles": quality["valid_candles"], "invalid_candles": quality["invalid_candles"]},
        "structure": {**t, "alignment": structure_alignment},
        "pressure": {"direction": direction, "score": pressure_score, "state": q["directional_state"]},
        "persistence": {"score": round(m["persistence"], 3), "long_horizon_score": round(m["long_persistence"], 3), "efficiency20": round(m["eff20"], 3), "efficiency40": round(m["eff40"], 3)},
        "ema_context": {"relation": m["ema_relation"], "gap_atr": round(m["ema_gap"], 3), "ema20_slope_atr": round(m["ema20_slope"], 3), "ema50_slope_atr": round(m["ema50_slope"], 3), "alignment": ema_alignment},
        "volatility": {"atr14": round(m["atr14"], 6), "prior_atr": round(m["prior_atr"], 6), "ratio": round(m["volatility_ratio"], 3)},
        "stability": {"score": q["stability"], "status": q["stability_status"]},
        "counter_evidence": q["counter"], "invalidation": {"primary": invalidation, "conditions": invalidation_conditions},
    }
    trace = [
        f"QUESTION -> {QUESTION}", f"1A DATA_QUALITY -> VALID {quality['valid_candles']}/{quality['valid_candles'] + quality['invalid_candles']}",
        f"1B VOLATILITY -> {v['state']} ratio={m['volatility_ratio']:.2f}",
        f"1C TREND -> structure={t['state']} quality={t['quality']:.2f} pressure={m['pressure']} persistence={m['persistence']:.2f}",
        f"1D RANGE -> {r['state']} score={r['score']:.2f}", f"1E COMPRESSION -> {c['state']} score={c['score']:.2f}",
        f"1F EXPANSION -> {e['behavior']} score={e['score']:.2f}", f"1G TRANSITION -> {tr['state']} evidence={tr['evidence']}",
        f"RECONCILIATION -> dominant={state} direction={direction} evidence_strength={q['support']:.2f} agreement={q['agreement']:.2f} counter={q['counter_score']:.2f}",
        f"CONFLICTS -> {q['conflicts']}", f"STABILITY -> {q['stability_status']} score={q['stability']:.2f}",
        f"CONFIDENCE -> {q['confidence']:.3f} (market-state confidence, not trade probability)",
        f"STATE -> {state} because={q['reason']}", f"INVALIDATION -> {invalidation}",
    ]
    return {
        **_base_result(),
        "market_state": state, "directional_pressure": direction, "directional_pressure_label": label,
        "directional_state": q["directional_state"], "trend_state": "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE",
        "volatility_state": v["state"], "structure_state": t["state"], "structure_quality": round(t["quality"], 3),
        "range_state": r["state"], "compression": c["state"], "expansion": e["state"],
        "transition": "PRESENT" if tr["confirmed"] else "ABSENT", "regime_stress": "PRESENT" if state == "UNCLEAR" and direction != "NEUTRAL" else "ABSENT",
        "confidence": q["confidence"], "evidence": evidence, "observations": evidence, "conflicts": q["conflicts"],
        "reasons": q["conflicts"] + (["REGIME_TRANSITION_CONFIRMED"] if tr["confirmed"] else ["REGIME_CONFIRMATION_INSUFFICIENT"] if state == "UNCLEAR" else ["MARKET_STATE_CLASSIFIED"]),
        "reasoning_trace": trace,
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": state, "market_state": state, "direction": direction,
            "directional_pressure": label, "directional_state": q["directional_state"], "trend_maturity": q["maturity"],
            "trend_confirmed": state in {"TREND_UP", "TREND_DOWN"}, "regime_stress": state == "UNCLEAR" and direction != "NEUTRAL",
            "transition_confirmed": tr["confirmed"], "transition_stage": tr["stage"], "conflict_detected": bool(q["conflicts"]),
            "conflict_count": len(q["conflicts"]), "classification_reason": q["reason"], "single_counter_candle": m["single_counter_candle"],
            "pressure_score": pressure_score, "structure_alignment": round(structure_alignment, 3), "trend_score": trend_score,
            "primary_thesis": thesis, "counter_evidence": q["counter"],
            "invalidation": {"primary": invalidation, "conditions": invalidation_conditions},
            "confidence_model": {"evidence_strength": q["support"], "evidence_agreement": q["agreement"], "counter_evidence": q["counter_score"], "stability": q["stability"]},
            "state_stability": {"status": q["stability_status"], "score": q["stability"]},
            "independent_evidence": independent, "evidence_hierarchy": EVIDENCE_HIERARCHY, "ownership_boundaries": OWNERSHIP,
        },
        "analysis_status": "COMPLETE",
    }
