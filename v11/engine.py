from __future__ import annotations
import math
import pandas as pd
from .common import num, atr14, ema, structure
from .contracts import StrategyResult
from .strategies.btc import REGISTRY as BTC_REGISTRY
from .strategies.gold import REGISTRY as GOLD_REGISTRY

ENGINE_VERSION="11.0-M5-M15-STRATEGY-SPLIT"
BTC_STRATEGIES=tuple(BTC_REGISTRY)
GOLD_STRATEGIES=tuple(GOLD_REGISTRY)


def get_strategy_registry(symbol):
    return BTC_REGISTRY if str(symbol).upper().startswith("BTC") else GOLD_REGISTRY


def detect_m15_trend(m15):
    x=m15.tail(100).reset_index(drop=True)
    if len(x)<60:return {"direction":"NEUTRAL","reason":"INSUFFICIENT_M15_CONTEXT"}
    e20=ema(x,20).iloc[-1]; e50=ema(x,50).iloc[-1]; s=structure(x,80); c=num(x.close.iloc[-1])
    if c>e20>e50 and s["bias"]=="BUY": direction="BUY"
    elif c<e20<e50 and s["bias"]=="SELL": direction="SELL"
    else: direction="NEUTRAL"
    return {"direction":direction,"close":c,"ema20":num(e20),"ema50":num(e50),"structure":s}


def detect_m5_direction(m5):
    x=m5.tail(50).reset_index(drop=True); s=structure(x,50); e9=ema(x,9).iloc[-1]; e21=ema(x,21).iloc[-1]; c=num(x.close.iloc[-1])
    if s["bias"] in ("BUY","SELL"): return s["bias"]
    if c>e9>e21:return "BUY"
    if c<e9<e21:return "SELL"
    return "NEUTRAL"


def _risk_levels(m5,direction,strategy,evidence):
    x=m5.tail(30).reset_index(drop=True); entry=num(x.close.iloc[-1]); a=num(atr14(x).iloc[-1]);
    if entry<=0 or a<=0:return {"valid":False,"reason":"ATR_UNAVAILABLE"}
    s=structure(x,25); raw_sl=evidence.get("support") if direction=="BUY" else evidence.get("resistance")
    if raw_sl is None: raw_sl=s["support"] if direction=="BUY" else s["resistance"]
    if direction=="BUY": sl=min(num(raw_sl)-a*.10,entry-a*.80); risk=entry-sl; tp=entry+2*risk
    else: sl=max(num(raw_sl)+a*.10,entry+a*.80); risk=sl-entry; tp=entry-2*risk
    if risk<=0 or tp<=0:return {"valid":False,"reason":"INVALID_RISK"}
    rr=abs(tp-entry)/risk
    if rr<2.0-1e-9:return {"valid":False,"reason":"RR_BELOW_2"}
    return {"valid":True,"entry":entry,"sl":sl,"tp":tp,"risk":risk,"risk_reward":round(rr,4),"effective_rr":round(rr,4),"target_rr":2.0,"strategy":strategy}


def _candidate_directions(m5, strategy):
    d=detect_m5_direction(m5)
    if d in ("BUY","SELL"):return [d]
    x=m5.tail(21).reset_index(drop=True); c=num(x.close.iloc[-1]); hi=num(x.iloc[:-1].high.max()); lo=num(x.iloc[:-1].low.min())
    if c>hi:return ["BUY"]
    if c<lo:return ["SELL"]
    return ["BUY","SELL"] if strategy in ("LIQUIDITY_SWEEP","SR_REVERSAL") else []


def analyze(m5,m15,symbol,index=None):
    if index is not None:m5=m5.iloc[:index+1].reset_index(drop=True)
    if len(m5)<60 or len(m15)<60:
        return {"engine_version":ENGINE_VERSION,"valid":False,"signal":"NO_TRADE","strategy":"NONE","rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    registry=get_strategy_registry(symbol); m15_trend=detect_m15_trend(m15); m5_direction=detect_m5_direction(m5); candidates=[]; passes=[]
    for name,fn in registry.items():
        dirs=_candidate_directions(m5,name)
        if not dirs:
            candidates.append(StrategyResult.not_applicable(name,"NEUTRAL","M5_DIRECTION_UNCLEAR").as_dict()); continue
        best=None
        for direction in dirs:
            r=fn(m5,direction,{"m15":m15_trend})
            if best is None or r.status=="PASS":best=r
            if r.status=="PASS":break
        candidates.append(best.as_dict())
        if best.status=="PASS":passes.append(best)
    aligned=[r for r in passes if r.direction==m15_trend["direction"] and m15_trend["direction"] in ("BUY","SELL")]
    if not aligned:
        reasons=[]
        if not passes:reasons.append("NO_M5_STRATEGY_SETUP")
        if passes and m15_trend["direction"]=="NEUTRAL":reasons.append("M15_TREND_NEUTRAL")
        elif passes:reasons.append("M5_M15_DIRECTION_MISMATCH")
        return {"engine_version":ENGINE_VERSION,"symbol":symbol,"valid":False,"signal":"NO_TRADE","strategy":"NONE","m5_direction":m5_direction,"m15_trend":m15_trend,"strategy_candidates":candidates,"strategy_passes":[p.as_dict() for p in passes],"rejection_reasons":reasons,"trade_levels":{"valid":False,"reason":reasons[0]}}
    selected=aligned[0]; levels=_risk_levels(m5,selected.direction,selected.strategy,selected.evidence)
    valid=bool(levels.get("valid"))
    reasons=[] if valid else [levels.get("reason","INVALID_RISK_LEVELS")]
    return {"engine_version":ENGINE_VERSION,"symbol":symbol,"valid":valid,"signal":selected.direction if valid else "NO_TRADE","strategy":selected.strategy,"m5_direction":selected.direction,"m15_trend":m15_trend,"strategy_candidates":candidates,"strategy_passes":[p.as_dict() for p in passes],"selected_strategy":selected.as_dict(),"rejection_reasons":reasons,"trade_levels":levels,"analysis_window":{"m5_setup_bars":50,"m15_context_bars":100}}
