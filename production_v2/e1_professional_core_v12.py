"""E1 V12 — standalone professional market-state analyst.

E1 answers one question only: What is the market doing right now?
It does not produce setup, entry, stop, target, RR, risk or trade decisions.

V12 principles:
- structural state and long-horizon persistence outrank EMA context
- counter-trend structure is explicitly represented, never silently promoted
- transition requires persistent structural repricing, not a single flip
- compression/expansion are regime modifiers when a directional regime exists
- uncertainty is preferred over forced classification
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
ARBITRATION_ORDER = [
    "DATA_QUALITY", "STRUCTURE", "LONG_HORIZON", "PERSISTENCE",
    "PRESSURE", "EMA_CONTEXT", "VOLATILITY", "COUNTER_EVIDENCE", "TRANSITION",
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
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN_V12",
        "market_state": "UNCLEAR", "trend_state": "NONE", "volatility_state": "UNKNOWN",
        "structure_state": "UNCLEAR", "structure_quality": 0.0,
        "structure_alignment": "UNRESOLVED", "directional_pressure": "NEUTRAL",
        "current_pressure": "NEUTRAL", "counter_pressure": "NONE",
        "dominant_direction": "NEUTRAL", "directional_state": "UNRESOLVED",
        "market_phase": "UNRESOLVED", "transition": "UNRESOLVED",
        "transition_status": "UNRESOLVED", "transition_confirmed": False,
        "transition_committed": False, "structural_persistence": False,
        "confidence": 0.0,
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
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V12",
        "e1_trade_authority": False, "analysis_status": "INCOMPLETE",
    }


def analyze_e1_professional_v12(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
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

    structural_candidate = structure_strength and sd in {"UP", "DOWN"}
    persistent_long = long_direction in {"UP", "DOWN"} and long_consensus >= 2/3 and long_persistence >= 2/3

    # Dominant direction: structure + persistent long horizon first. EMA can support,
    # but cannot override a structural/long-horizon conflict by itself.
    if structural_candidate and persistent_long and sd == long_direction:
        dominant, basis = sd, "STRUCTURE_LONG_HORIZON_PERSISTENCE"
    elif persistent_long and ema == long_direction and abs(ema_gap) >= .50:
        dominant, basis = long_direction, "LONG_HORIZON_EMA_ALIGNMENT"
    elif structural_candidate and sd == ema and abs(ema_gap) >= .50 and long_direction in {"NEUTRAL", sd}:
        dominant, basis = sd, "STRUCTURE_EMA_ALIGNMENT"
    elif structural_candidate and persistent_long:
        dominant, basis = sd, "STRUCTURE_WITH_LONG_HORIZON_SUPPORT"
    else:
        dominant, basis = "NEUTRAL", "NO_DOMINANT_REGIME"

    # Explicitly classify structural disagreement instead of allowing it to
    # silently override the dominant regime (e.g. BTC: TREND_DOWN + bullish structure).
    if dominant in {"UP", "DOWN"} and sd == dominant:
        structure_alignment = "ALIGNED"
    elif dominant in {"UP", "DOWN"} and sd in {"UP", "DOWN"} and sd != dominant:
        structure_alignment = "COUNTER_TREND"
    elif sd == "MIXED":
        structure_alignment = "MIXED"
    else:
        structure_alignment = "UNRESOLVED"

    # Transition is a separate commitment test. It must show repricing in the
    # direction opposite to the current dominant state across structure,
    # long-horizon pressure, EMA, pressure, persistence and BOS.
    transition_candidate = "DOWN" if dominant == "UP" else "UP" if dominant == "DOWN" else "NEUTRAL"
    candidate_structure = structural_candidate and sd == transition_candidate
    candidate_long = long_direction == transition_candidate and long_consensus >= 2/3 and long_persistence >= 2/3
    candidate_pressure = pressure == transition_candidate and recent_pressure == transition_candidate
    candidate_ema = ema == transition_candidate and abs(ema_gap) >= .50
    candidate_bos = st["bos"] == transition_candidate
    candidate_persistent_structure = candidate_structure and structural_persistence
    persistent_repricing = all((candidate_persistent_structure, candidate_long, candidate_pressure, candidate_ema, candidate_bos))
    transition_confirmed = bool(persistent_repricing and context_flip)

    counter = []
    if dominant in {"UP", "DOWN"}:
        opp = "DOWN" if dominant == "UP" else "UP"
        if sd == opp:
            counter.append("COUNTER_TREND_STRUCTURE_PRESENT")
        if pressure == opp:
            counter.append("SHORT_HORIZON_COUNTER_PRESSURE")
        if recent_pressure == opp:
            counter.append("RECENT_COUNTER_PRESSURE")
        if context_flip and not transition_confirmed:
            counter.append("CONTEXT_FLIP_REQUIRES_PERSISTENT_REPRICING")
    if not counter:
        counter.append("NO_MATERIAL_COUNTER_EVIDENCE")

    # Directional state is decided before volatility labels. Compression and
    # expansion are overlays when a directional regime is already established.
    if transition_confirmed:
        state, transition, phase = "TRANSITION", "CONFIRMED", "TRANSITION"
    elif dominant in {"UP", "DOWN"}:
        state = "TREND_UP" if dominant == "UP" else "TREND_DOWN"
        transition = "WATCH" if context_flip or pressure != dominant or sd != dominant else "ABSENT"
        phase = "PULLBACK" if recent_pressure != dominant and recent_pressure != "NEUTRAL" else "IMPULSE" if recent_pressure == dominant else "CONSOLIDATION"
    elif abs(slopes[2]) < .65 and eff20 < .35 and eff40 < .40:
        state, transition, phase = "RANGE", "ABSENT", "RANGE"
    elif compression:
        state, transition, phase = "COMPRESSION", "WATCH" if context_flip else "ABSENT", "UNRESOLVED"
    elif expansion:
        state, transition, phase = "EXPANSION", "WATCH" if context_flip else "ABSENT", "UNRESOLVED"
    else:
        state, transition, phase = "UNCLEAR", "WATCH" if context_flip else "ABSENT", "UNRESOLVED"

    if state in {"TREND_UP", "TREND_DOWN"}:
        directional_state = "CONFIRMED" if persistent_long and structural_persistence and sd == dominant else "DEVELOPING"
    elif state == "TRANSITION":
        directional_state = "CONFLICTED"
    else:
        directional_state = "NEUTRAL"

    # Confidence is evidence quality, not probability of profit. Penalize
    # unresolved structural disagreement and reward persistence/alignment.
    alignment_score = 1.0 if structure_alignment == "ALIGNED" else .35 if structure_alignment == "COUNTER_TREND" else .50 if structure_alignment == "MIXED" else .25
    support = .30 * consensus + .25 * long_consensus + .25 * long_persistence + .20 * alignment_score
    stability = .45 * long_persistence + .30 * (1.0 if structural_persistence else 0.0) + .15 * alignment_score + .10 * (1.0 if ema == dominant else 0.0)
    confidence = max(0.0, min(.99, .60 * support + .30 * stability + .10 * max(eff20, eff40)))
    if state == "UNCLEAR":
        confidence = min(confidence, .60)
    if state == "TRANSITION":
        confidence = min(confidence, .85)
    if structure_alignment == "COUNTER_TREND" and not transition_confirmed:
        confidence = min(confidence, .82)

    reasons = [
        "V12_DATA_INTEGRITY_VALIDATED",
        "V12_STRUCTURE_FIRST_HIERARCHY",
        f"V12_DOMINANT_BASIS={basis}",
        "V12_EMA_AS_CONTEXT_NOT_AUTHORITY",
        "V12_COUNTER_TREND_STRUCTURE_CANNOT_AUTO_FLIP_STATE",
        "V12_TRANSITION_REQUIRES_PERSISTENT_REPRICING",
    ]
    if persistent_long:
        reasons.append("V12_LONG_HORIZON_PERSISTENCE_CONFIRMED")
    if structural_persistence:
        reasons.append("V12_STRUCTURAL_PERSISTENCE_CONFIRMED")
    if compression:
        reasons.append("V12_VOLATILITY_COMPRESSION_DETECTED")
    if expansion:
        reasons.append("V12_VOLATILITY_EXPANSION_DETECTED")

    observations = [
        f"valid_candles={len(good)}", f"invalid_candles={invalid}",
        f"ema20_vs_ema50={ema}", f"ema_gap_atr={ema_gap:.3f}",
        *[f"price_slope_{n}_atr={s:.3f}" for n, s in zip(horizons, slopes)],
        f"multi_horizon={','.join(states)}", f"directional_consensus={consensus:.3f}",
        f"long_horizon_direction={long_direction}", f"long_horizon_consensus={long_consensus:.3f}",
        f"long_horizon_persistence={long_persistence:.3f}",
        f"structure={st['state']}", f"structure_quality={st['quality']:.3f}",
        f"structure_alignment={structure_alignment}", f"structural_persistence={structural_persistence}",
        f"structure_bos={st['bos']}", f"volatility_ratio={volatility_ratio:.3f}",
        f"recent_pressure={recent_pressure}", f"context_flip={context_flip}",
    ]

    return {
        "question": QUESTION,
        "reasoning_role": "MARKET_STATE_ANALYST",
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN_V12",
        "market_state": state,
        "trend_state": dominant if dominant in {"UP", "DOWN"} else "NONE",
        "volatility_state": "CONTRACTING" if compression else "EXPANDING" if expansion else "NORMAL",
        "structure_state": st["state"],
        "structure_quality": round(st["quality"], 4),
        "structure_alignment": structure_alignment,
        "directional_pressure": pressure,
        "current_pressure": recent_pressure,
        "counter_pressure": "PRESENT" if any(x != "NO_MATERIAL_COUNTER_EVIDENCE" for x in counter) else "NONE",
        "dominant_direction": dominant,
        "directional_state": directional_state,
        "market_phase": phase,
        "transition": transition,
        "transition_status": transition,
        "transition_confirmed": transition_confirmed,
        "transition_committed": transition_confirmed,
        "structural_persistence": structural_persistence,
        "confidence": round(confidence, 4),
        "evidence": observations,
        "observations": observations,
        "conflicts": ["COUNTER_TREND_STRUCTURE"] if structure_alignment == "COUNTER_TREND" else [],
        "reasons": reasons + counter,
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            f"STRUCTURE -> {st['state']} quality={st['quality']:.2f}",
            f"LONG_HORIZON -> {long_direction} consensus={long_consensus:.2f} persistence={long_persistence:.2f}",
            f"DOMINANT_DIRECTION -> {dominant} basis={basis}",
            f"STRUCTURE_ALIGNMENT -> {structure_alignment}",
            f"COUNTER_EVIDENCE -> {','.join(counter)}",
            f"TRANSITION_TEST -> {'CONFIRMED' if transition_confirmed else 'NOT_CONFIRMED'}",
            f"FINAL_MARKET_STATE -> {state}",
        ],
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY",
            "arbitration_order": ARBITRATION_ORDER,
            "trade_boundary": "MARKET_STATE_ONLY",
            "primary_thesis": {"direction": dominant, "status": directional_state},
            "dominant_basis": basis,
            "structure_alignment": structure_alignment,
            "transition_rule": "STRUCTURE + LONG_HORIZON + PRESSURE + EMA + BOS + PERSISTENCE + CONTEXT_REPRICING",
            "counter_trend_rule": "COUNTER_TREND_STRUCTURE_IS_EVIDENCE_NOT_STATE_OVERRIDE",
        },
        "e1_contract_version": "PROFESSIONAL_MARKET_STATE_V12",
        "e1_engine_version": "PROFESSIONAL_MARKET_STATE_V12",
        "e1_trade_authority": False,
        "analysis_status": "COMPLETE",
    }


__all__ = ["analyze_e1_professional_v12"]
