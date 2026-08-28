"""E1 — Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It classifies closed-candle regime/context and passes evidence downstream.
It never selects a setup or authorizes a trade action.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
DIRECTIONAL_STATES = {"CONFIRMED", "DEVELOPING", "NEUTRAL", "CONFLICTED", "UNRESOLVED"}
QUESTION = "What is the market doing right now?"
MIN_BARS = 60
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"
OWNERSHIP = {
    "owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "market_regime", "regime_transition"],
    "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution"],
}

def _num(value: Any) -> float | None:
    try: value = float(value)
    except (TypeError, ValueError): return None
    return value if isfinite(value) else None

def _ema(values: list[float], period: int) -> list[float]:
    if not values: return []
    alpha = 2.0 / (period + 1.0); current = values[0]; result = [current]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current; result.append(current)
    return result

def _atr(bars: list[dict[str, Any]], period: int, start: int | None = None, end: int | None = None) -> float:
    sample = bars[start:end] if start is not None or end is not None else bars[-period:]
    sample = sample[-period:]; trs: list[float] = []; previous_close: float | None = None
    for bar in sample:
        h, l, c = bar["high"], bar["low"], bar["close"]
        tr = h - l if previous_close is None else max(h - l, abs(h - previous_close), abs(l - previous_close))
        trs.append(max(0.0, tr)); previous_close = c
    return mean(trs) if trs else 0.0

def _slope(values: list[float], atr: float, lookback: int) -> float:
    return 0.0 if atr <= 0 or len(values) <= lookback else (values[-1] - values[-1 - lookback]) / atr

def _efficiency(values: list[float], lookback: int) -> float:
    sample = values[-lookback:]
    if len(sample) < 2: return 0.0
    path = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
    return abs(sample[-1] - sample[0]) / max(path, 1e-12)

def _pivot_structure(bars: list[dict[str, Any]], wing: int = 2) -> tuple[str, float, dict[str, int]]:
    highs: list[float] = []; lows: list[float] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i-wing:i+wing+1]
        if bars[i]["high"] >= max(x["high"] for x in window): highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in window): lows.append(bars[i]["low"])
    highs, lows = highs[-6:], lows[-6:]
    hh = sum(highs[i] > highs[i-1] for i in range(1, len(highs))); lh = sum(highs[i] < highs[i-1] for i in range(1, len(highs)))
    hl = sum(lows[i] > lows[i-1] for i in range(1, len(lows))); ll = sum(lows[i] < lows[i-1] for i in range(1, len(lows)))
    counts = {"HH": hh, "HL": hl, "LH": lh, "LL": ll}; bull, bear = min(hh, hl), min(lh, ll)
    if bull >= 2 and bull > bear: return "BULLISH", min(1.0, .62 + .09 * bull), counts
    if bear >= 2 and bear > bull: return "BEARISH", min(1.0, .62 + .09 * bear), counts
    if hh + hl >= 2 and hh + hl > lh + ll: return "BULLISH", .52, counts
    if lh + ll >= 2 and lh + ll > hh + hl: return "BEARISH", .52, counts
    return "MIXED", .30, counts

def _base() -> dict[str, Any]:
    return {"question": QUESTION, "reasoning_role": "MARKET_STATE_ANALYST", "trade_decision_authority": False, "decision_authority": "E9_ONLY", "architecture": "E1_SINGLE_PROFESSIONAL_BRAIN"}

def _incomplete(reason: str, evidence: list[str], conflicts: list[str]) -> dict[str, Any]:
    pr = {"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":"UNCLEAR","market_state":"UNCLEAR","direction":"NEUTRAL","directional_pressure":"NEUTRAL","directional_state":"UNRESOLVED","trend_maturity":"UNRESOLVED","trend_confirmed":False,"regime_stress":False,"transition_confirmed":False,"conflict_detected":bool(conflicts),"conflict_count":len(conflicts),"classification_reason":reason,"single_counter_candle":False,"pressure_score":0.0,"structure_alignment":0.0,"trend_score":0.0,"directional_consensus":{"confirmed":False,"score":0.0},"regime_basis":reason,"independent_evidence":{"data_quality":evidence},"evidence_hierarchy":EVIDENCE_HIERARCHY,"ownership_boundaries":OWNERSHIP}
    return {**_base(),"market_state":"UNCLEAR","directional_pressure":"NEUTRAL","directional_state":"UNRESOLVED","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","structure_quality":0.0,"range_state":"UNKNOWN","compression":"UNKNOWN","expansion":"UNKNOWN","transition":"UNKNOWN","regime_stress":"UNKNOWN","confidence":0.0,"evidence":evidence,"observations":evidence,"conflicts":conflicts,"reasons":[reason],"reasoning_trace":[f"QUESTION -> {QUESTION}","DATA -> insufficient reliable evidence",f"STATE -> UNCLEAR because={reason}","DIRECTIONAL_STATE -> UNRESOLVED"],"professional_reasoning":pr,"analysis_status":"INCOMPLETE"}

def analyze_e1(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []; invalid_count = 0
    for raw in bars or []:
        if not isinstance(raw, dict): invalid_count += 1; continue
        vals = {k:_num(raw.get(k)) for k in ("open","high","low","close")}
        if any(v is None for v in vals.values()): invalid_count += 1; continue
        o,h,l,c = vals["open"],vals["high"],vals["low"],vals["close"]
        if h < l or h < max(o,c) or l > min(o,c): invalid_count += 1; continue
        valid.append({**raw,"open":o,"high":h,"low":l,"close":c})
    if len(valid) < MIN_BARS:
        return _incomplete("insufficient reliable closed candles; classification withheld",[f"valid_candles={len(valid)}",f"minimum_required={MIN_BARS}"],["DATA_QUALITY_ANOMALIES"] if invalid_count else [])
    closes=[b["close"] for b in valid]; atr14=_atr(valid,14); atr50=_atr(valid,50)
    if atr14 <= 0 or atr50 <= 0: return _incomplete("ATR invalid; classification withheld",["ATR_INVALID"],["ATR_INVALID"])
    e20s,e50s=_ema(closes,20),_ema(closes,50); e20,e50=e20s[-1],e50s[-1]
    ema_relation="UP" if e20>e50 else "DOWN" if e20<e50 else "FLAT"; ema_gap=(e20-e50)/atr14
    ema20_slope,ema50_slope=_slope(e20s,atr14,5),_slope(e50s,atr14,5)
    lookbacks=(5,10,20,40); slopes=[_slope(closes,atr14,n) for n in lookbacks]; thresholds=(.15,.20,.30,.40)
    horizons=["UP" if s>=t else "DOWN" if s<=-t else "FLAT" for s,t in zip(slopes,thresholds)]; up,down=horizons.count("UP"),horizons.count("DOWN")
    long_horizons=horizons[1:]; long_up,long_down=long_horizons.count("UP"),long_horizons.count("DOWN")
    longer_up,longer_down=long_up,long_down
    if up==4: pressure="UP"
    elif down==4: pressure="DOWN"
    elif longer_up>longer_down: pressure="UP"
    elif longer_down>longer_up: pressure="DOWN"
    else: pressure="BALANCED"
    consensus=max(up,down)/4
    long_consensus=max(long_up,long_down)/3
    if pressure=="UP":
        persistence=sum((slopes[0]>=.20,slopes[1]>=.25,slopes[2]>=.35,slopes[3]>=.45))/4
        long_persistence=sum((slopes[1]>=.25,slopes[2]>=.35,slopes[3]>=.45))/3
    elif pressure=="DOWN":
        persistence=sum((slopes[0]<=-.20,slopes[1]<=-.25,slopes[2]<=-.35,slopes[3]<=-.45))/4
        long_persistence=sum((slopes[1]<=-.25,slopes[2]<=-.35,slopes[3]<=-.45))/3
    else:
        persistence=0.0; long_persistence=0.0
    eff10,eff20,eff40=(_efficiency(closes,n) for n in (10,20,40))
    structure,structure_quality,pivot_counts=_pivot_structure(valid); structure_direction="UP" if structure=="BULLISH" else "DOWN" if structure=="BEARISH" else "NEUTRAL"
    structure_conflict=pressure in {"UP","DOWN"} and structure_direction in {"UP","DOWN"} and structure_direction!=pressure
    structural_proxy=structure=="MIXED" and structure_quality<=.30 and long_persistence>=.667 and max(eff20,eff40)>=.22
    structure_alignment=1.0 if structure_direction==pressure and pressure!="BALANCED" else .75 if structural_proxy else .5 if pressure=="BALANCED" and structure=="MIXED" else 0.0
    ema_alignment=1.0 if pressure in {"UP","DOWN"} and ema_relation==pressure else 0.0
    ema_conflict=pressure in {"UP","DOWN"} and ema_relation in {"UP","DOWN"} and ema_relation!=pressure; horizon_conflict=up>0 and down>0
    conflicts=[]
    if invalid_count: conflicts.append("DATA_QUALITY_ANOMALIES")
    if ema_conflict: conflicts.append("EMA_VS_PRICE_PRESSURE")
    if structure_conflict: conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if horizon_conflict: conflicts.append("SHORT_VS_LONG_HORIZON")
    if pressure=="BALANCED": conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")
    prior_atr=_atr(valid,50,-64,-14) if len(valid)>=64 else atr50; volatility_ratio=atr14/max(prior_atr,1e-12)
    compression=volatility_ratio<.78; expansion=volatility_ratio>1.10
    volatility="EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"
    pressure_score=consensus*(.65+.35*persistence)
    trend_score=.25*consensus+.25*persistence+.20*structure_alignment+.15*ema_alignment+.10*long_consensus+.05*max(eff20,eff40)
    # Professional reconciliation: a short M5 counter-move must not erase a coherent
    # slower trend. Efficiency remains a strength measure, not a hard veto, when
    # EMA context + structure + 10/20/40-bar direction agree.
    established_trend=(pressure in {"UP","DOWN"} and consensus>=.75 and persistence>=.50 and structure_alignment>=.75 and ema_alignment==1.0 and max(eff20,eff40)>=.22)
    contextual_trend=(pressure in {"UP","DOWN"} and long_consensus>=.667 and long_persistence>=.667 and structure_alignment>=.75 and ema_alignment==1.0)
    trend_candidate=established_trend or contextual_trend
    prior_context=_slope(closes,atr14,30); recent_context=_slope(closes,atr14,8)
    context_flip=abs(prior_context)>=.45 and abs(recent_context)>=.65 and (prior_context>0)!=(recent_context>0)
    structure_break_proxy=structure_conflict and long_persistence>=.667 and structure_quality>=.52
    persistent_horizon_flip=horizon_conflict and consensus>=.75 and persistence>=.75
    ema_context_flip=ema_conflict and context_flip and persistence>=.50
    ema_lag_transition=ema_conflict and consensus>=.75 and persistence>=.75 and (abs(slopes[1])>=.20 or abs(slopes[2])>=.30)
    transition_evidence=[label for label,ok in (("CONTEXT_FLIP",context_flip),("STRUCTURE_BREAK_PROXY",structure_break_proxy),("PERSISTENT_HORIZON_FLIP",persistent_horizon_flip),("EMA_CONTEXT_FLIP",ema_context_flip),("EMA_LAG_WITH_PERSISTENT_PRESSURE",ema_lag_transition)) if ok]
    transition=not trend_candidate and ((context_flip or structure_break_proxy) and (persistent_horizon_flip or ema_context_flip or structure_break_proxy) or ema_lag_transition)
    regime_stress=not transition and not trend_candidate and pressure in {"UP","DOWN"} and (ema_conflict or structure_conflict or horizon_conflict) and (consensus>=.50 or persistence>=.50)
    if context_flip: conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")
    prior_pressure="UP" if _slope(closes[:-1],atr14,5)>.20 else "DOWN" if _slope(closes[:-1],atr14,5)<-.20 else "NEUTRAL"
    last_direction="UP" if closes[-1]>valid[-1]["open"] else "DOWN" if closes[-1]<valid[-1]["open"] else "FLAT"
    single_counter_candle=prior_pressure in {"UP","DOWN"} and last_direction in {"UP","DOWN"} and last_direction!=prior_pressure and not transition
    range_candidate=pressure=="BALANCED" and eff20<.35 and eff40<.40 and abs(ema_gap)<.85
    expansion_candidate=expansion and pressure in {"UP","DOWN"} and eff10>=.25 and abs(slopes[0])>=.25
    if transition: state,reason,maturity="TRANSITION","persistent repricing conflicts with slower market context","TRANSITION"
    elif trend_candidate:
        state="TREND_UP" if pressure=="UP" else "TREND_DOWN"
        if established_trend: reason="direction, persistence, structure, EMA context and efficiency are coherent"; maturity="ESTABLISHED"
        else: reason="slower-horizon direction, structure and EMA context remain coherent despite short-term pullback"; maturity="DEVELOPING"
    elif compression and (pressure=="BALANCED" or eff20<.30): state,reason,maturity="COMPRESSION","volatility contraction dominates directional evidence","CONTRACTING"
    elif expansion_candidate: state,reason,maturity="EXPANSION","volatility is expanding with directional impulse","EXPANDING"
    elif range_candidate: state,reason,maturity="RANGE","two-sided non-directional behavior dominates","RANGE"
    elif pressure in {"UP","DOWN"} and (persistence>=.25 or consensus>=.50): state,reason,maturity="UNCLEAR","directional pressure exists but regime confirmation is insufficient","DIRECTIONAL_DEVELOPING"
    else: state,reason,maturity="UNCLEAR","evidence does not establish a dominant regime","UNRESOLVED"
    direction="UP" if pressure=="UP" else "DOWN" if pressure=="DOWN" else "NEUTRAL"; public_pressure="BULLISH" if direction=="UP" else "BEARISH" if direction=="DOWN" else "NEUTRAL"
    if state in {"TREND_UP","TREND_DOWN"}: directional_state="CONFIRMED"
    elif transition: directional_state="CONFLICTED"
    elif direction in {"UP","DOWN"} and (consensus>=.50 or persistence>=.25): directional_state="DEVELOPING"
    elif direction=="NEUTRAL": directional_state="NEUTRAL"
    else: directional_state="UNRESOLVED"
    directional_consensus={"direction":direction,"confirmed":consensus>=.75,"score":round(consensus,3),"long_horizon_score":round(long_consensus,3),"horizons":horizons,"up_count":up,"down_count":down,"state":directional_state}
    independent_evidence={"data_quality":{"valid_candles":len(valid),"invalid_candles":invalid_count},"volatility":{"atr14":round(atr14,6),"prior_atr":round(prior_atr,6),"ratio":round(volatility_ratio,3)},"structure":{"state":structure,"quality":round(structure_quality,3),"alignment":round(structure_alignment,3),"counts":pivot_counts},"pressure":{"direction":direction,"score":round(pressure_score,3),"state":directional_state},"persistence":{"score":round(persistence,3),"long_horizon_score":round(long_persistence,3),"efficiency20":round(eff20,3),"efficiency40":round(eff40,3)},"ema_context":{"relation":ema_relation,"gap_atr":round(ema_gap,3),"alignment":round(ema_alignment,3)},"transition":{"confirmed":transition,"evidence":transition_evidence}}
    regime_basis=f"pressure={direction}; consensus={consensus:.2f}; long_consensus={long_consensus:.2f}; persistence={persistence:.2f}; long_persistence={long_persistence:.2f}; structure={structure}; ema={ema_relation}; volatility={volatility}; trend_score={trend_score:.2f}"
    evidence=[f"valid_candles={len(valid)}",f"invalid_candles={invalid_count}",f"ema20_vs_ema50={ema_relation}",f"ema_gap_atr={ema_gap:.3f}",f"ema20_slope_atr={ema20_slope:.3f}",f"ema50_slope_atr={ema50_slope:.3f}",*(f"price_slope_{n}_atr={s:.3f}" for n,s in zip(lookbacks,slopes)),f"multi_horizon={','.join(horizons)}",f"directional_consensus={consensus:.3f}",f"long_horizon_consensus={long_consensus:.3f}",f"directional_state={directional_state}",f"persistence={persistence:.3f}",f"long_horizon_persistence={long_persistence:.3f}",f"efficiency20={eff20:.3f}",f"efficiency40={eff40:.3f}",f"structure_counts={pivot_counts}",f"structure_alignment={structure_alignment:.3f}",f"pressure_score={pressure_score:.3f}",f"trend_score={trend_score:.3f}",f"volatility_ratio={volatility_ratio:.3f}",f"context_flip={context_flip}",f"transition_evidence={transition_evidence}",f"established_trend={established_trend}",f"contextual_trend={contextual_trend}",f"trend_candidate={trend_candidate}",f"regime_stress={regime_stress}",f"ema_lag_transition={ema_lag_transition}",f"single_counter_candle={single_counter_candle}"]
    confidence=.30+.25*structure_quality+.20*consensus+.15*persistence+.10*max(eff20,eff40)
    if state=="UNCLEAR": confidence=min(confidence,.65)
    if transition or regime_stress: confidence=min(confidence,.80)
    if contextual_trend and not established_trend: confidence=min(max(confidence,.72),.84)
    reasons=list(conflicts)
    if transition: reasons.append("REGIME_TRANSITION_CONFIRMED")
    elif regime_stress: reasons.append("REGIME_STRESS_ACTIVE")
    elif directional_state=="DEVELOPING": reasons.append("DIRECTIONAL_STATE_DEVELOPING")
    elif state=="UNCLEAR": reasons.append("REGIME_CONFIRMATION_INSUFFICIENT")
    pr={"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":state,"market_state":state,"direction":direction,"directional_pressure":public_pressure,"directional_state":directional_state,"trend_maturity":maturity,"trend_confirmed":state in {"TREND_UP","TREND_DOWN"},"regime_stress":regime_stress,"transition_confirmed":transition,"conflict_detected":bool(conflicts),"conflict_count":len(conflicts),"classification_reason":reason,"single_counter_candle":single_counter_candle,"pressure_score":round(pressure_score,3),"structure_alignment":round(structure_alignment,3),"trend_score":round(trend_score,3),"directional_consensus":directional_consensus,"regime_basis":regime_basis,"independent_evidence":independent_evidence,"evidence_hierarchy":EVIDENCE_HIERARCHY,"ownership_boundaries":OWNERSHIP}
    return {**_base(),"market_state":state,"directional_pressure":public_pressure,"directional_state":directional_state,"trend_state":"UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE","volatility_state":volatility,"structure_state":structure,"structure_quality":round(structure_quality,3),"range_state":"RANGE" if range_candidate else "NOT_RANGE","compression":"PRESENT" if compression else "ABSENT","expansion":"PRESENT" if expansion else "ABSENT","transition":"PRESENT" if transition else "ABSENT","regime_stress":"PRESENT" if regime_stress else "ABSENT","confidence":round(max(0.0,min(.99,confidence)),3),"evidence":evidence,"observations":evidence,"conflicts":conflicts,"reasons":reasons,"reasoning_trace":[f"QUESTION -> {QUESTION}",f"EVIDENCE_HIERARCHY -> {EVIDENCE_HIERARCHY}",f"STRUCTURE -> {structure} quality={structure_quality:.2f} alignment={structure_alignment:.2f}",f"PRESSURE -> {direction} score={pressure_score:.2f} state={directional_state}",f"VOLATILITY -> {volatility} ratio={volatility_ratio:.2f}",f"PERSISTENCE -> {persistence:.2f} long={long_persistence:.2f}",f"TREND_SCORE -> {trend_score:.2f}",f"REGIME_RECONCILIATION -> established={established_trend} contextual={contextual_trend}",f"REGIME_CONFIRMATION -> trend_confirmed={trend_candidate} maturity={maturity}",f"REGIME_STRESS -> {'PRESENT' if regime_stress else 'ABSENT'}",f"STATE -> {state} because={reason}",f"DIRECTIONAL_STATE -> {directional_state}",f"TRANSITION -> {'PRESENT' if transition else 'ABSENT'} evidence={transition_evidence}"],"professional_reasoning":pr,"analysis_status":"COMPLETE"}
