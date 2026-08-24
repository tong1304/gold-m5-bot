from __future__ import annotations
import math
import pandas as pd
from .common import num, atr14

MIN_RISK_REWARD=2.0
STRUCTURE_LOOKBACK=25
PIVOT_LEFT=2
PIVOT_RIGHT=2
SL_BUFFER_ATR=0.10
MIN_STRUCTURE_RISK_ATR=0.50
SAFE_ZONE_ATR=0.20
MAX_TP_LEVELS=3


def _pivot_levels(df):
    x=df.tail(STRUCTURE_LOOKBACK).reset_index(drop=True)
    supports=[]; resistances=[]
    for i in range(PIVOT_LEFT, max(PIVOT_LEFT, len(x)-PIVOT_RIGHT)):
        high=num(x.high.iloc[i]); low=num(x.low.iloc[i])
        if high >= max(num(v) for v in x.high.iloc[i-PIVOT_LEFT:i+PIVOT_RIGHT+1]):
            resistances.append((i,high))
        if low <= min(num(v) for v in x.low.iloc[i-PIVOT_LEFT:i+PIVOT_RIGHT+1]):
            supports.append((i,low))
    return supports,resistances


def _structure_levels(df,direction,entry,atr):
    supports,resistances=_pivot_levels(df)
    min_gap=max(atr*MIN_STRUCTURE_RISK_ATR,1e-12)
    if direction=="BUY":
        below=sorted((v for _,v in supports if v<entry),reverse=True)
        above=sorted(set(v for _,v in resistances if v>entry))
        eligible=[v for v in below if entry-v>=min_gap]
        return "support", (eligible[0] if eligible else None), above
    above=sorted((v for _,v in resistances if v>entry))
    below=sorted(set(v for _,v in supports if v<entry),reverse=True)
    eligible=[v for v in above if v-entry>=min_gap]
    return "resistance", (eligible[0] if eligible else None), below


def calculate(m5,direction: str,strategy: str,evidence: dict|None=None,*,rr: float=MIN_RISK_REWARD):
    evidence=evidence or {}
    if direction not in ("BUY","SELL"): return {"valid":False,"reason":"INVALID_DIRECTION"}
    x=m5.tail(STRUCTURE_LOOKBACK).reset_index(drop=True)
    if len(x)<14: return {"valid":False,"reason":"INSUFFICIENT_RISK_CONTEXT"}
    entry=num(x.close.iloc[-1]); a=num(atr14(x).iloc[-1])
    if not math.isfinite(entry) or entry<=0 or not math.isfinite(a) or a<=0: return {"valid":False,"reason":"ATR_UNAVAILABLE"}
    level_name,sl_level,tp_levels=_structure_levels(x,direction,entry,a)
    if sl_level is None:
        return {"valid":False,"reason":"NO_STRUCTURE_WITH_SUFFICIENT_RISK_DISTANCE","entry":entry,"atr":a,"min_structure_risk":a*MIN_STRUCTURE_RISK_ATR,"structure_type":level_name,"strategy":strategy}
    buffer=a*SL_BUFFER_ATR
    if direction=="BUY":
        if sl_level>=entry: return {"valid":False,"reason":"NO_SUPPORT_BELOW_ENTRY"}
        sl=sl_level-buffer; risk=entry-sl
    else:
        if sl_level<=entry: return {"valid":False,"reason":"NO_RESISTANCE_ABOVE_ENTRY"}
        sl=sl_level+buffer; risk=sl-entry
    if not math.isfinite(risk) or risk<=0: return {"valid":False,"reason":"INVALID_RISK"}

    candidates=[]
    for level in tp_levels:
        level=num(level)
        if direction=="BUY" and level>entry: reward=level-entry
        elif direction=="SELL" and level<entry: reward=entry-level
        else: continue
        candidates.append((level,reward/risk))
    if not candidates:
        return {"valid":False,"reason":"NO_TP_STRUCTURE_LEVEL","entry":entry,"sl":sl,"risk":risk,"structure_level":sl_level,"structure_type":level_name,"strategy":strategy}

    # The nearest opposing structure is the first decision point. Never skip it
    # to manufacture a 2R target from a farther level.
    first_level,first_rr=candidates[0]
    if first_rr<MIN_RISK_REWARD:
        return {"valid":False,"reason":"NEAREST_STRUCTURE_RR_BELOW_2","entry":entry,"sl":sl,"risk":risk,"first_tp":first_level,"first_tp_rr":round(first_rr,4),"target_rr":MIN_RISK_REWARD,"structure_level":sl_level,"structure_type":level_name,"strategy":strategy}

    tp_levels_out=[{"price":first_level,"risk_reward":round(first_rr,4),"type":"PRIMARY"}]
    safe_limit=a*SAFE_ZONE_ATR
    previous=first_level
    for level,level_rr in candidates[1:]:
        if abs(level-previous)>=safe_limit:
            tp_levels_out.append({"price":level,"risk_reward":round(level_rr,4),"type":"EXTENSION"})
            previous=level
        if len(tp_levels_out)>=MAX_TP_LEVELS: break

    tp=first_level
    effective_rr=abs(tp-entry)/risk
    levels={"valid":True,"entry":entry,"sl":sl,"tp":tp,"risk":risk,"risk_reward":round(effective_rr,4),"effective_rr":round(effective_rr,4),"target_rr":MIN_RISK_REWARD,"structure_level":sl_level,"structure_type":level_name,"sl_buffer":buffer,"tp_levels":tp_levels_out,"safe_zone_buffer":safe_limit,"atr":a,"min_structure_risk":a*MIN_STRUCTURE_RISK_ATR,"strategy":strategy}
    levels["support" if direction=="BUY" else "resistance"]=sl_level
    levels["tp_structure_levels"]=[p["price"] for p in tp_levels_out]
    return levels
