"""Production-V2 E4 — Professional Liquidity Brain.

E4 is a standalone, analysis-only brain. Legacy 4A-4F specialists remain
present but are PAUSED and are not executed by this entrypoint.
"""
from __future__ import annotations
from math import isfinite
from typing import Any, Iterable

_EPS = 1e-9
_FORBIDDEN = {"decision", "trade_decision", "decision_score", "score", "gate", "gate_passed", "specialist_gate"}

def _num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None

def _get(bar: Any, *names: str) -> float | None:
    if isinstance(bar, dict):
        for name in names:
            if name in bar:
                value = _num(bar[name])
                if value is not None: return value
            lower = name.lower()
            for key, raw in bar.items():
                if str(key).lower() == lower:
                    value = _num(raw)
                    if value is not None: return value
    else:
        for name in names:
            value = _num(getattr(bar, name, None))
            if value is not None: return value
    return None

def _clean_bars(bars: Iterable[Any]) -> list[dict[str, float]]:
    result = []
    for bar in bars:
        o, h, l, c = (_get(bar, n) for n in ("open", "high", "low", "close"))
        if None not in (o, h, l, c) and h >= l:
            result.append({"open": o, "high": h, "low": l, "close": c})
    return result

def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    trs = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        trs.append(max(b["high"]-b["low"], abs(b["high"]-p["close"]), abs(b["low"]-p["close"])))
    sample = trs[-period:]
    return sum(sample)/len(sample) if sample else 0.0

def _pivot_levels(bars: list[dict[str, float]], lookback: int = 2):
    highs, lows = [], []
    if len(bars) < lookback*2+1: return highs, lows
    for i in range(lookback, len(bars)-lookback):
        w = bars[i-lookback:i+lookback+1]
        if bars[i]["high"] >= max(x["high"] for x in w): highs.append(bars[i]["high"])
        if bars[i]["low"] <= min(x["low"] for x in w): lows.append(bars[i]["low"])
    return highs, lows

def _cluster(levels, tolerance):
    groups = []
    for level in sorted(levels):
        if not groups or abs(level-sum(groups[-1])/len(groups[-1])) > max(tolerance,_EPS): groups.append([level])
        else: groups[-1].append(level)
    return [{"zone_id":f"L{i}","price":sum(g)/len(g),"lower":min(g),"upper":max(g),"touches":len(g),"type":"CLUSTERED_LIQUIDITY" if len(g)>1 else "SWING_LIQUIDITY"} for i,g in enumerate(groups,1)]

def _evidence_values(evidence_bus):
    result = {}
    for engine_id in ("E1","E2","E3"):
        package = (evidence_bus or {}).get(engine_id)
        if not isinstance(package,dict): continue
        evidence = package.get("evidence") or package.get("output") or {}
        if not isinstance(evidence,dict): continue
        output = evidence.get("output") if isinstance(evidence.get("output"),dict) else evidence
        result[engine_id] = {k:v for k,v in output.items() if str(k).lower() not in _FORBIDDEN}
    return result

def _iter_values(value):
    if isinstance(value,dict):
        for item in value.values(): yield from _iter_values(item)
    elif isinstance(value,(list,tuple,set)):
        for item in value: yield from _iter_values(item)
    elif isinstance(value,str): yield value.upper().strip()

def _direction_hint(values):
    found={v for v in _iter_values(values) if v in {"BULLISH","BEARISH","UP","DOWN","BUY","SELL","LONG","SHORT"}}
    down,up=found&{"BEARISH","DOWN","SELL","SHORT"},found&{"BULLISH","UP","BUY","LONG"}
    if down and up: return "CONFLICTING"
    if down: return "DOWN"
    if up: return "UP"
    return "UNRESOLVED"

def _base(status="COMPLETE"):
    return {"architecture":"E4_PROFESSIONAL_LIQUIDITY_BRAIN_V1","analysis_status":status,"sub_engines_active":False,"sub_engines_status":"PAUSED","specialists":{},"decision_authority":"E9_ONLY","trade_decision_authority":False,"decision":None,"gate":None,"score":None,"reasoning_role":"LIQUIDITY_ANALYST","question":"Where is liquidity and what did price do with it?"}

