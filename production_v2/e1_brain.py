"""E1 — Professional Market-State Brain.

E1 answers one question only: What is the market doing right now?
It uses closed-candle evidence, structure, volatility, pressure and persistence.
It never chooses a setup, entry, risk or trade action.
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
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"
OWNERSHIP = {"owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "market_regime", "regime_transition"], "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution"]}


def _num(x: Any) -> float | None:
    try: x = float(x)
    except (TypeError, ValueError): return None
    return x if isfinite(x) else None


def _ema(v: list[float], p: int) -> list[float]:
    if not v: return []
    a, cur = 2.0 / (p + 1.0), v[0]
    out = [cur]
    for x in v[1:]: cur = a * x + (1 - a) * cur; out.append(cur)
    return out


def _atr(bars: list[dict[str, Any]], p: int, start: int | None = None, end: int | None = None) -> float:
    sample = (bars[start:end] if start is not None or end is not None else bars)[-p:]
    trs, prev = [], None
    for b in sample:
        h, l, c = b["high"], b["low"], b["close"]
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))); prev = c
    return mean(trs) if trs else 0.0


def _slope(v: list[float], atr: float, n: int) -> float:
    return 0.0 if atr <= 0 or len(v) <= n else (v[-1] - v[-1 - n]) / atr


def _eff(v: list[float], n: int) -> float:
    s = v[-n:]
    if len(s) < 2: return 0.0
    path = sum(abs(s[i] - s[i - 1]) for i in range(1, len(s)))
    return abs(s[-1] - s[0]) / max(path, 1e-12)


def _structure(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    highs, lows = [], []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        w = bars[i-PIVOT_WING:i+PIVOT_WING+1]; h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in w): highs.append((i, h))
        if l <= min(x["low"] for x in w): lows.append((i, l))
    highs, lows = highs[-6:], lows[-6:]
    hh = sum(highs[i][1] > highs[i-1][1] for i in range(1, len(highs)))
    lh = sum(highs[i][1] < highs[i-1][1] for i in range(1, len(highs)))
    hl = sum(lows[i][1] > lows[i-1][1] for i in range(1, len(lows)))
    ll = sum(lows[i][1] < lows[i-1][1] for i in range(1, len(lows)))
    bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear: state, quality = "BULLISH", min(1.0, .62 + .09 * bull)
    elif bear >= 2 and bear > bull: state, quality = "BEARISH", min(1.0, .62 + .09 * bear)
    elif hh + hl >= 2 and hh + hl > lh + ll: state, quality = "BULLISH", .52
    elif lh + ll >= 2 and lh + ll > hh + hl: state, quality = "BEARISH", .52
    else: state, quality = "MIXED", .30
    last = bars[-1]["close"]; sh = max((x[1] for x in highs), default=last); sl = min((x[1] for x in lows), default=last)
    buf = max(.10 * atr, 1e-12); bos_up, bos_dn = last > sh + buf, last < sl - buf
    return {"state": state, "quality": quality, "counts": {"HH": hh, "HL": hl, "LH": lh, "LL": ll}, "external_bos": "CONFIRMED_BOS" if bos_up or bos_dn else "NO_BOS", "bos_direction": "UP" if bos_up else "DOWN" if bos_dn else "NONE", "recent_swing_high": sh, "recent_swing_low": sl}


def _base() -> dict[str, Any]:
    return {"question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY", "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN"}


def _incomplete(reason: str, evidence: list[str], conflicts: list[str]) -> dict[str, Any]:
    pr = {"task": "DESCRIBE_MARKET_STATE_ONLY", "primary_state": "UNCLEAR", "market_state": "UNCLEAR", "direction": "NEUTRAL", "directional_pressure": "NEUTRAL", "directional_state": "UNRESOLVED", "trend_maturity": "UNRESOLVED", "trend_confirmed": False, "regime_stress": False, "transition_confirmed": False, "conflict_detected": bool(conflicts), "conflict_count": len(conflicts), "classification_reason": reason, "single_counter_candle": False, "pressure_score": 0.0, "structure_alignment": 0.0, "trend_score": 0.0, "directional_consensus": {"confirmed": False, "score": 0.0}, "regime_basis": reason, "independent_evidence": {"data_quality": evidence}, "evidence_hierarchy": EVIDENCE_HIERARCHY, "ownership_boundaries": OWNERSHIP}
    return {**_base(), "market_state": "UNCLEAR", "directional_pressure": "NEUTRAL", "directional_state": "UNRESOLVED", "trend_state": "NONE", "volatility_state": "UNKNOWN", "structure_state": "UNCLEAR", "structure_quality": 0.0, "range_state": "UNKNOWN", "compression": "UNKNOWN", "expansion": "UNKNOWN", "transition": "UNKNOWN", "regime_stress": "UNKNOWN", "confidence": 0.0, "evidence": evidence, "observations": evidence, "conflicts": conflicts, "reasons": [reason], "reasoning_trace": [f"QUESTION -> {QUESTION}", "DATA -> insufficient reliable closed candles", f"STATE -> UNCLEAR because={reason}", "DIRECTIONAL_STATE -> UNRESOLVED"], "professional_reasoning": pr, "analysis_status": "INCOMPLETE"}


def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    valid, invalid = [], 0
    for raw in bars or []:
        if not isinstance(raw, dict): invalid += 1; continue
        v = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()): invalid += 1; continue
        o, h, l, c = v["open"], v["high"], v["low"], v["close"]
        if h < l or h < max(o, c) or l > min(o, c): invalid += 1; continue
        valid.append({**raw, **v})
    if len(valid) < MIN_BARS:
        return _incomplete("insufficient reliable closed candles; classification withheld", [f"valid_candles={len(valid)}", f"minimum_required={MIN_BARS}"], ["DATA_QUALITY_ANOMALIES"] if invalid else [])
    closes = [b["close"] for b in valid]; atr14, atr50 = _atr(valid, 14), _atr(valid, 50)
    if atr14 <= 0 or atr50 <= 0: return _incomplete("ATR invalid; classification withheld", ["ATR_INVALID"], ["ATR_INVALID"])
    e20s, e50s = _ema(closes, 20), _ema(closes, 50); e20, e50 = e20s[-1], e50s[-1]
    ema = "UP" if e20 > e50 else "DOWN" if e20 < e50 else "FLAT"; ema_gap = (e20 - e50) / atr14
    ema20_s, ema50_s = _slope(e20s, atr14, 5), _slope(e50s, atr14, 5)
    lbs, th = (5, 10, 20, 40), (.15, .20, .30, .40); slopes = [_slope(closes, atr14, n) for n in lbs]
    horizons = ["UP" if s >= t else "DOWN" if s <= -t else "FLAT" for s, t in zip(slopes, th)]; up, dn = horizons.count("UP"), horizons.count("DOWN")
    long = horizons[1:]; lu, ld = long.count("UP"), long.count("DOWN")
    pressure = "UP" if up == 4 else "DOWN" if dn == 4 else "UP" if lu > ld else "DOWN" if ld > lu else "BALANCED"
    consensus, long_consensus = max(up, dn) / 4, max(lu, ld) / 3
    if pressure == "UP": persistence = sum((slopes[0]>=.20, slopes[1]>=.25, slopes[2]>=.35, slopes[3]>=.45))/4; long_persistence = sum((slopes[1]>=.25, slopes[2]>=.35, slopes[3]>=.45))/3
    elif pressure == "DOWN": persistence = sum((slopes[0]<=-.20, slopes[1]<=-.25, slopes[2]<=-.35, slopes[3]<=-.45))/4; long_persistence = sum((slopes[1]<=-.25, slopes[2]<=-.35, slopes[3]<=-.45))/3
    else: persistence = long_persistence = 0.0
    eff10, eff20, eff40 = (_eff(closes, n) for n in (10, 20, 40))
    st = _structure(valid, atr14); sd = "UP" if st["state"] == "BULLISH" else "DOWN" if st["state"] == "BEARISH" else "NEUTRAL"
    structural_proxy = st["state"] == "MIXED" and st["quality"] <= .30 and long_persistence >= .667 and long_consensus >= .667
    structure_alignment = 1.0 if sd == pressure and pressure != "BALANCED" else .75 if structural_proxy else .5 if pressure == "BALANCED" and st["state"] == "MIXED" else 0.0
    ema_alignment = 1.0 if pressure in {"UP", "DOWN"} and ema == pressure else 0.0
    ema_conflict = pressure in {"UP", "DOWN"} and ema in {"UP", "DOWN"} and ema != pressure
    structure_conflict = pressure in {"UP", "DOWN"} and sd in {"UP", "DOWN"} and sd != pressure
    horizon_conflict = up > 0 and dn > 0
    prior_atr = _atr(valid, 50, -64, -14) if len(valid) >= 64 else atr50; vol_ratio = atr14 / max(prior_atr, 1e-12)
    compression, expansion = vol_ratio < .78, vol_ratio > 1.10; volatility = "EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    pressure_score = consensus * (.65 + .35 * persistence)
    trend_score = .25*consensus + .25*persistence + .20*structure_alignment + .15*ema_alignment + .10*long_consensus + .05*max(eff20, eff40)
    established = pressure in {"UP","DOWN"} and consensus >= .75 and persistence >= .50 and structure_alignment >= .75 and ema_alignment == 1.0 and max(eff20,eff40) >= .22
    contextual = pressure in {"UP","DOWN"} and long_consensus >= .667 and long_persistence >= .667 and structure_alignment >= .75 and ema_alignment == 1.0
    trend = established or contextual
    prior_ctx, recent_ctx = _slope(closes, atr14, 30), _slope(closes, atr14, 8); context_flip = abs(prior_ctx)>=.45 and abs(recent_ctx)>=.65 and (prior_ctx>0)!=(recent_ctx>0)
    bos_against = st["external_bos"] == "CONFIRMED_BOS" and pressure in {"UP","DOWN"} and st["bos_direction"] != pressure
    persistent_flip = horizon_conflict and consensus >= .75 and persistence >= .75
    ema_flip = ema_conflict and context_flip and persistence >= .50
    ema_lag = ema_conflict and consensus >= .75 and persistence >= .75 and (abs(slopes[1])>=.20 or abs(slopes[2])>=.30)
    transition_evidence = [x for x, ok in (("CONTEXT_FLIP",context_flip),("STRUCTURE_BREAK",st["external_bos"]=="CONFIRMED_BOS"),("STRUCTURE_BREAK_AGAINST_PRESSURE",bos_against),("PERSISTENT_HORIZON_FLIP",persistent_flip),("EMA_CONTEXT_FLIP",ema_flip),("EMA_LAG_WITH_PERSISTENT_PRESSURE",ema_lag)) if ok]
    transition = not trend and (bos_against or ((context_flip or st["external_bos"]=="CONFIRMED_BOS") and (persistent_flip or ema_flip)) or ema_lag)
    stress = not transition and not trend and pressure in {"UP","DOWN"} and (ema_conflict or structure_conflict or horizon_conflict) and (consensus >= .50 or persistence >= .50)
    conflicts=[]
    if invalid: conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict: conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structure_conflict: conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict: conflicts.append("SHORT_VS_LONG_HORIZON")
    if pressure == "BALANCED": conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")
    if context_flip: conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")
    if bos_against: conflicts.append("STRUCTURE_BREAK_VS_PRESSURE")
    prior_pressure = "UP" if _slope(closes[:-1],atr14,5)>.20 else "DOWN" if _slope(closes[:-1],atr14,5)<-.20 else "NEUTRAL"
    last_dir = "UP" if closes[-1] > valid[-1]["open"] else "DOWN" if closes[-1] < valid[-1]["open"] else "FLAT"
    single_counter = prior_pressure in {"UP","DOWN"} and last_dir in {"UP","DOWN"} and last_dir != prior_pressure and not transition
    range_candidate = pressure == "BALANCED" and eff20 < .35 and eff40 < .40 and abs(ema_gap) < .85
    expansion_candidate = expansion and pressure in {"UP","DOWN"} and eff10 >= .25 and abs(slopes[0]) >= .25
    if transition: state, reason, maturity = "TRANSITION", "persistent repricing conflicts with established context", "TRANSITION"
    elif trend: state, reason, maturity = ("TREND_UP" if pressure=="UP" else "TREND_DOWN", "structure, pressure, persistence, EMA context and efficiency are coherent" if established else "slower-horizon structure and directional context are coherent", "ESTABLISHED" if established else "DEVELOPING")
    elif compression and (pressure=="BALANCED" or eff20<.30): state, reason, maturity = "COMPRESSION", "volatility contraction dominates directional evidence", "CONTRACTING"
    elif expansion_candidate: state, reason, maturity = "EXPANSION", "volatility is expanding with directional impulse", "EXPANDING"
    elif range_candidate: state, reason, maturity = "RANGE", "two-sided non-directional behavior dominates", "RANGE"
    elif pressure in {"UP","DOWN"} and (persistence>=.25 or consensus>=.50): state, reason, maturity = "UNCLEAR", "directional pressure exists but independent regime confirmation is insufficient", "DIRECTIONAL_DEVELOPING"
    else: state, reason, maturity = "UNCLEAR", "evidence does not establish a dominant regime", "UNRESOLVED"
    direction = "UP" if pressure=="UP" else "DOWN" if pressure=="DOWN" else "NEUTRAL"; public_pressure = "BULLISH" if direction=="UP" else "BEARISH" if direction=="DOWN" else "NEUTRAL"
    directional_state = "CONFIRMED" if state in {"TREND_UP","TREND_DOWN"} else "CONFLICTED" if transition else "DEVELOPING" if direction in {"UP","DOWN"} and (consensus>=.50 or persistence>=.25) else "NEUTRAL" if direction=="NEUTRAL" else "UNRESOLVED"
    dc = {"direction":direction,"confirmed":consensus>=.75,"score":round(consensus,3),"long_horizon_score":round(long_consensus,3),"horizons":horizons,"up_count":up,"down_count":dn,"state":directional_state}
    indep = {"data_quality":{"valid_candles":len(valid),"invalid_candles":invalid},"volatility":{"atr14":round(atr14,6),"prior_atr":round(prior_atr,6),"ratio":round(vol_ratio,3)},"structure":{**st,"quality":round(st["quality"],3),"alignment":round(structure_alignment,3)},"pressure":{"direction":direction,"score":round(pressure_score,3),"state":directional_state},"persistence":{"score":round(persistence,3),"long_horizon_score":round(long_persistence,3),"efficiency20":round(eff20,3),"efficiency40":round(eff40,3)},"ema_context":{"relation":ema,"gap_atr":round(ema_gap,3),"ema20_slope_atr":round(ema20_s,3),"ema50_slope_atr":round(ema50_s,3),"alignment":round(ema_alignment,3)},"transition":{"confirmed":transition,"evidence":transition_evidence}}
    reasons=list(dict.fromkeys(conflicts)); reasons += ["REGIME_TRANSITION_CONFIRMED"] if transition else ["REGIME_STRESS_ACTIVE"] if stress else ["DIRECTIONAL_STATE_DEVELOPING"] if directional_state=="DEVELOPING" else ["REGIME_CONFIRMATION_INSUFFICIENT"] if state=="UNCLEAR" else []
    confidence=.30+.25*st["quality"]+.20*consensus+.15*persistence+.10*max(eff20,eff40); confidence=min(confidence,.65) if state=="UNCLEAR" else confidence; confidence=min(confidence,.80) if transition or stress else confidence; confidence=min(max(confidence,.72),.84) if contextual and not established else confidence
    professional={"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":state,"market_state":state,"direction":direction,"directional_pressure":public_pressure,"directional_state":directional_state,"trend_maturity":maturity,"trend_confirmed":state in {"TREND_UP","TREND_DOWN"},"regime_stress":stress,"transition_confirmed":transition,"conflict_detected":bool(conflicts),"conflict_count":len(conflicts),"classification_reason":reason,"single_counter_candle":single_counter,"pressure_score":round(pressure_score,3),"structure_alignment":round(structure_alignment,3),"trend_score":round(trend_score,3),"directional_consensus":dc,"regime_basis":f"pressure={direction}; consensus={consensus:.2f}; long_consensus={long_consensus:.2f}; persistence={persistence:.2f}; long_persistence={long_persistence:.2f}; structure={st['state']}; ema={ema}; volatility={volatility}; trend_score={trend_score:.2f}","independent_evidence":indep,"evidence_hierarchy":EVIDENCE_HIERARCHY,"ownership_boundaries":OWNERSHIP}
    evidence=[f"valid_candles={len(valid)}",f"invalid_candles={invalid}",f"ema20_vs_ema50={ema}",f"ema_gap_atr={ema_gap:.3f}",f"ema20_slope_atr={ema20_s:.3f}",f"ema50_slope_atr={ema50_s:.3f}",*(f"price_slope_{n}_atr={s:.3f}" for n,s in zip(lbs,slopes)),f"multi_horizon={','.join(horizons)}",f"directional_consensus={consensus:.3f}",f"long_horizon_consensus={long_consensus:.3f}",f"directional_state={directional_state}",f"persistence={persistence:.3f}",f"long_horizon_persistence={long_persistence:.3f}",f"efficiency20={eff20:.3f}",f"efficiency40={eff40:.3f}",f"structure_counts={st['counts']}",f"structure_state={st['state']}",f"structure_alignment={structure_alignment:.3f}",f"external_bos={st['external_bos']}",f"pressure_score={pressure_score:.3f}",f"trend_score={trend_score:.3f}",f"volatility_ratio={vol_ratio:.3f}",f"context_flip={context_flip}",f"transition_evidence={transition_evidence}",f"established_trend={established}",f"contextual_trend={contextual}",f"trend_candidate={trend}",f"regime_stress={stress}",f"ema_lag_transition={ema_lag}",f"single_counter_candle={single_counter}"]
    return {**_base(),"market_state":state,"directional_pressure":public_pressure,"directional_state":directional_state,"trend_state":"UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE","volatility_state":volatility,"structure_state":st["state"],"structure_quality":round(st["quality"],3),"range_state":"RANGE" if range_candidate else "NOT_RANGE","compression":"PRESENT" if compression else "ABSENT","expansion":"PRESENT" if expansion else "ABSENT","transition":"PRESENT" if transition else "ABSENT","regime_stress":"PRESENT" if stress else "ABSENT","confidence":round(max(0.0,min(.99,confidence)),3),"evidence":evidence,"observations":evidence,"conflicts":conflicts,"reasons":reasons,"reasoning_trace":[f"QUESTION -> {QUESTION}",f"EVIDENCE_HIERARCHY -> {EVIDENCE_HIERARCHY}",f"STRUCTURE -> {st['state']} quality={st['quality']:.2f} alignment={structure_alignment:.2f}",f"PRESSURE -> {direction} score={pressure_score:.2f} state={directional_state}",f"VOLATILITY -> {volatility} ratio={vol_ratio:.2f}",f"PERSISTENCE -> {persistence:.2f} long={long_persistence:.2f}",f"TREND_SCORE -> {trend_score:.2f}",f"REGIME_RECONCILIATION -> established={established} contextual={contextual}",f"REGIME_CONFIRMATION -> trend_confirmed={trend} maturity={maturity}",f"REGIME_STRESS -> {'PRESENT' if stress else 'ABSENT'}",f"STATE -> {state} because={reason}",f"DIRECTIONAL_STATE -> {directional_state}",f"TRANSITION -> {'PRESENT' if transition else 'ABSENT'} evidence={transition_evidence}"],"professional_reasoning":professional,"analysis_status":"COMPLETE"}
