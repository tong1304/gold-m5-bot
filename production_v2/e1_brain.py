"""E1 Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It describes market state from closed-candle OHLC evidence. It never
creates an entry, trade decision, risk decision, or calls E2-E9.

Design principles:
- STATE and CONDITION are separate concepts.
- Structure has authority over short-term pressure for regime classification.
- Counter-pressure is not a reversal.
- Volatility contraction is not automatically Compression.
- Volatility expansion is not automatically directional Expansion.
- Transition requires persistent structural repricing, not disagreement alone.
- Confidence measures confidence in the market-state classification only.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
MARKET_STATES = {
    "TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION",
    "EXPANSION", "TRANSITION", "UNCLEAR",
}
EVIDENCE_HIERARCHY = (
    "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> "
    "VOLATILITY -> RELATIONSHIP -> STABILITY -> COUNTER_EVIDENCE -> STATE -> TRANSITION"
)
OWNERSHIP = {
    "owns": [
        "data_integrity", "volatility_regime", "market_structure_context",
        "directional_pressure", "multi_horizon_alignment", "trend_persistence",
        "market_regime", "regime_transition", "state_stability",
        "counter_evidence", "market_state_thesis", "market_state_invalidation",
    ],
    "does_not_own": [
        "opportunity_setup", "liquidity_auction", "trade_location",
        "entry_confirmation", "trade_economics", "risk_management",
        "trade_execution",
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
        if previous_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
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
        "market_state": "UNCLEAR",
        "directional_pressure": "NEUTRAL",
        "directional_pressure_label": "NEUTRAL",
        "directional_state": "UNRESOLVED",
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
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            "1A DATA_QUALITY -> insufficient",
            "STATE -> UNCLEAR",
        ],
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": "UNCLEAR",
            "market_state": "UNCLEAR",
            "direction": "NEUTRAL",
            "directional_pressure": "NEUTRAL",
            "directional_state": "UNRESOLVED",
            "trend_maturity": "UNAVAILABLE",
            "trend_confirmed": False,
            "transition_confirmed": False,
            "transition_stage": "UNKNOWN",
            "conflict_detected": bool(conflicts),
            "conflict_count": len(conflicts),
            "classification_reason": reason,
            "counter_evidence": [reason],
            "confidence_model": {
                "evidence_strength": 0.0,
                "evidence_agreement": 0.0,
                "counter_evidence": 1.0,
                "stability": 0.0,
            },
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
    total = len(valid) + invalid
    return {
        "valid": valid,
        "valid_candles": len(valid),
        "invalid_candles": invalid,
        "sufficient": len(valid) >= MIN_BARS,
        "quality": _clamp(len(valid) / max(total, 1)),
    }


def _measure(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [bar["close"] for bar in bars]
    atr14 = _atr(bars, 14)
    atr50 = _atr(bars, 50)
    ema20s, ema50s = _ema(closes, 20), _ema(closes, 50)
    ema_relation = "UP" if ema20s[-1] > ema50s[-1] else "DOWN" if ema20s[-1] < ema50s[-1] else "FLAT"
    ema_gap = (ema20s[-1] - ema50s[-1]) / max(atr14, 1e-12)

    horizons = (5, 10, 20, 40)
    thresholds = (0.15, 0.20, 0.30, 0.40)
    slopes = [_slope(closes, atr14, n) for n in horizons]
    horizon_states = [
        "UP" if s >= threshold else "DOWN" if s <= -threshold else "FLAT"
        for s, threshold in zip(slopes, thresholds)
    ]
    up = horizon_states.count("UP")
    down = horizon_states.count("DOWN")
    long_states = horizon_states[1:]
    long_up = long_states.count("UP")
    long_down = long_states.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "BALANCED"
    consensus = max(up, down) / 4.0
    long_consensus = max(long_up, long_down) / 3.0

    if pressure == "UP":
        persistence = sum((
            slopes[0] >= .20, slopes[1] >= .25,
            slopes[2] >= .35, slopes[3] >= .45,
        )) / 4.0
        long_persistence = sum((
            slopes[1] >= .25, slopes[2] >= .35, slopes[3] >= .45,
        )) / 3.0
    elif pressure == "DOWN":
        persistence = sum((
            slopes[0] <= -.20, slopes[1] <= -.25,
            slopes[2] <= -.35, slopes[3] <= -.45,
        )) / 4.0
        long_persistence = sum((
            slopes[1] <= -.25, slopes[2] <= -.35, slopes[3] <= -.45,
        )) / 3.0
    else:
        persistence = long_persistence = 0.0

    prior_atr = _atr(bars, 50, -64, -14) if len(bars) >= 64 else atr50
    volatility_ratio = atr14 / max(prior_atr, 1e-12)
    context_slope = _slope(closes, atr14, 30)
    recent_slope = _slope(closes, atr14, 8)
    context_flip = (
        abs(context_slope) >= .45
        and abs(recent_slope) >= .65
        and (context_slope > 0) != (recent_slope > 0)
    )
    prior_slope = _slope(closes[:-1], atr14, 5)
    prior_pressure = "UP" if prior_slope > .20 else "DOWN" if prior_slope < -.20 else "NEUTRAL"
    last_candle = (
        "UP" if bars[-1]["close"] > bars[-1]["open"]
        else "DOWN" if bars[-1]["close"] < bars[-1]["open"]
        else "FLAT"
    )
    single_counter_candle = (
        prior_pressure in {"UP", "DOWN"}
        and last_candle in {"UP", "DOWN"}
        and prior_pressure != last_candle
    )
    return {
        "closes": closes,
        "atr14": atr14,
        "atr50": atr50,
        "ema20": ema20s,
        "ema50": ema50s,
        "ema_relation": ema_relation,
        "ema_gap": ema_gap,
        "ema20_slope": _slope(ema20s, atr14, 5),
        "ema50_slope": _slope(ema50s, atr14, 5),
        "horizons": horizons,
        "slopes": slopes,
        "horizon_states": horizon_states,
        "up": up,
        "down": down,
        "long_up": long_up,
        "long_down": long_down,
        "pressure": pressure,
        "consensus": consensus,
        "long_consensus": long_consensus,
        "persistence": persistence,
        "long_persistence": long_persistence,
        "eff10": _efficiency(closes, 10),
        "eff20": _efficiency(closes, 20),
        "eff40": _efficiency(closes, 40),
        "prior_atr": prior_atr,
        "volatility_ratio": volatility_ratio,
        "context_slope": context_slope,
        "recent_slope": recent_slope,
        "context_flip": context_flip,
        "prior_pressure": prior_pressure,
        "single_counter_candle": single_counter_candle,
    }


def _structure(bars: list[dict[str, Any]], m: dict[str, Any]) -> dict[str, Any]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING:i + PIVOT_WING + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, bars[i]["low"]))

    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i][1] > highs[i - 1][1] for i in range(1, len(highs)))
    lh = sum(highs[i][1] < highs[i - 1][1] for i in range(1, len(highs)))
    hl = sum(lows[i][1] > lows[i - 1][1] for i in range(1, len(lows)))
    ll = sum(lows[i][1] < lows[i - 1][1] for i in range(1, len(lows)))
    bull_pairs = min(hh, hl)
    bear_pairs = min(lh, ll)

    if bull_pairs >= 2 and bull_pairs > bear_pairs:
        state, quality = "BULLISH", min(1.0, .62 + .07 * bull_pairs)
    elif bear_pairs >= 2 and bear_pairs > bull_pairs:
        state, quality = "BEARISH", min(1.0, .62 + .07 * bear_pairs)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", .52
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", .52
    else:
        state, quality = "MIXED", .30

    direction = "UP" if state == "BULLISH" else "DOWN" if state == "BEARISH" else "NEUTRAL"
    last = bars[-1]["close"]
    latest_swing_high = highs[-1][1] if highs else last
    latest_swing_low = lows[-1][1] if lows else last
    buffer = max(.15 * m["atr14"], 1e-12)

    # A break is only a structural event when the closed candle clears the latest
    # confirmed swing. Two consecutive closes beyond it are required for acceptance.
    prior_close = bars[-2]["close"] if len(bars) >= 2 else last
    probe_up = last > latest_swing_high + buffer and prior_close <= latest_swing_high + buffer
    probe_down = last < latest_swing_low - buffer and prior_close >= latest_swing_low - buffer
    accepted_up = last > latest_swing_high + buffer and prior_close > latest_swing_high + buffer
    accepted_down = last < latest_swing_low - buffer and prior_close < latest_swing_low - buffer

    failed_up = probe_up and last <= latest_swing_high + buffer
    failed_down = probe_down and last >= latest_swing_low - buffer
    bos_direction = "UP" if accepted_up else "DOWN" if accepted_down else "NONE"

    # Protected swings are the latest opposite swing supporting the current structure.
    protected_high = latest_swing_high
    protected_low = latest_swing_low
    if state == "BULLISH" and lows:
        protected_low = lows[-1][1]
    elif state == "BEARISH" and highs:
        protected_high = highs[-1][1]

    return {
        "state": state,
        "direction": direction,
        "quality": quality,
        "counts": {"HH": hh, "HL": hl, "LH": lh, "LL": ll},
        "external_bos": "CONFIRMED_BOS" if bos_direction != "NONE" else "NO_BOS",
        "bos_direction": bos_direction,
        "recent_swing_high": latest_swing_high,
        "recent_swing_low": latest_swing_low,
        "protected_high": protected_high,
        "protected_low": protected_low,
        "break_buffer_atr": .15,
        "acceptance": "UP" if accepted_up else "DOWN" if accepted_down else "NONE",
        "break_probe": "UP" if probe_up else "DOWN" if probe_down else "NONE",
        "failed_break": "UP" if failed_up else "DOWN" if failed_down else "NONE",
        "structure_quality": quality,
    }


def _volatility(m: dict[str, Any]) -> dict[str, Any]:
    ratio = m["volatility_ratio"]
    state = "EXPANDING" if ratio > 1.10 else "CONTRACTING" if ratio < .78 else "NORMAL"
    return {
        "state": state,
        "ratio": ratio,
        "atr14": m["atr14"],
        "prior_atr": m["prior_atr"],
    }


def _range(m: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    balance = 1.0 if m["pressure"] == "BALANCED" else 0.0
    efficiency = 1.0 - _clamp((m["eff20"] + m["eff40"]) / .90)
    structure_weak = 1.0 - _clamp(t["quality"] / .70)
    ema_neutral = 1.0 - _clamp(abs(m["ema_gap"]) / 1.20)
    score = _clamp(.35 * balance + .30 * efficiency + .20 * structure_weak + .15 * ema_neutral)
    confirmed = (
        score >= .62
        and m["eff20"] < .40
        and m["eff40"] < .45
        and abs(m["ema_gap"]) < 1.0
        and t["state"] == "MIXED"
    )
    return {
        "state": "RANGE" if confirmed else "NOT_RANGE",
        "score": score,
        "behavior": "BALANCED_ROTATION" if confirmed else "NOT_CONFIRMED",
    }


def _compression(m: dict[str, Any], v: dict[str, Any]) -> dict[str, Any]:
    atr_contraction = _clamp((.90 - m["volatility_ratio"]) / .20)
    efficiency_contraction = _clamp((.55 - max(m["eff20"], m["eff40"])) / .55)
    directional_balance = 1.0 if m["pressure"] == "BALANCED" else 1.0 - m["consensus"]
    confirmed = (
        v["state"] == "CONTRACTING"
        and m["volatility_ratio"] < .82
        and directional_balance >= .25
        and max(m["eff20"], m["eff40"]) < .55
    )
    score = _clamp(.45 * atr_contraction + .25 * efficiency_contraction + .30 * directional_balance)
    return {
        "state": "CONFIRMED" if confirmed else "ABSENT",
        "score": score,
        "behavior": "ENERGY_BUILD" if confirmed else "NONE",
        "directional_balance": directional_balance,
    }


def _expansion(m: dict[str, Any], v: dict[str, Any], compression: dict[str, Any]) -> dict[str, Any]:
    displacement = _clamp(abs(m["slopes"][0]) / .80)
    efficiency = _clamp(m["eff10"] / .45)
    directional = m["consensus"] if m["pressure"] in {"UP", "DOWN"} else 0.0
    directional_confirmed = (
        v["state"] == "EXPANDING"
        and m["eff10"] >= .25
        and abs(m["slopes"][0]) >= .25
        and directional >= .50
    )
    shock = v["state"] == "EXPANDING" and not directional_confirmed
    score = _clamp(
        .40 * _clamp((m["volatility_ratio"] - 1.05) / .35)
        + .25 * displacement
        + .20 * efficiency
        + .15 * directional
    )
    return {
        "state": "CONFIRMED" if directional_confirmed else "ABSENT",
        "score": score,
        "behavior": "DIRECTIONAL_EXPANSION" if directional_confirmed else "VOLATILITY_SHOCK" if shock else "NONE",
        "directional": directional_confirmed,
        "shock": shock,
        "origin": "AFTER_COMPRESSION" if compression["state"] == "CONFIRMED" else "UNCONFIRMED_ORIGIN",
    }


def _transition(m: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    pressure = m["pressure"]
    structure = t["direction"]
    structural_repricing = (
        t["external_bos"] == "CONFIRMED_BOS"
        and structure in {"UP", "DOWN"}
        and pressure in {"UP", "DOWN"}
        and structure != pressure
    )
    context_flip = m["context_flip"]
    persistent_flip = (
        m["consensus"] >= .75
        and m["persistence"] >= .75
        and m["long_consensus"] >= .667
        and m["long_persistence"] >= .667
    )
    ema_lag = (
        m["ema_relation"] in {"UP", "DOWN"}
        and pressure in {"UP", "DOWN"}
        and m["ema_relation"] != pressure
        and m["persistence"] >= .75
        and (abs(m["slopes"][1]) >= .20 or abs(m["slopes"][2]) >= .30)
    )

    # Watch = evidence is changing. Developing = persistent repricing is visible.
    # Confirmed = the old structural direction has actually been broken and accepted.
    confirmed = structural_repricing and persistent_flip
    developing = persistent_flip and (context_flip or ema_lag or structural_repricing)
    watch = (
        not developing
        and (context_flip or ema_lag or t["break_probe"] != "NONE" or t["failed_break"] != "NONE")
    )

    evidence: list[str] = []
    if context_flip:
        evidence.append("CONTEXT_FLIP")
    if t["external_bos"] == "CONFIRMED_BOS":
        evidence.append("STRUCTURE_BREAK_ACCEPTED")
    if t["break_probe"] != "NONE":
        evidence.append("STRUCTURE_BREAK_PROBE")
    if t["failed_break"] != "NONE":
        evidence.append("FAILED_BREAK")
    if persistent_flip:
        evidence.append("PERSISTENT_MULTI_HORIZON_REPRICING")
    if ema_lag:
        evidence.append("EMA_LAG_WITH_PERSISTENT_PRESSURE")
    if confirmed:
        evidence.append("STRUCTURAL_REPRICING_CONFIRMED")

    stage = "CONFIRMED" if confirmed else "DEVELOPING" if developing else "WATCH" if watch else "ABSENT"
    return {
        "state": stage,
        "confirmed": confirmed,
        "stage": stage,
        "structural_repricing": structural_repricing,
        "context_flip": context_flip,
        "persistent_flip": persistent_flip,
        "watch": watch,
        "evidence": evidence,
        "direction": pressure if pressure in {"UP", "DOWN"} else structure,
    }


def _reconcile(m: dict[str, Any], t: dict[str, Any], v: dict[str, Any], r: dict[str, Any], c: dict[str, Any], e: dict[str, Any], tr: dict[str, Any]) -> dict[str, Any]:
    pressure = m["pressure"]
    structure = t["direction"]
    conflicts: list[str] = []
    counter: list[str] = []

    # These are observations of disagreement, not automatic regime changes.
    if pressure in {"UP", "DOWN"} and structure in {"UP", "DOWN"} and pressure != structure:
        conflicts.append("STRUCTURE_VS_PRESSURE")
        counter.append("COUNTER_TREND_PRESSURE")
    if pressure in {"UP", "DOWN"} and m["ema_relation"] in {"UP", "DOWN"} and m["ema_relation"] != pressure:
        conflicts.append("EMA_VS_PRESSURE")
        counter.append("EMA_CONTEXT_DISAGREES_WITH_PRESSURE")
    if m["up"] > 0 and m["down"] > 0:
        conflicts.append("MULTI_HORIZON_DISAGREEMENT")
        counter.append("MULTI_HORIZON_NOT_FULLY_ALIGNED")
    if m["single_counter_candle"]:
        counter.append("SINGLE_COUNTER_CANDLE")
    if t["failed_break"] != "NONE":
        conflicts.append("FAILED_STRUCTURE_BREAK")
        counter.append("FAILED_STRUCTURE_BREAK")

    # Dominant state is established from structural regime first, then pressure,
    # while volatility/range/compression/expansion act as regime conditions.
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
        and t["quality"] >= .52
    )

    if tr["confirmed"]:
        state = "TRANSITION"
        maturity = "TRANSITION"
        reason = "persistent pressure has produced accepted structural repricing"
    elif trend_aligned:
        state = "TREND_UP" if structural_direction == "UP" else "TREND_DOWN"
        maturity = "ESTABLISHED"
        reason = "structure, pressure, long-horizon alignment and persistence agree"
    elif trend_developing:
        state = "TREND_UP" if structural_direction == "UP" else "TREND_DOWN"
        maturity = "DEVELOPING"
        reason = "structure and pressure agree, but long-horizon confirmation is incomplete"
    elif e["state"] == "CONFIRMED":
        state = "EXPANSION"
        maturity = "EXPANSION"
        reason = "directional volatility expansion is confirmed"
    elif c["state"] == "CONFIRMED":
        state = "COMPRESSION"
        maturity = "COMPRESSION"
        reason = "volatility is contracting while directional travel is inefficient"
    elif r["state"] == "RANGE":
        state = "RANGE"
        maturity = "RANGE"
        reason = "price is rotating with balanced pressure, weak efficiency and mixed structure"
    else:
        state = "UNCLEAR"
        maturity = "UNRESOLVED"
        reason = "independent evidence does not establish a dominant market state"

    # Direction is descriptive. It must not turn a counter-pressure observation
    # into a reversal before structural repricing is confirmed.
    if state in {"TREND_UP", "TREND_DOWN"}:
        direction = structural_direction
    elif state == "TRANSITION":
        direction = tr["direction"] if tr["direction"] in {"UP", "DOWN"} else pressure
    elif pressure in {"UP", "DOWN"}:
        direction = pressure
    else:
        direction = "NEUTRAL"

    evidence_strength = _clamp(
        .40 * t["quality"]
        + .25 * m["long_persistence"]
        + .20 * m["long_consensus"]
        + .15 * max(m["eff20"], m["eff40"])
    )
    agreement = _clamp(
        .40 * (1.0 if pressure == structural_direction and pressure != "BALANCED" else 0.0)
        + .30 * m["long_consensus"]
        + .30 * m["long_persistence"]
    )
    counter_score = _clamp(len(set(counter)) / 5.0)
    conflict_penalty = _clamp(len(set(conflicts)) / 5.0)
    stability = _clamp(
        .45 * m["long_consensus"]
        + .35 * m["long_persistence"]
        + .20 * (1.0 - conflict_penalty)
    )
    stability_status = (
        "STABLE" if stability >= .70 and not tr["confirmed"]
        else "UNSTABLE" if stability < .45 or tr["confirmed"]
        else "WATCH"
    )

    # State confidence is evidence quality/agreement, not trade probability.
    fit = {
        "TREND_UP": 1.0 if direction == "UP" else .0,
        "TREND_DOWN": 1.0 if direction == "DOWN" else .0,
        "RANGE": r["score"],
        "COMPRESSION": c["score"],
        "EXPANSION": e["score"],
        "TRANSITION": .90 if tr["confirmed"] else .0,
        "UNCLEAR": .35,
    }[state]
    confidence = _clamp(
        .35 * evidence_strength
        + .25 * agreement
        + .20 * stability
        + .20 * fit
        - .25 * counter_score
        - .15 * conflict_penalty
    )
    if state == "UNCLEAR":
        confidence = min(confidence, .60)
    if tr["confirmed"]:
        confidence = min(confidence, .85)

    directional_state = (
        "CONFIRMED" if maturity == "ESTABLISHED"
        else "DEVELOPING" if direction in {"UP", "DOWN"}
        else "NEUTRAL"
    )
    if not counter:
        counter = ["NO_MATERIAL_COUNTER_EVIDENCE"]
    all_conflicts = list(dict.fromkeys(conflicts))
    return {
        "state": state,
        "direction": direction,
        "maturity": maturity,
        "directional_state": directional_state,
        "reason": reason,
        "counter": counter,
        "conflicts": all_conflicts,
        "support": round(evidence_strength, 3),
        "agreement": round(agreement, 3),
        "counter_score": round(counter_score, 3),
        "stability": round(stability, 3),
        "stability_status": stability_status,
        "confidence": round(confidence, 3),
    }


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    quality = _data_quality(bars)
    if not quality["sufficient"]:
        return _incomplete(
            "insufficient reliable closed candles; classification withheld",
            [
                f"valid_candles={quality['valid_candles']}",
                f"invalid_candles={quality['invalid_candles']}",
                f"minimum_required={MIN_BARS}",
            ],
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
    trend_score = round(
        .30 * m["consensus"]
        + .25 * m["persistence"]
        + .25 * structure_alignment
        + .10 * ema_alignment
        + .10 * m["long_consensus"],
        3,
    )

    invalidation = (
        "PRICE_ACCEPTS_BELOW_PROTECTED_BULLISH_STRUCTURE_AND_PERSISTENT_DOWN_PRESSURE"
        if direction == "UP"
        else "PRICE_ACCEPTS_ABOVE_PROTECTED_BEARISH_STRUCTURE_AND_PERSISTENT_UP_PRESSURE"
        if direction == "DOWN"
        else "PERSISTENT_DIRECTIONAL_PRESSURE_AND_CONFIRMED_STRUCTURAL_REPRICING"
    )
    invalidation_conditions = (
        [
            "STRUCTURE_TURNS_BEARISH",
            "MULTI_HORIZON_PRESSURE_TURNS_DOWN_AND_PERSISTS",
            "EMA_CONTEXT_FLIPS_DOWN_WITH_CONFIRMING_STRUCTURE",
        ]
        if direction == "UP"
        else [
            "STRUCTURE_TURNS_BULLISH",
            "MULTI_HORIZON_PRESSURE_TURNS_UP_AND_PERSISTS",
            "EMA_CONTEXT_FLIPS_UP_WITH_CONFIRMING_STRUCTURE",
        ]
        if direction == "DOWN"
        else [
            "PERSISTENT_MULTI_HORIZON_DIRECTIONAL_PRESSURE",
            "CONFIRMED_STRUCTURE_BREAK_WITH_ACCEPTANCE",
        ]
    )

    supporting = []
    if structure_alignment:
        supporting.append("STRUCTURE_ALIGNS")
    if pressure_score >= .50:
        supporting.append("DIRECTIONAL_PRESSURE_PRESENT")
    if m["long_persistence"] >= .667:
        supporting.append("LONG_HORIZON_PERSISTENCE")
    if m["long_consensus"] >= .667:
        supporting.append("LONG_HORIZON_ALIGNMENT")

    thesis = {
        "direction": direction,
        "label": label,
        "status": (
            "CONFIRMED" if state in {"TREND_UP", "TREND_DOWN"} and q["maturity"] == "ESTABLISHED"
            else "DEVELOPING" if direction != "NEUTRAL" else "UNRESOLVED"
        ),
        "supporting_evidence": supporting,
        "counter_evidence": q["counter"],
        "support_score": q["support"],
        "counter_score": q["counter_score"],
        "relationship": (
            "WITH_TREND" if structure_alignment and direction == m["pressure"]
            else "COUNTER_TREND_PRESSURE" if structure_alignment and m["pressure"] in {"UP", "DOWN"}
            else "MIXED_OR_NEUTRAL"
        ),
    }

    evidence = [
        f"valid_candles={quality['valid_candles']}",
        f"invalid_candles={quality['invalid_candles']}",
        f"ema20_vs_ema50={m['ema_relation']}",
        f"ema_gap_atr={m['ema_gap']:.3f}",
        *(f"price_slope_{n}_atr={s:.3f}" for n, s in zip(m["horizons"], m["slopes"])),
        f"multi_horizon={','.join(m['horizon_states'])}",
        f"directional_consensus={m['consensus']:.3f}",
        f"long_horizon_consensus={m['long_consensus']:.3f}",
        f"persistence={m['persistence']:.3f}",
        f"long_horizon_persistence={m['long_persistence']:.3f}",
        f"structure_state={t['state']}",
        f"structure_quality={t['quality']:.3f}",
        f"protected_high={t['protected_high']:.6f}",
        f"protected_low={t['protected_low']:.6f}",
        f"external_bos={t['external_bos']}",
        f"acceptance={t['acceptance']}",
        f"break_probe={t['break_probe']}",
        f"failed_break={t['failed_break']}",
        f"volatility_ratio={m['volatility_ratio']:.3f}",
        f"volatility_condition={v['state']}",
        f"compression={c['state']}:{c['score']:.3f}",
        f"expansion={e['behavior']}:{e['score']:.3f}",
        f"transition_stage={tr['stage']}",
        f"transition_confirmed={tr['confirmed']}",
        f"state={state}",
        f"direction={direction}",
        f"relationship={thesis['relationship']}",
        f"stability={q['stability_status']}:{q['stability']:.3f}",
        f"counter_evidence={q['counter']}",
    ]

    independent = {
        "1A_data_quality": {
            "valid_candles": quality["valid_candles"],
            "invalid_candles": quality["invalid_candles"],
            "quality": round(quality["quality"], 3),
        },
        "1B_volatility": v,
        "1C_trend": t,
        "1D_range": r,
        "1E_compression": c,
        "1F_expansion": e,
        "1G_transition": tr,
        "data_quality": {
            "valid_candles": quality["valid_candles"],
            "invalid_candles": quality["invalid_candles"],
        },
        "structure": {**t, "alignment": structure_alignment},
        "pressure": {
            "direction": m["pressure"],
            "score": pressure_score,
            "state": q["directional_state"],
            "relationship_to_structure": thesis["relationship"],
        },
        "persistence": {
            "score": round(m["persistence"], 3),
            "long_horizon_score": round(m["long_persistence"], 3),
            "efficiency20": round(m["eff20"], 3),
            "efficiency40": round(m["eff40"], 3),
        },
        "ema_context": {
            "relation": m["ema_relation"],
            "gap_atr": round(m["ema_gap"], 3),
            "ema20_slope_atr": round(m["ema20_slope"], 3),
            "ema50_slope_atr": round(m["ema50_slope"], 3),
            "alignment": ema_alignment,
            "authority": "CONTEXT_ONLY",
        },
        "volatility": {
            "atr14": round(m["atr14"], 6),
            "prior_atr": round(m["prior_atr"], 6),
            "ratio": round(m["volatility_ratio"], 3),
            "condition": v["state"],
        },
        "transition": tr,
        "stability": {"score": q["stability"], "status": q["stability_status"]},
        "counter_evidence": q["counter"],
        "invalidation": {"primary": invalidation, "conditions": invalidation_conditions},
    }

    trace = [
        f"QUESTION -> {QUESTION}",
        f"1A DATA_QUALITY -> VALID {quality['valid_candles']}/{quality['valid_candles'] + quality['invalid_candles']}",
        f"1B VOLATILITY -> CONDITION={v['state']} ratio={m['volatility_ratio']:.2f}",
        f"1C TREND -> structure={t['state']} quality={t['quality']:.2f} pressure={m['pressure']} persistence={m['persistence']:.2f}",
        f"1C RELATIONSHIP -> {thesis['relationship']}",
        f"1D RANGE -> {r['state']} score={r['score']:.2f}",
        f"1E COMPRESSION -> {c['state']} score={c['score']:.2f}",
        f"1F EXPANSION -> {e['behavior']} score={e['score']:.2f}",
        f"1G TRANSITION -> {tr['stage']} confirmed={tr['confirmed']} evidence={tr['evidence']}",
        f"RECONCILIATION -> dominant_state={state} direction={direction}",
        f"RECONCILIATION -> support={q['support']:.2f} agreement={q['agreement']:.2f} counter={q['counter_score']:.2f}",
        f"CONFLICTS -> {q['conflicts']}",
        f"STABILITY -> {q['stability_status']} score={q['stability']:.2f}",
        "RULE -> COUNTER_PRESSURE_IS_NOT_REVERSAL_WITHOUT_STRUCTURAL_REPRICING",
        "RULE -> VOLATILITY_CONDITION_IS_NOT_AUTOMATICALLY_MARKET_STATE",
        "RULE -> EMA_IS_CONTEXT_NOT_STRUCTURE_AUTHORITY",
        f"CONFIDENCE -> {q['confidence']:.3f} (market-state confidence, not trade probability)",
        f"STATE -> {state} because={q['reason']}",
        f"INVALIDATION -> {invalidation}",
    ]

    return {
        **_base_result(),
        "market_state": state,
        # Preserve legacy key semantics: this is the current directional pressure,
        # not a claim that the market state itself has reversed.
        "directional_pressure": m["pressure"],
        "directional_pressure_label": "BULLISH" if m["pressure"] == "UP" else "BEARISH" if m["pressure"] == "DOWN" else "NEUTRAL",
        "directional_state": q["directional_state"],
        "trend_state": "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE",
        "volatility_state": v["state"],
        "structure_state": t["state"],
        "structure_quality": round(t["quality"], 3),
        "range_state": r["state"],
        "compression": c["state"],
        "expansion": e["state"],
        # Backward-compatible legacy flag; use transition_stage for full reasoning.
        "transition": "PRESENT" if tr["confirmed"] else "ABSENT",
        "transition_stage": tr["stage"],
        "regime_stress": "PRESENT" if state == "UNCLEAR" and direction != "NEUTRAL" else "ABSENT",
        "confidence": q["confidence"],
        "evidence": evidence,
        "observations": evidence,
        "conflicts": q["conflicts"],
        "reasons": q["conflicts"] + (
            ["REGIME_TRANSITION_CONFIRMED"] if tr["confirmed"]
            else ["TRANSITION_WATCH_ONLY"] if tr["stage"] in {"WATCH", "DEVELOPING"}
            else ["MARKET_STATE_CLASSIFIED"]
        ),
        "reasoning_trace": trace,
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "primary_state": state,
            "market_state": state,
            "direction": direction,
            "directional_pressure": m["pressure"],
            "directional_state": q["directional_state"],
            "trend_maturity": q["maturity"],
            "trend_confirmed": state in {"TREND_UP", "TREND_DOWN"} and q["maturity"] == "ESTABLISHED",
            "regime_stress": state == "UNCLEAR" and direction != "NEUTRAL",
            "transition_confirmed": tr["confirmed"],
            "transition_stage": tr["stage"],
            "transition_direction": tr["direction"],
            "transition_evidence": tr["evidence"],
            "conflict_detected": bool(q["conflicts"]),
            "conflict_count": len(q["conflicts"]),
            "classification_reason": q["reason"],
            "single_counter_candle": m["single_counter_candle"],
            "pressure_score": pressure_score,
            "structure_alignment": round(structure_alignment, 3),
            "trend_score": trend_score,
            "primary_thesis": thesis,
            "counter_evidence": q["counter"],
            "dominant_evidence": supporting if supporting else [f"STATE={state}"],
            "invalidation": {"primary": invalidation, "conditions": invalidation_conditions},
            "confidence_model": {
                "evidence_strength": q["support"],
                "evidence_agreement": q["agreement"],
                "counter_evidence": q["counter_score"],
                "stability": q["stability"],
            },
            "state_stability": {"status": q["stability_status"], "score": q["stability"]},
            "independent_evidence": independent,
            "evidence_hierarchy": EVIDENCE_HIERARCHY,
            "ownership_boundaries": OWNERSHIP,
        },
        "analysis_status": "COMPLETE",
    }
