from __future__ import annotations
import pandas as pd
from .common import num, ema, structure
from .data_quality import validate_frame
from .risk import calculate as calculate_risk, MIN_RISK_REWARD as V11_MIN_RR
from .strategies.btc import REGISTRY as BTC_REGISTRY
from .strategies.gold import REGISTRY as GOLD_REGISTRY
from .selection import select

ENGINE_VERSION="11.1-HARDENED"
FORWARD_BARS=12
MIN_RISK_REWARD=V11_MIN_RR
RISK_REWARD=V11_MIN_RR
BTC_STRATEGIES=tuple(BTC_REGISTRY)
GOLD_STRATEGIES=tuple(GOLD_REGISTRY)

def get_strategy_registry(symbol): return BTC_REGISTRY if str(symbol).upper().startswith("BTC") else GOLD_REGISTRY

def detect_m15_trend(m15):
    x=m15.tail(100).reset_index(drop=True)
    if len(x)<60:return {"direction":"NEUTRAL","reason":"INSUFFICIENT_M15_CONTEXT"}
    e20=ema(x,20).iloc[-1]; e50=ema(x,50).iloc[-1]; s=structure(x,80); c=num(x.close.iloc[-1])
    direction="BUY" if c>e20>e50 and s["bias"]=="BUY" else "SELL" if c<e20<e50 and s["bias"]=="SELL" else "NEUTRAL"
    return {"direction":direction,"close":c,"ema20":num(e20),"ema50":num(e50),"structure":s}

def detect_m5_direction(m5):
    x=m5.tail(50).reset_index(drop=True); s=structure(x,50); e9=ema(x,9).iloc[-1]; e21=ema(x,21).iloc[-1]; c=num(x.close.iloc[-1])
    if s["bias"] in ("BUY","SELL"):return s["bias"]
    if c>e9>e21:return "BUY"
    if c<e9<e21:return "SELL"
    return "NEUTRAL"

def _freshness(m5,direction):
    x=m5.reset_index(drop=True)
    for i in range(min(5,len(x))):
        row=x.iloc[-1-i]; o,h,l,c=map(float,(row.open,row.high,row.low,row.close)); rng=max(h-l,1e-12)
        if direction=="BUY" and c>o and (c-l)/rng>=.65:return i
        if direction=="SELL" and c<o and (h-c)/rng>=.65:return i
    return 5

def _enrich(result,m5,direction):
    d=result.as_dict()
    if result.status=="PASS":
        ev=dict(result.evidence or {}); freshness=int(result.freshness_bars or ev.get("freshness_bars",_freshness(m5,direction))); quality=float(result.quality or ev.get("quality",55.0)); d.update({"freshness_bars":freshness,"quality":quality})
    return d

def analyze(m5,m15,symbol,index=None):
    if index is not None:m5=m5.iloc[:index+1].reset_index(drop=True)
    m5=m5.reset_index(drop=True); m15=m15.reset_index(drop=True); q5=validate_frame(m5,minimum=60,timeframe_minutes=5); q15=validate_frame(m15,minimum=60,timeframe_minutes=15)
    if q5 or q15:return {"engine_version":ENGINE_VERSION,"symbol":symbol,"valid":False,"signal":"NO_TRADE","strategy":"NONE","rejection_reasons":q5+q15,"trade_levels":{"valid":False},"data_quality":{"m5":q5,"m15":q15},"live_orders_allowed":False}
    registry=get_strategy_registry(symbol); m15_trend=detect_m15_trend(m15); m5_direction=detect_m5_direction(m5); candidates=[]; passes=[]; directions=[m5_direction,"SELL" if m5_direction=="BUY" else "BUY"] if m5_direction in ("BUY","SELL") else ["BUY","SELL"]
    for name,fn in registry.items():
        best=None
        for direction in directions:
            result=fn(m5,direction,{"m15":m15_trend}); best=result
            if result.status=="PASS":break
        enriched=_enrich(best,m5,best.direction); candidates.append(enriched)
        if best.status=="PASS":passes.append(enriched)
    selected=select(candidates,m15_trend["direction"])
    if not selected:
        reasons=["NO_M5_STRATEGY_SETUP"] if not passes else ["M15_TREND_NEUTRAL" if m15_trend["direction"]=="NEUTRAL" else "M5_M15_DIRECTION_MISMATCH"]
        return {"engine_version":ENGINE_VERSION,"symbol":symbol,"valid":False,"signal":"NO_TRADE","strategy":"NONE","m5_direction":m5_direction,"m15_trend":m15_trend,"strategy_candidates":candidates,"strategy_passes":passes,"rejection_reasons":reasons,"trade_levels":{"valid":False,"reason":reasons[0]},"data_quality":{"m5":[],"m15":[]},"live_orders_allowed":False}
    levels=calculate_risk(m5,selected["direction"],selected["strategy"],selected.get("evidence"),rr=MIN_RISK_REWARD); valid=bool(levels.get("valid")); reasons=[] if valid else [levels.get("reason","INVALID_RISK_LEVELS")]
    return {"engine_version":ENGINE_VERSION,"symbol":symbol,"valid":valid,"signal":selected["direction"] if valid else "NO_TRADE","strategy":selected["strategy"],"m5_direction":m5_direction,"m15_trend":m15_trend,"strategy_candidates":candidates,"strategy_passes":passes,"selected_strategy":selected,"rejection_reasons":reasons,"trade_levels":levels,"analysis_window":{"m5_setup_bars":50,"m15_context_bars":100},"data_quality":{"m5":[],"m15":[]},"live_orders_allowed":False}

analyze_structure_setup=analyze
