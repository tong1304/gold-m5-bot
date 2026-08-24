from __future__ import annotations
import math
import pandas as pd
from .common import num, atr14

MIN_RISK_REWARD=2.0
STRUCTURE_LOOKBACK=25
PIVOT_LEFT=2
PIVOT_RIGHT=2
SL_BUFFER_ATR=0.10
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


def _structure_levels(df,direction,entry):
    supports,resistances=_pivot_levels(df)
    if direction=="BUY":
        below=[v for _,v in supports if v<entry]
        above=[v for _,v in resistances if v>entry]
        if not below:
            below=[num(df.loc[pd.to_numeric(df.low,errors="coerce")<entry,"low"].min())]
        return "support", max(below), sorted(set(above))
    above=[v for _,v in resistances if v>entry]
    below=[v for _,v in supports if v<entry]
    if not above:
        above=[num(df.loc[pd.to_numeric(df.high,errors="coerce")>entry,"high"].max())]
    return "resistance", min(above), sorted(set(below),reverse=True)


def calculate(m5,direction: str,strategy: str,evidence: dict|None=None,*,rr: float=MIN_RISK_REWARD):
    evidence=evidence or {}
    if direction not in ("BUY","SELL"): return {"valid":False,"reason":"INVALID_DIRECTION"}
    x=m5.tail(STRUCTURE_LOOKBACK).reset_index(drop=True)
    if len(x)<14: return {"valid":False,"reason":"INSUFFICIENT_RISK_CONTEXT"}
    entry=num(x.close.iloc[-1]); a=num(atr14(x).iloc[-1])
    if not math.isfinite(entry) or entry<=0 or not math.isfinite(a) or a<=0: return {"valid":False,"reason":"ATR_UNAVAILABLE"}
    level_name,sl_level,tp_levels=_structure_levels(x,direction,entry)
    if not math.isfinite(sl_level) or sl_level<=0: return {"valid":False,"reason":"STRUCTURE_LEVEL_UNAVAILABLE"}
    buffer=a*SL_BUFFER_ATR
    if direction=="BUY":
        if sl_level>=entry: return {"valid":False,"reason":"NO_SUPPORT_BELOW_ENTRY"}
        sl=sl_level-buffer; risk=entry-sl
    else:
        if sl_level<=entry: return {"valid":False,"reason":"NO_RESISTANCE_ABOVE_ENTRY"}
        sl=sl_level+buffer; risk=sl-entry
    if not math.isfinite(risk) or risk<=0: return {"valid":False,"reason":"INVALID_RISK"}

    # TP is determined by actual market structure. Never move TP merely to manufacture 2R.
    candidates=[]
    for level in tp_levels:
        level=num(level)
        if direction=="BUY" and level>entry: reward=level-entry
        elif direction=="SELL" and level<entry: reward=entry-level
        else: continue
        level_rr=reward/risk
        candidates.append((level,level_rr))

    if not candidates:
        return {"valid":False,"reason":"NO_TP_STRUCTURE_LEVEL"}

    valid_candidates=[(level,level_rr) for level,level_rr in candidates if level_rr>=MIN_RISK_REWARD]
    if not valid_candidates:
        first_level,first_rr=candidates[0]
        return {"valid":False,"reason":"STRUCTURE_RR_BELOW_2","entry":entry,"sl":sl,"risk":risk,"first_tp":first_level,"first_tp_rr":round(first_rr,4),"target_rr":MIN_RISK_REWARD,"structure_level":sl_level,"structure_type":level_name,"strategy":strategy}

    # First structure target reaching 2R is the primary TP. Later levels are optional
    # extensions only while the next resistance/support remains a safe structural zone.
    primary_level,primary_rr=valid_candidates[0]
    tp_levels_out=[]
    safe_limit=a*SAFE_ZONE_ATR
    for level,level_rr in valid_candidates:
        if not tp_levels_out:
            tp_levels_out.append({"price":level,"risk_reward":round(level_rr,4),"type":"PRIMARY"})
            continue
        previous=tp_levels_out[-1]["price"]
        # Require a meaningful structural gap; do not stack targets inside the same zone.
        if abs(level-previous)>=safe_limit:
            tp_levels_out.append({"price":level,"risk_reward":round(level_rr,4),"type":"EXTENSION"})
        if len(tp_levels_out)>=MAX_TP_LEVELS: break

    tp=primary_level
    effective_rr=(abs(tp-entry)/risk)
    levels={"valid":True,"entry":entry,"sl":sl,"tp":tp,"risk":risk,"risk_reward":round(effective_rr,4),"effective_rr":round(effective_rr,4),"target_rr":MIN_RISK_REWARD,"structure_level":sl_level,"structure_type":level_name,"sl_buffer":buffer,"tp_levels":tp_levels_out,"safe_zone_buffer":safe_limit,"strategy":strategy}
    levels["support" if direction=="BUY" else "resistance"]=sl_level
    levels["tp_structure_levels"]=[p["price"] for p in tp_levels_out]
    return levels
