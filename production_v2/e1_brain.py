"""E1 Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It analyzes closed-candle OHLC data and supplies market-state context only.
It never creates a setup, entry, risk plan, or BUY/SELL decision.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 80
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> MULTI_HORIZON -> VOLATILITY -> RELATIONSHIP -> STABILITY -> TRANSITION -> MARKET_STATE"
OWNERSHIP = {
    "owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "market_regime", "regime_transition", "state_stability", "counter_evidence", "market_state_invalidation"],
    "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution"],
}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _num(x: Any) -> float | None:
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    current = values[0]
    out = [current]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
        out.append(current)
    return out


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    previous = None
    for bar in bars:
        high, low, close = bar["high"], bar["low"], bar["close"]
        out.append(high - low if previous is None else max(high - low, abs(high - previous), abs(low - previous)))
        previous = close
    return out


def _atr(bars: list[dict[str, Any]], period: int) -> float:
    tr = _true_ranges(bars[-period:])
    return mean(tr) if tr else 0.0


def _slope(values: list[float], atr: float, lookback: int) -> float:
    if atr <= 0 or len(values) <= lookback:
        return 0.0
    return (values[-1] - values[-1 - lookback]) / atr


def _efficiency(values: list[float], lookback: int) -> float:
    sample = values[-lookback:]
    if len(sample) < 2:
        return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return _clamp(abs(sample[-1] - sample[0]) / max(path, 1e-12))


def _quality(bars: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], int]:
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
    return valid, invalid


def _pivots(bars: list[dict[str, Any]], wing: int = PIVOT_WING) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for index in range(wing, len(bars) - wing):
        window = bars[index - wing:index + wing + 1]
        high, low = bars[index]["high"], bars[index]["low"]
        if high >= max(bar["high"] for bar in window):
            highs.append((index, high))
        if low <= min(bar["low"] for bar in window):
            lows.append((index, low))
    return highs, lows


def _structure(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    highs, lows = _pivots(bars)
    highs, lows = highs[-10:], lows[-10:]
    hh = sum(highs[i][1] > highs[i - 1][1] for i in range(1, len(highs)))
    lh = sum(highs[i][1] < highs[i - 1][1] for i in range(1, len(highs)))
    hl = sum(lows[i][1] > lows[i - 1][1] for i in range(1, len(lows)))
    ll = sum(lows[i][1] < lows[i - 1][1] for i in range(1, len(lows)))
    bull_pairs, bear_pairs = min(hh, hl), min(lh, ll)
    bull_score, bear_score = hh + hl, lh + ll
    if bull_pairs >= 2 and bull_pairs > bear_pairs:
        state, direction, quality = "BULLISH", "UP", _clamp(0.60 + 0.08 * bull_pairs)
    elif bear_pairs >= 2 and bear_pairs > bull_pairs:
        state, direction, quality = "BEARISH", "DOWN", _clamp(0.60 + 0.08 * bear_pairs)
    elif bull_score >= 3 and bull_score > bear_score + 1:
        state, direction, quality = "BULLISH", "UP", 0.52
    elif bear_score >= 3 and bear_score > bull_score + 1:
        state, direction, quality = "BEARISH", "DOWN", 0.52
    else:
        state, direction, quality = "MIXED", "NEUTRAL", 0.30
    last, prior = bars[-1]["close"], bars[-2]["close"]
    high = highs[-1][1] if highs else last
    low = lows[-1][1] if lows else last
    buffer = max(0.15 * atr, 1e-12)
    accepted_up = last > high + buffer and prior > high + buffer
    accepted_down = last < low - buffer and prior < low - buffer
    probe_up = last > high + buffer and prior <= high + buffer
    probe_down = last < low - buffer and prior >= low - buffer
    return {
        "state": state, "direction": direction, "quality": quality,
        "HH": hh, "HL": hl, "LH": lh, "LL": ll,
        "external_bos": "CONFIRMED_BOS" if accepted_up or accepted_down else "NO_BOS",
        "bos_direction": "UP" if accepted_up else "DOWN" if accepted_down else "NONE",
        "protected_high": high, "protected_low": low,
        "acceptance": "UP" if accepted_up else "DOWN" if accepted_down else "NONE",
        "break_probe": "UP" if probe_up else "DOWN" if probe_down else "NONE",
    }


def _pressure(slopes: list[float]) -> dict[str, Any]:
    thresholds = (0.15, 0.20, 0.30, 0.40)
    states = ["UP" if slope >= threshold else "DOWN" if slope <= -threshold else "FLAT" for slope, threshold in zip(slopes, thresholds)]
    up, down = states.count("UP"), states.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "BALANCED"
    long_states = states[1:]
    long_up, long_down = long_states.count("UP"), long_states.count("DOWN")
    return {
        "states": states, "pressure": pressure, "consensus": max(up, down) / len(states),
        "long_direction": "UP" if long_up > long_down else "DOWN" if long_down > long_up else "NEUTRAL",
        "long_consensus": max(long_up, long_down) / len(long_states),
        "slope_5": slopes[0], "slope_10": slopes[1], "slope_20": slopes[2], "slope_40": slopes[3],
    }


def _persistence(closes: list[float], atr: float, pressure: str) -> dict[str, Any]:
    windows = (5, 10, 20, 40)
    values = [_slope(closes, atr, n) for n in windows]
    thresholds = (0.15, 0.20, 0.30, 0.40)
    if pressure == "UP":
        hits = sum(value >= threshold for value, threshold in zip(values, thresholds))
    elif pressure == "DOWN":
        hits = sum(value <= -threshold for value, threshold in zip(values, thresholds))
    else:
        hits = 0
    score = hits / len(values)
    recent = closes[-24:]
    if len(recent) >= 12:
        chunks = [recent[:8], recent[8:16], recent[16:]]
        chunk_slopes = [chunk[-1] - chunk[0] for chunk in chunks if len(chunk) >= 2]
        consistency = (sum(x > 0 for x in chunk_slopes) if pressure == "UP" else sum(x < 0 for x in chunk_slopes)) / len(chunk_slopes) if pressure in {"UP", "DOWN"} else 0.0
    else:
        consistency = 0.0
    return {"score": score, "consistency": consistency, "values": values, "persistent": score >= 0.75 and consistency >= 0.667}


def _range_analysis(bars: list[dict[str, Any]], closes: list[float], atr: float, structure: dict[str, Any]) -> dict[str, Any]:
    hi20, lo20 = max(bar["high"] for bar in bars[-21:-1]), min(bar["low"] for bar in bars[-21:-1])
    hi40, lo40 = max(bar["high"] for bar in bars[-41:-1]), min(bar["low"] for bar in bars[-41:-1])
    width20, width40 = max(hi20 - lo20, 1e-12), max(hi40 - lo40, 1e-12)
    position20, position40 = _clamp((closes[-1] - lo20) / width20), _clamp((closes[-1] - lo40) / width40)
    eff20, eff40 = _efficiency(closes, 20), _efficiency(closes, 40)
    balance = 1.0 - abs(position20 - 0.5) * 2.0
    boundary_rejection = 1.0 if ((position20 <= 0.20 and closes[-1] >= closes[-2]) or (position20 >= 0.80 and closes[-1] <= closes[-2])) else 0.0
    score = _clamp(0.30 * balance + 0.25 * (1 - eff20) + 0.20 * (1 - eff40) + 0.15 * (1 if structure["state"] == "MIXED" else 0) + 0.10 * boundary_rejection)
    return {
        "range_score": score, "range_confirmed": score >= 0.62 and eff20 < 0.45 and eff40 < 0.55 and width40 / atr <= 10.0,
        "position_20": position20, "position_40": position40, "range_high_20": hi20, "range_low_20": lo20,
        "range_high_40": hi40, "range_low_40": lo40, "efficiency_20": eff20, "efficiency_40": eff40,
        "boundary_rejection": boundary_rejection,
    }


def _volatility(bars: list[dict[str, Any]], atr14: float, atr50: float, closes: list[float]) -> dict[str, Any]:
    ratio = atr14 / max(atr50, 1e-12)
    ranges = [bar["high"] - bar["low"] for bar in bars]
    short_range_ratio = mean(ranges[-5:]) / max(mean(ranges[-20:]), 1e-12)
    state = "EXPANDING" if ratio >= 1.12 else "CONTRACTING" if ratio <= 0.82 else "NORMAL"
    directional = state == "EXPANDING" and _efficiency(closes, 10) >= 0.30 and abs(_slope(closes, atr14, 5)) >= 0.25
    return {
        "state": state, "ratio": ratio, "short_range_ratio": short_range_ratio,
        "volatility_expansion": state == "EXPANDING", "directional_expansion": directional,
        "compression": state == "CONTRACTING" and short_range_ratio <= 0.85 and _efficiency(closes, 10) <= 0.55,
    }


def _transition(closes: list[float], atr: float, structure: dict[str, Any], pressure: dict[str, Any], persistence: dict[str, Any], volatility: dict[str, Any]) -> dict[str, Any]:
    slope8, slope30 = _slope(closes, atr, 8), _slope(closes, atr, 30)
    short_dir = "UP" if slope8 > 0.20 else "DOWN" if slope8 < -0.20 else "FLAT"
    context_dir = "UP" if slope30 > 0.35 else "DOWN" if slope30 < -0.35 else "FLAT"
    disagreement = structure["direction"] in {"UP", "DOWN"} and pressure["pressure"] in {"UP", "DOWN"} and structure["direction"] != pressure["pressure"]
    inflection = short_dir in {"UP", "DOWN"} and context_dir in {"UP", "DOWN"} and short_dir != context_dir
    structural_repricing = structure["external_bos"] == "CONFIRMED_BOS"
    persistent_counter = disagreement and (persistence["score"] >= 0.50 or pressure["long_consensus"] >= 0.667)
    confirmed = structural_repricing and persistent_counter
    present = confirmed or (disagreement and (inflection or persistent_counter))
    watch = disagreement or inflection or volatility["directional_expansion"]
    stage = "CONFIRMED" if confirmed else "PRESENT" if present else "WATCH" if watch else "ABSENT"
    return {
        "state": stage, "stage": stage, "short_direction": short_dir, "context_direction": context_dir,
        "disagreement": disagreement, "inflection": inflection, "structural_repricing": structural_repricing,
        "persistent_counter": persistent_counter, "lifecycle": "NONE" if stage == "ABSENT" else stage,
    }


def _reconcile(*, structure: dict[str, Any], pressure: dict[str, Any], persistence: dict[str, Any], volatility: dict[str, Any], range_info: dict[str, Any], transition: dict[str, Any], ema_relation: str, ema_gap_atr: float) -> dict[str, Any]:
    counter: list[str] = []
    sd, pd = structure["direction"], pressure["pressure"]
    if sd in {"UP", "DOWN"} and pd in {"UP", "DOWN"} and sd != pd: counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if ema_relation in {"UP", "DOWN"} and pd in {"UP", "DOWN"} and ema_relation != pd: counter.append("EMA_CONTEXT_DISAGREES_WITH_PRESSURE")
    if persistence["score"] < 0.50 and pd in {"UP", "DOWN"}: counter.append("PERSISTENCE_WEAK")
    if pressure["long_consensus"] < 0.667 and pd in {"UP", "DOWN"}: counter.append("LONG_HORIZON_NOT_ALIGNED")
    if abs(ema_gap_atr) < 0.25: counter.append("EMA_SEPARATION_WEAK")
    if range_info["range_confirmed"] and pd in {"UP", "DOWN"}: counter.append("RANGE_COMPETES_WITH_DIRECTION")
    dominant: list[str] = []
    if sd in {"UP", "DOWN"} and structure["quality"] >= 0.60: dominant.append("STRUCTURE")
    if pd in {"UP", "DOWN"} and pressure["consensus"] >= 0.75: dominant.append("PRESSURE")
    if persistence["persistent"]: dominant.append("PERSISTENCE")
    if pressure["long_consensus"] >= 0.667: dominant.append("MULTI_HORIZON")
    if range_info["range_confirmed"]: dominant.append("RANGE_BOUNDARY_BALANCE")
    if volatility["compression"]: dominant.append("VOLATILITY_COMPRESSION")
    if volatility["directional_expansion"]: dominant.append("DIRECTIONAL_EXPANSION")
    if transition["stage"] in {"PRESENT", "CONFIRMED"}: dominant.append("TRANSITION_EVIDENCE")
    aligned = sd in {"UP", "DOWN"} and pd == sd and persistence["persistent"] and pressure["long_consensus"] >= 0.667 and structure["quality"] >= 0.60
    if transition["stage"] == "CONFIRMED":
        state, direction = "TRANSITION", pd if pd in {"UP", "DOWN"} else "NEUTRAL"
    elif range_info["range_confirmed"] and transition["stage"] == "ABSENT":
        state, direction = "RANGE", "NEUTRAL"
    elif aligned:
        state, direction = ("TREND_UP" if sd == "UP" else "TREND_DOWN"), sd
    elif volatility["compression"]:
        state, direction = "COMPRESSION", pd if pd in {"UP", "DOWN"} else "NEUTRAL"
    elif volatility["directional_expansion"]:
        state, direction = "EXPANSION", pd if pd in {"UP", "DOWN"} else "NEUTRAL"
    elif sd in {"UP", "DOWN"} and pd == sd and pressure["consensus"] >= 0.50:
        state, direction = ("TREND_UP" if sd == "UP" else "TREND_DOWN"), sd
    elif transition["stage"] in {"PRESENT", "WATCH"}:
        state, direction = "TRANSITION", pd if pd in {"UP", "DOWN"} else "NEUTRAL"
    else:
        state, direction = "UNCLEAR", pd if pd in {"UP", "DOWN"} else "NEUTRAL"
    agreement = 1.0 - min(len(counter), 5) / 5.0
    confidence = _clamp(0.24 * structure["quality"] + 0.20 * pressure["consensus"] + 0.20 * persistence["score"] + 0.16 * pressure["long_consensus"] + 0.10 * persistence["consistency"] + 0.10 * agreement)
    if state == "RANGE": confidence = max(confidence, _clamp(0.55 + 0.25 * range_info["range_score"]))
    if state == "TRANSITION" and transition["stage"] != "CONFIRMED": confidence = _clamp(confidence * 0.85)
    stability = "STABLE" if confidence >= 0.75 and len(counter) <= 1 else "CHALLENGED" if confidence >= 0.50 else "UNSTABLE"
    return {"state": state, "direction": direction, "confidence": confidence, "dominant_evidence": dominant, "counter_evidence": counter, "conflicts": counter, "stability": stability, "evidence_agreement": agreement}


def _incomplete(base: dict[str, Any], valid: int, invalid: int, reason: str) -> dict[str, Any]:
    return {**base, "market_state": "UNCLEAR", "direction": "NEUTRAL", "directional_pressure": "NEUTRAL", "directional_state": "UNRESOLVED", "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "structure_quality": 0.0, "range_state": "UNKNOWN", "compression": "UNKNOWN", "expansion": "UNKNOWN", "expansion_directional": "UNKNOWN", "transition": "UNKNOWN", "transition_stage": "UNKNOWN", "confidence": 0.0, "evidence": [f"valid_candles={valid}", f"invalid_candles={invalid}"], "observations": [], "conflicts": [], "reasons": [reason], "reason_codes": [reason], "analysis_status": "INCOMPLETE"}


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Return professional market-state context only; E1 never owns trade authority."""
    base = {"question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY", "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN", "ownership": OWNERSHIP, "evidence_hierarchy": EVIDENCE_HIERARCHY}
    valid, invalid = _quality(bars)
    if len(valid) < MIN_BARS: return _incomplete(base, len(valid), invalid, "DATA_QUALITY_INSUFFICIENT")
    closes = [bar["close"] for bar in valid]
    atr14, atr50 = _atr(valid, 14), _atr(valid, 50)
    if atr14 <= 0 or atr50 <= 0: return _incomplete(base, len(valid), invalid, "ATR_INVALID")
    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    ema_relation = "UP" if ema20[-1] > ema50[-1] else "DOWN" if ema20[-1] < ema50[-1] else "FLAT"
    ema_gap_atr = (ema20[-1] - ema50[-1]) / atr14
    slopes = [_slope(closes, atr14, n) for n in (5, 10, 20, 40)]
    pressure = _pressure(slopes)
    persistence = _persistence(closes, atr14, pressure["pressure"])
    structure = _structure(valid, atr14)
    range_info = _range_analysis(valid, closes, atr14, structure)
    volatility = _volatility(valid, atr14, atr50, closes)
    transition = _transition(closes, atr14, structure, pressure, persistence, volatility)
    reconciled = _reconcile(structure=structure, pressure=pressure, persistence=persistence, volatility=volatility, range_info=range_info, transition=transition, ema_relation=ema_relation, ema_gap_atr=ema_gap_atr)
    observations = [f"valid_candles={len(valid)}", f"invalid_candles={invalid}", f"ema20_vs_ema50={ema_relation}", f"ema_gap_atr={ema_gap_atr:.3f}", f"multi_horizon={','.join(pressure['states'])}", f"directional_consensus={pressure['consensus']:.3f}", f"long_horizon_direction={pressure['long_direction']}", f"long_horizon_consensus={pressure['long_consensus']:.3f}", f"persistence={persistence['score']:.3f}", f"persistence_consistency={persistence['consistency']:.3f}", f"structure={structure['state']}", f"structure_quality={structure['quality']:.3f}", f"external_bos={structure['external_bos']}", f"volatility_ratio={volatility['ratio']:.3f}", f"range_score={range_info['range_score']:.3f}", f"transition_stage={transition['stage']}"]
    reasons = ["DATA_INTEGRITY_VALIDATED"]
    if reconciled["dominant_evidence"]: reasons.append("DOMINANT_EVIDENCE=" + "+".join(reconciled["dominant_evidence"]))
    if reconciled["counter_evidence"]: reasons.append("COUNTER_EVIDENCE_PRESENT")
    if volatility["compression"]: reasons.append("VOLATILITY_COMPRESSION_DETECTED")
    if volatility["directional_expansion"]: reasons.append("DIRECTIONAL_EXPANSION_DETECTED")
    if transition["stage"] == "WATCH": reasons.append("TRANSITION_WATCH_ONLY")
    elif transition["stage"] == "PRESENT": reasons.append("REGIME_TRANSITION_PRESENT")
    elif transition["stage"] == "CONFIRMED": reasons.append("REGIME_TRANSITION_CONFIRMED")
    if ema_relation in {"UP", "DOWN"}: reasons.append("EMA_AS_CONTEXT_NOT_AUTHORITY")
    state, direction = reconciled["state"], reconciled["direction"]
    directional_state = "CONFIRMED" if state in {"TREND_UP", "TREND_DOWN"} and reconciled["confidence"] >= 0.70 else "DEVELOPING" if direction in {"UP", "DOWN"} else "NEUTRAL"
    trace = {"question": QUESTION, "data_quality": {"valid_candles": len(valid), "invalid_candles": invalid, "status": "VALIDATED"}, "volatility": volatility, "trend": {"structure": structure["state"], "pressure": pressure["pressure"], "persistence": persistence["score"], "persistence_consistency": persistence["consistency"], "multi_horizon": pressure["states"], "long_horizon_consensus": pressure["long_consensus"]}, "range": range_info, "compression": {"active": volatility["compression"]}, "expansion": {"volatility": volatility["volatility_expansion"], "directional": volatility["directional_expansion"]}, "transition": transition, "reconciliation": reconciled}
    return {**base, "market_state": state, "direction": direction, "directional_pressure": pressure["pressure"], "directional_state": directional_state, "trend_state": "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE", "volatility_state": volatility["state"], "structure_state": structure["state"], "structure_direction": structure["direction"], "structure_quality": structure["quality"], "pressure": pressure["pressure"], "persistence": persistence["score"], "persistence_consistency": persistence["consistency"], "multi_horizon": pressure["states"], "directional_consensus": pressure["consensus"], "long_horizon_direction": pressure["long_direction"], "long_horizon_consensus": pressure["long_consensus"], "ema_relation": ema_relation, "ema_gap_atr": ema_gap_atr, "range_state": "CONFIRMED" if range_info["range_confirmed"] else "UNCONFIRMED", "range_score": range_info["range_score"], "compression": "ACTIVE" if volatility["compression"] else "INACTIVE", "expansion": "ACTIVE" if volatility["volatility_expansion"] else "INACTIVE", "expansion_directional": "ACTIVE" if volatility["directional_expansion"] else "INACTIVE", "transition": transition["stage"], "transition_stage": transition["stage"], "transition_lifecycle": transition["lifecycle"], "transition_evidence": transition, "dominant_evidence": reconciled["dominant_evidence"], "counter_evidence": reconciled["counter_evidence"], "conflicts": reconciled["conflicts"], "stability": reconciled["stability"], "confidence": reconciled["confidence"], "evidence_strength": reconciled["confidence"], "evidence": observations, "observations": observations, "reasons": reasons, "reason_codes": reasons, "reasoning_trace": trace, "analysis_status": "COMPLETE", "invalidations": ["market_state_invalid_if_data_quality_fails", "trend_invalid_if_structure_and_persistent_pressure_no_longer_agree", "transition_invalid_if_repricing_is_not_confirmed"], "trade_authority_isolated": True, "trade_decision": None, "entry": None, "risk": None}
