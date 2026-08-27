"""E4 Professional Liquidity & Auction Brain V9.

Standalone analysis-only peer brain. It does not gate or authorize trades,
and it does not consume upstream scores, gates, or decisions. Legacy E4
sub-engines 4A-4F remain paused outside this entrypoint.
"""
from __future__ import annotations
from typing import Any
from math import isfinite

QUESTION = "What is liquidity doing around current price?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V9"
_FORBIDDEN = {"decision", "trade_decision", "decision_score", "score", "gate", "gate_passed", "specialist_gate"}

def _f(x: Any):
    try:
        y=float(x); return y if isfinite(y) else None
    except (TypeError,ValueError): return None

def _bars(snapshot):
    out=[]
    for b in (snapshot or {}).get("bars") or []:
        if not isinstance(b,dict): continue
        vals={k:_f(b.get(k)) for k in ("open","high","low","close")}
        if all(v is not None for v in vals.values()) and vals["high"]>=vals["low"]:
            out.append(vals)
    return out

def _atr(bars, period=14):
    if len(bars)<2:return 0.0
    trs=[]
    for i in range(1,len(bars)):
        b,p=bars[i],bars[i-1]
        trs.append(max(b["high"]-b["low"],abs(b["high"]-p["close"]),abs(b["low"]-p["close"])))
    return sum(trs[-period:])/min(len(trs),period)

def _pivots(bars, wing=2):
    hi=[];lo=[]
    for i in range(wing,len(bars)-wing):
        w=bars[i-wing:i+wing+1]; h=bars[i]["high"]; l=bars[i]["low"]
        if h>=max(x["high"] for x in w): hi.append(h)
        if l<=min(x["low"] for x in w): lo.append(l)
    return hi,lo

def _clusters(levels,tol):
    groups=[]
    for x in sorted(levels):
        if not groups or abs(x-sum(groups[-1])/len(groups[-1]))>tol: groups.append([x])
        else: groups[-1].append(x)
    return [{"price":sum(g)/len(g),"lower":min(g),"upper":max(g),"touches":len(g),"type":"CLUSTERED" if len(g)>1 else "SWING"} for g in groups]

def _directional_context(bus):
    ctx={}
    for eid in ("E1","E2","E3"):
        p=(bus or {}).get(eid,{})
        if isinstance(p,dict):
            e=p.get("evidence") if isinstance(p.get("evidence"),dict) else p
            if isinstance(e,dict): ctx[eid]={k:v for k,v in e.items() if str(k).lower() not in _FORBIDDEN}
    return ctx

def analyze_e4(snapshot:dict[str,Any]|None=None, evidence_bus:dict[str,Any]|None=None)->dict[str,Any]:
    snapshot=snapshot or {}; bars=_bars(snapshot); atr=_atr(bars); ctx=_directional_context(evidence_bus)
    if len(bars)<20 or atr<=0:
        return {"state":"UNAVAILABLE","architecture":ARCHITECTURE,"question":QUESTION,"finding":"LIQUIDITY_DATA_INSUFFICIENT","direction":"NEUTRAL","confidence":0.0,"observations":[],"evidence":[],"liquidity_map":{},"event":{},"interaction":{},"reasons":["INSUFFICIENT_CLOSED_CANDLE_DATA"]}
    hi,lo=_pivots(bars); price=bars[-1]["close"]; tol=max(atr*0.15,1e-9)
    highz=_clusters(hi[-30:],tol); lowz=_clusters(lo[-30:],tol)
    recent=bars[-3:]; last=bars[-1]
    swept_high=any(last["high"]>z["upper"] and last["close"]<=z["upper"] for z in highz)
    swept_low=any(last["low"]<z["lower"] and last["close"]>=z["lower"] for z in lowz)
    rng=max(last["high"]-last["low"],1e-9); upper_wick=last["high"]-max(last["open"],last["close"]); lower_wick=min(last["open"],last["close"])-last["low"]
    rejection_high=swept_high and upper_wick/rng>=0.35
    rejection_low=swept_low and lower_wick/rng>=0.35
    acceptance_high=last["close"]>max((z["upper"] for z in highz),default=float("inf"))
    acceptance_low=last["close"]<min((z["lower"] for z in lowz),default=-float("inf"))
    if rejection_high and not acceptance_high: event="HIGH_SWEEP_REJECTION"; direction="DOWN"
    elif rejection_low and not acceptance_low: event="LOW_SWEEP_REJECTION"; direction="UP"
    elif swept_high: event="HIGH_LIQUIDITY_INTERACTION"; direction="NEUTRAL"
    elif swept_low: event="LOW_LIQUIDITY_INTERACTION"; direction="NEUTRAL"
    elif acceptance_high: event="HIGH_LIQUIDITY_ACCEPTANCE"; direction="UP"
    elif acceptance_low: event="LOW_LIQUIDITY_ACCEPTANCE"; direction="DOWN"
    else: event="NO_CONFIRMED_LIQUIDITY_EVENT"; direction="NEUTRAL"
    nearest_high=min((z["price"] for z in highz if z["price"]>=price),default=None,key=lambda x:x-price)
    nearest_low=max((z["price"] for z in lowz if z["price"]<=price),default=None,key=lambda x:price-x)
    strength=min(1.0,0.35 + 0.15*bool(swept_high or swept_low)+0.2*bool(rejection_high or rejection_low)+0.2*bool(acceptance_high or acceptance_low))
    obs=[f"closed_candles={len(bars)}",f"atr14={atr:.6f}",f"price={price:.6f}",f"high_liquidity_zones={len(highz)}",f"low_liquidity_zones={len(lowz)}",f"swept_high={swept_high}",f"swept_low={swept_low}",f"rejection_high={rejection_high}",f"rejection_low={rejection_low}",f"acceptance_high={acceptance_high}",f"acceptance_low={acceptance_low}",f"nearest_high={nearest_high}",f"nearest_low={nearest_low}",f"upstream_context_available={bool(ctx)}"]
    reasons=[]
    if event.startswith("HIGH_SWEEP"): reasons += ["HIGH_LIQUIDITY_TAKEN","REJECTION_AFTER_SWEEP"]
    elif event.startswith("LOW_SWEEP"): reasons += ["LOW_LIQUIDITY_TAKEN","REJECTION_AFTER_SWEEP"]
    elif event.startswith("HIGH_LIQUIDITY_INTERACTION") or event.startswith("LOW_LIQUIDITY_INTERACTION"): reasons += ["SWEEP_WITHOUT_CONFIRMED_REACTION"]
    elif event.startswith("NO_CONFIRMED"): reasons += ["NO_CONFIRMED_EVENT"]
    return {"state":"ANALYSIS_COMPLETE","architecture":ARCHITECTURE,"question":QUESTION,"finding":event,"direction":direction,"directional_implication":direction,"confidence":round(strength,3),"evidence_strength":round(strength,3),"observations":obs,"evidence":obs,"liquidity_map":{"high_zones":highz,"low_zones":lowz,"nearest_high":nearest_high,"nearest_low":nearest_low},"event":{"type":event,"sweep_high":swept_high,"sweep_low":swept_low},"interaction":{"rejection_high":rejection_high,"rejection_low":rejection_low,"acceptance_high":acceptance_high,"acceptance_low":acceptance_low},"auction_state":"REJECTION" if rejection_high or rejection_low else ("ACCEPTANCE" if acceptance_high or acceptance_low else "UNRESOLVED"),"context_used":{"E1":bool(ctx.get("E1")),"E2":bool(ctx.get("E2")),"E3":bool(ctx.get("E3"))},"reasons":reasons,"conflicts":[],"missing_evidence":[]}