def analyze_e4(bars: Iterable[Any], evidence_bus=None):
    data=_clean_bars(bars)
    if not data:
        out=_base("INSUFFICIENT_DATA")
        out.update({"finding":"NO_VALID_MARKET_DATA","liquidity_state":"UNRESOLVED","event":"NONE","observations":[],"reasons":["E4_NO_VALID_BARS"],"reason_codes":("E4_NO_VALID_BARS",),"confidence":0.0})
        return out
    atr=_atr(data); last=data[-1]; tol=max(atr*0.12,(last["high"]-last["low"])*0.15,_EPS)
    ph,pl=_pivot_levels(data[-250:]); ext_h=max(b["high"] for b in data[:-1]) if len(data)>1 else last["high"]; ext_l=min(b["low"] for b in data[:-1]) if len(data)>1 else last["low"]
    high_zones=_cluster(ph+[ext_h],tol); low_zones=_cluster(pl+[ext_l],tol)
    lookback=min(20,len(data)-1); prior=data[-lookback-1:-1] if lookback else data[:-1]
    prior_h=max(b["high"] for b in prior) if prior else last["high"]; prior_l=min(b["low"] for b in prior) if prior else last["low"]
    swept_h=last["high"]>prior_h+_EPS; swept_l=last["low"]<prior_l-_EPS
    body=abs(last["close"]-last["open"]); upper=last["high"]-max(last["open"],last["close"]); lower=min(last["open"],last["close"])-last["low"]
    reject_h=swept_h and last["close"]<prior_h and upper>=max(body*0.8,tol*0.25); reject_l=swept_l and last["close"]>prior_l and lower>=max(body*0.8,tol*0.25)
    accept_h=swept_h and last["close"]>prior_h; accept_l=swept_l and last["close"]<prior_l
    if reject_h and reject_l: event,imp="CONFLICTING_SWEEP","UNRESOLVED"
    elif reject_h: event,imp="HIGH_SWEEP_REJECTION","DOWN"
    elif reject_l: event,imp="LOW_SWEEP_REJECTION","UP"
    elif accept_h: event,imp="HIGH_ACCEPTANCE","UP"
    elif accept_l: event,imp="LOW_ACCEPTANCE","DOWN"
    elif swept_h: event,imp="HIGH_LIQUIDITY_PENETRATION","UNRESOLVED"
    elif swept_l: event,imp="LOW_LIQUIDITY_PENETRATION","UNRESOLVED"
    else: event,imp="NO_CONFIRMED_LIQUIDITY_EVENT","UNRESOLVED"
    evidence=_evidence_values(evidence_bus); hint=_direction_hint(evidence); conflicts=[]
    if hint not in {"UNRESOLVED","CONFLICTING",imp} and imp!="UNRESOLVED": conflicts.append("UPSTREAM_CONTEXT_DISAGREES_WITH_LIQUIDITY_EVENT")
    strength=1.0 if event in {"HIGH_SWEEP_REJECTION","LOW_SWEEP_REJECTION","HIGH_ACCEPTANCE","LOW_ACCEPTANCE"} else 0.55 if "PENETRATION" in event else 0.25
    confidence=round(100*(0.50*strength+0.30*min(1,(len(high_zones)+len(low_zones))/8)+0.20*(1 if atr>0 else 0)),2)
    observations=[f"liquidity_high_zones={len(high_zones)}",f"liquidity_low_zones={len(low_zones)}",f"swept_high={swept_h}",f"swept_low={swept_l}",f"rejection_high={reject_h}",f"rejection_low={reject_l}",f"acceptance_high={accept_h}",f"acceptance_low={accept_l}",f"event={event}",f"directional_implication={imp}",f"atr14={round(atr,8)}"]
    reasons=["E4_LIQUIDITY_ANALYSIS_COMPLETE"]+conflicts
    out=_base(); out.update({"finding":event,"liquidity_state":"EVENT_DETECTED" if event!="NO_CONFIRMED_LIQUIDITY_EVENT" else "LIQUIDITY_MAPPED","event":event,"directional_implication":imp,"contextual_direction_hint":hint,"liquidity_map":{"high_zones":high_zones,"low_zones":low_zones,"external_high":ext_h,"external_low":ext_l,"atr":atr,"tolerance":tol},"interaction":{"swept_high":swept_h,"swept_low":swept_l,"rejection_high":reject_h,"rejection_low":reject_l,"acceptance_high":accept_h,"acceptance_low":accept_l},"liquidity_strength":confidence,"confidence":round(confidence/100,4),"observations":observations,"reasons":reasons,"reason_codes":tuple(reasons),"evidence":{"source_engines":sorted(evidence),"decisions_used":False,"gates_used":False,"scores_used":False,"raw_market_data_used":True},"conflicts":conflicts})
    return out

__all__=["analyze_e4"]
