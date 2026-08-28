"""E1 V11 — standalone professional market-state analyst.

E1 answers only: What is the market doing right now?
No setup, entry, stop, target, risk, or trade decision is produced here.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
ARBITRATION_ORDER = [
    "DATA_QUALITY", "STRUCTURE", "LONG_HORIZON", "EMA_CONTEXT", "PRESSURE",
    "PERSISTENCE", "VOLATILITY", "COUNTER_EVIDENCE", "TRANSITION",
]


def _num(x: Any) -> float | None:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _clean(bars: list[dict[str, Any]] | None):
    valid, invalid = [], 0
    for raw in bars or []:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        v = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            invalid += 1
            continue
        o, h, l, c = v["open"], v["high"], v["low"], v["close"]
        if h < l or h < max(o, c) or l > min(o, c):
            invalid += 1
            continue
        valid.append({**raw, **v})
    return valid, invalid


def _ema(xs: list[float], n: int) -> list[float]:
    if not xs:
        return []
    a, cur, out = 2.0 / (n + 1.0), xs[0], [xs[0]]
    for x in xs[1:]:
        cur = a * x + (1.0 - a) * cur
        out.append(cur)
    return out


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    sample = bars[-n:]
    trs, prev = [], None
    for b in sample:
        h, l, c = b["high"], b["low"], b["close"]
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return mean(trs) if trs else 0.0


def _slope(xs: list[float], atr: float, n: int) -> float:
    return 0.0 if atr <= 0 or len(xs) <= n else (xs[-1] - xs[-1 - n]) / atr


def _efficiency(xs: list[float], n: int) -> float:
    s = xs[-n:]
    if len(s) < 2:
        return 0.0
    path = sum(abs(s[i] - s[i - 1]) for i in range(1, len(s)))
    return abs(s[-1] - s[0]) / max(path, 1e-12)


def _structure(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    highs, lows = [], []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        w = bars[i - PIVOT_WING:i + PIVOT_WING + 1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in w):
            highs.append(h)
        if l <= min(x["low"] for x in w):
            lows.append(l)
    highs, lows = highs[-8:], lows[-8:]
    hh = sum(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    lh = sum(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    ll = sum(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear:
        state, quality = "BULLISH", min(1.0, .62 + .07 * bull)
    elif bear >= 2 and bear > bull:
        state, quality = "BEARISH", min(1.0, .62 + .07 * bear)
    elif hh + hl >= 2 and hh + hl > lh + ll:
        state, quality = "BULLISH", .52
    elif lh + ll >= 2 and lh + ll > hh + hl:
        state, quality = "BEARISH", .52
    else:
        state, quality = "MIXED", .30
    last = bars[-1]["close"]
    hi, lo = max(highs, default=last), min(lows, default=last)
    buf = max(.10 * atr, 1e-12)
    bos = "UP" if last > hi + buf else "DOWN" if last < lo - buf else "NONE"
    return {
        "state": state, "quality": quality,
        "counts": {"HH": hh, "HL": hl, "LH": lh, "LL": ll},
        "bos": bos, "recent_high": hi, "recent_low": lo,
    }


def _dir(state: str) -> str:
    return "UP" if state == "BULLISH" else "DOWN" if state == "BEARISH" else "NEUTRAL"


def _incomplete(reason: str, valid: int, invalid: int) -> dict[str, Any]:
    return {
        "question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN",
        "market_state": "UNCLEAR", "trend_state": "NONE", "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR", "structure_quality": 0.0,
        "directional_pressure": "NEUTRAL", "current_pressure": "NEUTRAL",
        "counter_pressure": "NONE", "dominant_direction": "NEUTRAL",
        "directional_state": "UNRESOLVED", "market_phase": "UNRESOLVED",
        "transition": "UNRESOLVED", "transition_status": "UNRESOLVED",
        "transition_confirmed": False, "transition_committed": False,
        "structural_persistence": False, "confidence": 0.0,
        "evidence": [f"valid_candles={valid}", f"invalid_candles={invalid}"],
        "observations": [f"valid_candles={valid}", f"invalid_candles={invalid}"],
        "conflicts": ["DATA_QUALITY_ANOMALIES"] if invalid else [],
        "reasons": [reason],
        "reasoning_trace": [f"QUESTION -> {QUESTION}", f"STATE -> UNCLEAR because={reason}"],
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "arbitration_order": ARBITRATION_ORDER,
            "trade_boundary": "MARKET_STATE_ONLY",
            "primary_thesis": {"direction": "NEUTRAL", "status": "UNRESOLVED"},
        },
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V11",
        "e1_trade_authority": False, "analysis_status": "INCOMPLETE",
    }


def analyze_e1_professional_v11(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    good, invalid = _clean(bars)
    if len(good) < MIN_BARS:
        return _incomplete("INSUFFICIENT_RELIABLE_CLOSED_CANDLES", len(good), invalid)
    if invalid:
        return _incomplete("DATA_QUALITY_ANOMALIES_PRESENT_CLASSIFICATION_WITHHELD", len(good), invalid)

    closes = [b["close"] for b in good]
    atr = _atr(good, 14)
    atr50 = _atr(good, 50)
    if atr <= 0 or atr50 <= 0:
        return _incomplete("ATR_INVALID", len(good), invalid)

    e20s, e50s = _ema(closes, 20), _ema(closes, 50)
    ema = "UP" if e20s[-1] > e50s[-1] else "DOWN" if e20s[-1] < e50s[-1] else "NEUTRAL"
    ema_gap = (e20s[-1] - e50s[-1]) / atr
    horizons = (5, 10, 20, 40)
    thresholds = (.15, .20, .30, .40)
    slopes = [_slope(closes, atr, n) for n in horizons]
    states = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s, t in zip(slopes, thresholds)]
    up, down = states.count("UP"), states.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "NEUTRAL"
    consensus = max(up, down) / 4.0
    long_states = states[1:]
    long_up, long_down = long_states.count("UP"), long_states.count("DOWN")
    long_direction = "UP" if long_up > long_down else "DOWN" if long_down > long_up else "NEUTRAL"
    long_consensus = max(long_up, long_down) / 3.0
    if pressure == "UP":
        persistence = sum(s >= t for s, t in zip(slopes, (.20, .25, .35, .45))) / 4.0
        long_persistence = sum(s >= t for s, t in zip(slopes[1:], (.25, .35, .45))) / 3.0
    elif pressure == "DOWN":
        persistence = sum(s <= -t for s, t in zip(slopes, (.20, .25, .35, .45))) / 4.0
        long_persistence = sum(s <= -t for s, t in zip(slopes[1:], (.25, .35, .45))) / 3.0
    else:
        persistence = long_persistence = 0.0

    st = _structure(good, atr)
    sd = _dir(st["state"])
    sr = _dir(_structure(good[-80:], _atr(good[-80:], 14))["state"])
    sl40 = _dir(_structure(good[-40:], _atr(good[-40:], 14))["state"])
    structural_persistence = sd in {"UP", "DOWN"} and sd == sr == sl40
    structure_strength = sd in {"UP", "DOWN"} and st["quality"] >= .52

    prior_atr = _atr(good[-64:-14], 50) if len(good) >= 64 else atr50
    volatility_ratio = atr / max(prior_atr, 1e-12)
    compression, expansion = volatility_ratio < .78, volatility_ratio > 1.20
    eff20, eff40 = _efficiency(closes, 20), _efficiency(closes, 40)

    recent_delta = closes[-1] - closes[-6]
    recent_pressure = "UP" if recent_delta >= .15 * atr else "DOWN" if recent_delta <= -.15 * atr else "NEUTRAL"
    recent8 = _slope(closes, atr, 8)
    context30 = _slope(closes, atr, 30)
    context_flip = abs(context30) >= .45 and abs(recent8) >= .65 and (context30 > 0) != (recent8 > 0)

    # Professional hierarchy: structure + long horizon are the thesis; EMA is context.
    structural_candidate = structure_strength and sd in {"UP", "DOWN"}
    persistent_long = long_direction in {"UP", "DOWN"} and long_consensus >= 2/3 and long_persistence >= 2/3
    if structural_candidate and persistent_long and sd == long_direction:
        dominant = sd
        basis = "STRUCTURE_LONG_HORIZON_PERSISTENCE"
    elif structural_candidate and sd == ema and abs(ema_gap) >= .50:
        dominant = sd
        basis = "STRUCTURE_EMA_ALIGNMENT"
    elif persistent_long and ema == long_direction and abs(ema_gap) >= .50:
        dominant = long_direction
        basis = "LONG_HORIZON_EMA_ALIGNMENT"
    elif structural_candidate and persistent_long:
        dominant = sd
        basis = "STRUCTURE_WITH_LONG_HORIZON_SUPPORT"
    else:
        dominant = "NEUTRAL"
        basis = "NO_DOMINANT_REGIME"

    # A transition is not a score. It is a state commitment requiring repricing evidence.
    opposite_to_ema = dominant in {"UP", "DOWN"} and ema == ("DOWN" if dominant == "UP" else "UP")
    opposite_structure = structural_candidate and dominant in {"UP", "DOWN"} and sd == dominant
    opposite_long = persistent_long and long_direction == dominant
    opposite_pressure = pressure == dominant and recent_pressure == dominant
    bos_supports = st["bos"] == dominant
    persistent_repricing = opposite_structure and structural_persistence and opposite_long and long_persistence >= .667 and bos_supports and opposite_pressure
    transition_confirmed = bool(persistent_repricing and opposite_to_ema and context_flip)

    counter = []
    if dominant in {"UP", "DOWN"}:
        opp = "DOWN" if dominant == "UP" else "UP"
        if recent_pressure == opp:
            counter.append("COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
        if pressure == opp:
            counter.append("SHORT_HORIZON_COUNTER_PRESSURE")
        if context_flip and not transition_confirmed:
            counter.append("CONTEXT_FLIP_REQUIRES_STRUCTURAL_REPRICING")
    if not counter:
        counter.append("NO_MATERIAL_COUNTER_EVIDENCE")

    if transition_confirmed:
        state, transition, phase = "TRANSITION", "CONFIRMED", "TRANSITION"
    elif dominant in {"UP", "DOWN"}:
        state = "TREND_UP" if dominant == "UP" else "TREND_DOWN"
        transition = "WATCH" if context_flip or pressure != dominant else "ABSENT"
        phase = "PULLBACK" if recent_pressure != dominant and recent_pressure != "NEUTRAL" else "IMPULSE" if recent_pressure == dominant else "CONSOLIDATION"
    elif compression:
        state, transition, phase = "COMPRESSION", "WATCH" if context_flip else "ABSENT", "UNRESOLVED"
    elif expansion:
        state, transition, phase = "EXPANSION", "WATCH" if context_flip else "ABSENT", "UNRESOLVED"
    elif abs(slopes[2]) < .65 and eff20 < .35 and eff40 < .40:
        state, transition, phase = "RANGE", "ABSENT", "RANGE"
    else:
        state, transition, phase = "UNCLEAR", "WATCH" if context_flip else "ABSENT", "UNRESOLVED"

    if state == "TREND_UP" or state == "TREND_DOWN":
        directional_state = "CONFIRMED" if persistent_long and structural_persistence else "DEVELOPING"
    elif state == "TRANSITION":
        directional_state = "CONFLICTED"
    else:
        directional_state = "NEUTRAL"

    stability = max(0.0, min(1.0, .40 * long_consensus + .30 * long_persistence + .20 * (1.0 if structural_persistence else 0.0) + .10 * (1.0 if ema == dominant else 0.0)))
    support = max(0.0, min(1.0, .30 * consensus + .25 * long_consensus + .25 * long_persistence + .20 * (1.0 if structure_strength and sd == dominant else 0.0)))
    confidence = max(0.0, min(.99, .60 * support + .30 * stability + .10 * max(eff20, eff40)))
    if state == "UNCLEAR":
        confidence = min(confidence, .60)
    if transition_confirmed:
        confidence = min(confidence, .85)

    reasons = [
        "V11_STANDALONE_E1", "V11_DATA_INTEGRITY_VALIDATED", "V11_STRUCTURE_FIRST_HIERARCHY",
        "V11_LONG_HORIZON_CONFIRMATION", "V11_EMA_AS_CONTEXT_NOT_AUTHORITY",
        "V11_COUNTER_PRESSURE_IS_PHASE_NOT_REVERSAL",
        "V11_TRANSITION_REQUIRES_STRUCTURAL_REPRICING",
        "V11_TRANSITION_REQUIRES_PERSISTENCE", "V11_MARKET_STATE_ONLY_BOUNDARY",
    ]
    if recent_pressure != dominant and dominant in {"UP", "DOWN"}:
        reasons.append("COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    if context_flip and not transition_confirmed:
        reasons.append("CONTEXT_FLIP_REQUIRES_STRUCTURAL_REPRICING")
    if recent_pressure != dominant and dominant in {"UP", "DOWN"}:
        reasons.append("SINGLE_COUNTER_MOVE_CANNOT_COMMIT_TRANSITION")
    if transition_confirmed:
        reasons.append("V11_TRANSITION_COMMITTED_BY_STRUCTURAL_REPRICING")
    reasons.extend(counter)

    evidence = [
        f"valid_candles={len(good)}", f"invalid_candles={invalid}", f"ema20_vs_ema50={ema}",
        f"ema_gap_atr={ema_gap:.3f}", *(f"price_slope_{n}_atr={s:.3f}" for n, s in zip(horizons, slopes)),
        f"multi_horizon={','.join(states)}", f"directional_consensus={consensus:.3f}",
        f"long_horizon_direction={long_direction}", f"long_horizon_consensus={long_consensus:.3f}",
        f"long_horizon_persistence={long_persistence:.3f}", f"structure={st['state']}",
        f"structure_quality={st['quality']:.3f}", f"structure_persistence={structural_persistence}",
        f"structure_bos={st['bos']}", f"volatility_ratio={volatility_ratio:.3f}",
        f"recent_pressure={recent_pressure}", f"context_flip={context_flip}",
        f"dominant_direction={dominant}", f"transition_confirmed={transition_confirmed}",
    ]
    trace = [
        f"QUESTION -> {QUESTION}", "DATA -> reliable closed-candle OHLC validated",
        f"STRUCTURE -> {st['state']} quality={st['quality']:.2f} persistent={structural_persistence}",
        f"LONG_HORIZON -> direction={long_direction} consensus={long_consensus:.3f} persistence={long_persistence:.3f}",
        f"EMA_CONTEXT -> relation={ema} gap_atr={ema_gap:.3f}",
        f"PRESSURE -> {pressure}; recent={recent_pressure}; horizons={','.join(states)}",
        f"DOMINANT_CONTEXT -> {dominant} basis={basis}", f"PHASE -> {phase}",
        f"TRANSITION -> status={transition} confirmed={transition_confirmed}",
        "RULE -> short counter-pressure cannot overturn persistent structural context",
        "RULE -> transition requires structural repricing + persistence + context flip",
        "BOUNDARY -> E1 reports market state only",
    ]
    professional = {
        "task": "DESCRIBE_MARKET_STATE_ONLY", "arbitration_order": ARBITRATION_ORDER,
        "primary_thesis": {"direction": dominant, "status": directional_state, "basis": basis, "market_state": state},
        "structure_authority": {"direction": sd, "quality": round(st["quality"], 3), "persistent": structural_persistence},
        "long_horizon_authority": {"direction": long_direction, "consensus": round(long_consensus, 3), "persistence": round(long_persistence, 3)},
        "counter_evidence": counter,
        "transition_commitment": {
            "confirmed": transition_confirmed,
            "committed": transition_confirmed,
            "requirements": ["STRUCTURAL_REPRICING", "STRUCTURAL_PERSISTENCE", "LONG_HORIZON_PERSISTENCE", "OPPOSITE_EMA_CONTEXT", "RECENT_PRESSURE", "CONTEXT_FLIP"],
        },
        "trade_boundary": "MARKET_STATE_ONLY",
    }
    return {
        "question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN", "market_state": state,
        "trend_state": dominant if state in {"TREND_UP", "TREND_DOWN"} else "NONE",
        "volatility_state": "CONTRACTING" if compression else "EXPANDING" if expansion else "NORMAL",
        "structure_state": st["state"], "structure_quality": round(st["quality"], 3),
        "directional_pressure": dominant, "current_pressure": "BULLISH" if recent_pressure == "UP" else "BEARISH" if recent_pressure == "DOWN" else "NEUTRAL",
        "counter_pressure": "PULLBACK_WITHIN_TREND" if recent_pressure != dominant and dominant in {"UP", "DOWN"} else "NONE",
        "dominant_direction": dominant, "directional_state": directional_state, "market_phase": phase,
        "range_state": "RANGE" if state == "RANGE" else "NOT_RANGE", "compression": "YES" if compression else "NO", "expansion": "YES" if expansion else "NO",
        "transition": transition, "transition_status": transition, "transition_confirmed": transition_confirmed,
        "transition_committed": transition_confirmed, "structural_persistence": structural_persistence,
        "confidence": round(confidence, 3), "evidence": evidence, "observations": evidence,
        "conflicts": counter if counter != ["NO_MATERIAL_COUNTER_EVIDENCE"] else [],
        "reasons": list(dict.fromkeys(reasons)), "reasoning_trace": trace,
        "professional_reasoning": professional,
        "independent_evidence": {
            "data_quality": {"valid_candles": len(good), "invalid_candles": invalid},
            "structure": st,
            "pressure": {"direction": pressure, "recent": recent_pressure, "consensus": consensus},
            "persistence": {"score": persistence, "long_horizon_score": long_persistence, "efficiency20": eff20, "efficiency40": eff40},
            "ema": {"relation": ema, "gap_atr": ema_gap},
            "volatility": {"atr14": atr, "prior": prior_atr, "ratio": volatility_ratio},
        },
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V11",
        "e1_trade_authority": False, "analysis_status": "COMPLETE",
    }
