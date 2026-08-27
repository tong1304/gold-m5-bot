"""E1 — single professional Market-State Brain.

E1 is the sole decision authority for market-state classification.  No E1
wrapper, reconciliation brain, or transition-guard brain is called from here.
Helpers in this file only calculate evidence; analyze_e1() owns arbitration.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
QUESTION = "What is the market doing right now?"
OWNERSHIP = {
    "owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "market_regime", "regime_transition"],
    "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution"],
}
MIN_BARS = 60


def _num(x: Any):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _ema(xs: list[float], p: int) -> list[float]:
    if not xs:
        return []
    a = 2.0 / (p + 1.0)
    cur = xs[0]
    out = [cur]
    for x in xs[1:]:
        cur = a * x + (1.0 - a) * cur
        out.append(cur)
    return out


def _atr(bars: list[dict[str, Any]], n: int = 14) -> float:
    trs: list[float] = []
    prev = None
    for b in bars[-n:]:
        h, l, c = b["high"], b["low"], b["close"]
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return mean(trs) if trs else 0.0


def _slope(xs: list[float], atr: float, n: int) -> float:
    return 0.0 if len(xs) <= n or atr <= 0 else (xs[-1] - xs[-1-n]) / atr


def _eff(xs: list[float], n: int) -> float:
    x = xs[-n:]
    if len(x) < 2:
        return 0.0
    path = sum(abs(x[i] - x[i-1]) for i in range(1, len(x)))
    return abs(x[-1] - x[0]) / max(path, 1e-12)


def _structure(bars: list[dict[str, Any]]) -> tuple[str, float]:
    hs, ls, w = [], [], 2
    for i in range(w, len(bars) - w):
        win = bars[i-w:i+w+1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in win): hs.append(h)
        if l <= min(x["low"] for x in win): ls.append(l)
    hs, ls = hs[-6:], ls[-6:]
    hh = sum(hs[i] > hs[i-1] for i in range(1, len(hs)))
    lh = sum(hs[i] < hs[i-1] for i in range(1, len(hs)))
    hl = sum(ls[i] > ls[i-1] for i in range(1, len(ls)))
    ll = sum(ls[i] < ls[i-1] for i in range(1, len(ls)))
    bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear: return "BULLISH", min(1.0, .65 + .08 * bull)
    if bear >= 2 and bear > bull: return "BEARISH", min(1.0, .65 + .08 * bear)
    if hh + hl >= 2 and hh + hl > lh + ll: return "BULLISH", .55
    if lh + ll >= 2 and lh + ll > hh + hl: return "BEARISH", .55
    return "MIXED", .30


def _result(base: dict[str, Any], state: str, pressure: str, volatility: str,
            structure: str, sq: float, compression: bool, expansion: bool,
            transition: bool, confidence: float, evidence: list[str],
            conflicts: list[str], reason: str, maturity: str,
            trend_confirmed: bool) -> dict[str, Any]:
    ts = "UP" if state == "TREND_UP" else "DOWN" if state == "TREND_DOWN" else "NONE"
    direction = "UP" if pressure == "UP" else "DOWN" if pressure == "DOWN" else "NEUTRAL"
    reasons = list(conflicts)
    if transition: reasons.append("REGIME_CONFLICT_ACTIVE")
    elif state == "UNCLEAR": reasons.append("REGIME_CONFIRMATION_INSUFFICIENT")
    return {
        **base, "market_state": state, "directional_pressure": direction,
        "trend_state": ts, "volatility_state": volatility,
        "structure_state": structure, "structure_quality": round(sq, 3),
        "compression": "PRESENT" if compression else "ABSENT",
        "expansion": "PRESENT" if expansion else "ABSENT",
        "transition": "PRESENT" if transition else "ABSENT",
        "confidence": round(max(0.0, min(.99, confidence)), 3),
        "evidence": evidence, "conflicts": conflicts, "reasons": reasons,
        "reasoning_trace": [
            f"QUESTION -> {QUESTION}",
            f"STRUCTURE -> {structure} quality={sq:.2f}",
            f"PRESSURE -> {direction}",
            f"REGIME_CONFIRMATION -> trend_confirmed={trend_confirmed} maturity={maturity}",
            f"STATE -> {state} because={reason}",
            f"TRANSITION -> {'PRESENT' if transition else 'ABSENT'}",
        ],
        "professional_reasoning": {
            "task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": state,
            "market_state": state, "direction": direction,
            "directional_pressure": direction, "trend_maturity": maturity,
            "trend_confirmed": trend_confirmed, "conflict_detected": bool(conflicts),
            "conflict_count": len(conflicts), "classification_reason": reason,
            "ownership_boundaries": OWNERSHIP,
        },
        "analysis_status": "COMPLETE",
    }


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    """One and only E1 decision function.

    Calculates evidence, arbitrates contradictions, classifies the regime, and
    returns the professional market-state contract.  It never consumes E2-E9.
    """
    valid, bad = [], []
    for i, b in enumerate(bars or []):
        if not isinstance(b, dict):
            bad.append(f"bar_{i}_not_mapping"); continue
        v = {k: _num(b.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            bad.append(f"bar_{i}_ohlc_invalid"); continue
        if v["high"] < max(v["open"], v["close"]) or v["low"] > min(v["open"], v["close"]) or v["high"] < v["low"]:
            bad.append(f"bar_{i}_ohlc_inconsistent"); continue
        valid.append({**b, **v})

    base = {"question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST",
            "trade_decision_authority": False, "decision_authority": "E9_ONLY",
            "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN"}
    if len(valid) < MIN_BARS:
        return {**base, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL",
                "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR",
                "structure_quality": 0.0, "compression": "UNKNOWN", "expansion": "UNKNOWN",
                "transition": "UNKNOWN", "confidence": 0.0, "evidence": ["valid_candles_below_minimum"],
                "conflicts": bad[:6], "reasons": ["insufficient reliable candles; classification withheld"],
                "analysis_status": "INCOMPLETE",
                "professional_reasoning": {"task": "DESCRIBE_MARKET_STATE_ONLY", "trend_maturity": "UNAVAILABLE",
                    "trend_confirmed": False, "classification_reason": "insufficient reliable candles; classification withheld",
                    "ownership_boundaries": OWNERSHIP}}

    c = [b["close"] for b in valid]
    atr14 = _atr(valid, 14)
    if atr14 <= 0:
        return {**base, "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "trend_state": "NONE",
                "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "structure_quality": 0.0,
                "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "confidence": 0.0,
                "evidence": ["atr_invalid"], "conflicts": ["ATR_INVALID"],
                "reasons": ["ATR invalid; classification withheld"], "analysis_status": "INCOMPLETE",
                "professional_reasoning": {"task": "DESCRIBE_MARKET_STATE_ONLY", "trend_maturity": "UNAVAILABLE",
                    "trend_confirmed": False, "classification_reason": "ATR invalid; classification withheld",
                    "ownership_boundaries": OWNERSHIP}}

    e20s, e50s = _ema(c, 20), _ema(c, 50)
    rel = "UP" if e20s[-1] > e50s[-1] else "DOWN" if e20s[-1] < e50s[-1] else "FLAT"
    gap = (e20s[-1] - e50s[-1]) / atr14
    es20, es50 = _slope(e20s, atr14, 5), _slope(e50s, atr14, 5)
    ss, ms, ls = (_slope(c, atr14, n) for n in (5, 10, 20))
    dirs = ["UP" if ss > .15 else "DOWN" if ss < -.15 else "FLAT",
            "UP" if ms > .20 else "DOWN" if ms < -.20 else "FLAT",
            "UP" if ls > .30 else "DOWN" if ls < -.30 else "FLAT"]
    up, down = dirs.count("UP"), dirs.count("DOWN")
    pressure = "UP" if up > down else "DOWN" if down > up else "BALANCED"
    aligned = sum((ss >= .20, ms >= .30, ls >= .45)) if pressure == "UP" else sum((ss <= -.20, ms <= -.30, ls <= -.45)) if pressure == "DOWN" else 0
    persistence = aligned / 3.0
    e10, e20 = _eff(c, 10), _eff(c, 20)
    structure, sq = _structure(valid)
    sd = "UP" if structure == "BULLISH" else "DOWN" if structure == "BEARISH" else "FLAT"

    ema_ok = pressure in ("UP", "DOWN") and rel == pressure and ((pressure == "UP" and es20 >= -.05 and es50 >= -.10) or (pressure == "DOWN" and es20 <= .05 and es50 <= .10))
    ema_conflict = pressure in ("UP", "DOWN") and rel in ("UP", "DOWN") and rel != pressure
    struct_conflict = pressure in ("UP", "DOWN") and sd in ("UP", "DOWN") and sd != pressure
    horizon_conflict = len({x for x in dirs if x in ("UP", "DOWN")}) > 1
    conflicts = []
    if bad: conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict: conflicts.append("EMA_VS_PRICE_PRESSURE")
    if struct_conflict: conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict: conflicts.append("SHORT_VS_LONG_HORIZON")
    if pressure == "BALANCED": conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")

    consensus = pressure in ("UP", "DOWN") and max(up, down) >= 2 and persistence >= 2/3
    strong_structure = sd == pressure and sq >= .55
    trend = consensus and ema_ok and abs(gap) >= .10 and e20 >= .12 and not ema_conflict and not struct_conflict and (strong_structure or persistence == 1.0)

    # Professional transition arbitration: a recent impulse alone is not a
    # transition. It must materially contradict persistent prior context.
    prior = (c[-31] - c[-71]) / atr14 if len(c) >= 71 else 0.0
    recent = (c[-1] - c[-11]) / atr14 if len(c) >= 11 else 0.0
    impulse_conflict = len(c) >= 71 and abs(prior) >= .35 and abs(recent) >= .80 and (prior > 0) != (recent > 0)
    transition = (not trend) and (impulse_conflict or ((ema_conflict or struct_conflict) and persistence >= 1/3) or (horizon_conflict and e20 < .45))
    if impulse_conflict and "RECENT_IMPULSE_VS_PRIOR_CONTEXT" not in conflicts:
        conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")

    ar = _atr(valid, 14) / max(_atr(valid, 50), 1e-12)
    compression, expansion = ar < .78, ar > 1.18

    if transition:
        state, reason = "TRANSITION", "material conflict between persistent context and current auction"
    elif compression and pressure == "BALANCED":
        state, reason = "COMPRESSION", "volatility compression with balanced direction"
    elif trend:
        state, reason = ("TREND_UP" if pressure == "UP" else "TREND_DOWN"), "persistent multi-horizon direction with EMA and structure coherence"
    elif expansion and pressure in ("UP", "DOWN") and e10 >= .25:
        state, reason = "EXPANSION", "volatility expansion with directional displacement"
    elif pressure == "BALANCED" and e20 < .35:
        state, reason = "RANGE", "low directional efficiency and balanced pressure"
    else:
        state, reason = "UNCLEAR", "directional evidence exists but regime confirmation is insufficient"

    maturity = "ESTABLISHED" if trend else "DIRECTIONAL_ONLY" if pressure in ("UP", "DOWN") else "NONE"
    confidence = .45 + .25 * sq + .20 * persistence + .10 * min(1.0, e20/.7) + .10 * float(ema_ok) - .05 * len(conflicts)
    evidence = [
        f"ema20_vs_ema50={rel}", f"ema_gap_atr={gap:.3f}", f"ema20_slope_atr={es20:.3f}",
        f"ema50_slope_atr={es50:.3f}", f"price_slope_atr={ss:.3f}", f"price_medium_slope_atr={ms:.3f}",
        f"price_long_slope_atr={ls:.3f}", f"structure={structure}", f"structure_quality={sq:.3f}",
        f"directional_pressure={'BULLISH' if pressure == 'UP' else 'BEARISH' if pressure == 'DOWN' else 'NEUTRAL'}",
        f"price_consensus={max(up, down)}/3", f"trend_persistence={persistence:.3f}",
        f"price_efficiency_10={e10:.3f}", f"price_efficiency_20={e20:.3f}", f"trend_maturity={maturity}",
        f"prior_context_slope_atr={prior:.3f}", f"recent_impulse_slope_atr={recent:.3f}",
    ]
    return _result(base, state, pressure, "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL",
                   structure, sq, compression, expansion, transition, confidence, evidence, conflicts,
                   reason, maturity, trend)


__all__ = ["MARKET_STATES", "QUESTION", "OWNERSHIP", "analyze_e1"]
