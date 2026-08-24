from __future__ import annotations
import math
import pandas as pd
from .common import num, atr14

MIN_RISK_REWARD=2.0
STRUCTURE_LOOKBACK=25
SL_BUFFER_ATR=0.10


def _latest_structure_level(df, direction: str):
    """Return the most recent confirmed M5 swing level on the safe side of entry."""
    x=df.tail(STRUCTURE_LOOKBACK).reset_index(drop=True)
    entry=num(x.close.iloc[-1])
    pivots=[]
    for i in range(2,max(2,len(x)-2)):
        high=num(x.high.iloc[i]); low=num(x.low.iloc[i])
        if high >= max(num(v) for v in x.high.iloc[i-2:i+3]) and direction=="SELL" and high>entry:
            pivots.append((i,"resistance",high))
        if low <= min(num(v) for v in x.low.iloc[i-2:i+3]) and direction=="BUY" and low<entry:
            pivots.append((i,"support",low))
    if pivots:
        return pivots[-1][1], pivots[-1][2]
    if direction=="BUY":
        safe=x.loc[pd.to_numeric(x.low,errors="coerce")<entry,"low"]
        return "support", num(safe.iloc[-1] if len(safe) else x.low.min())
    safe=x.loc[pd.to_numeric(x.high,errors="coerce")>entry,"high"]
    return "resistance", num(safe.iloc[-1] if len(safe) else x.high.max())


def calculate(m5,direction: str,strategy: str,evidence: dict|None=None,*,rr: float=MIN_RISK_REWARD):
    evidence=evidence or {}
    if direction not in ("BUY","SELL"):return {"valid":False,"reason":"INVALID_DIRECTION"}
    x=m5.tail(STRUCTURE_LOOKBACK).reset_index(drop=True)
    if len(x)<14:return {"valid":False,"reason":"INSUFFICIENT_RISK_CONTEXT"}
    entry=num(x.close.iloc[-1]); a=num(atr14(x).iloc[-1])
    if not math.isfinite(entry) or entry<=0 or not math.isfinite(a) or a<=0:return {"valid":False,"reason":"ATR_UNAVAILABLE"}
    level_name,raw=_latest_structure_level(x,direction); raw=num(raw)
    if not math.isfinite(raw) or raw<=0:return {"valid":False,"reason":"STRUCTURE_LEVEL_UNAVAILABLE"}
    buffer=a*SL_BUFFER_ATR
    if direction=="BUY":
        if raw>=entry:return {"valid":False,"reason":"NO_SUPPORT_BELOW_ENTRY"}
        sl=raw-buffer; risk=entry-sl
    else:
        if raw<=entry:return {"valid":False,"reason":"NO_RESISTANCE_ABOVE_ENTRY"}
        sl=raw+buffer; risk=sl-entry
    if not math.isfinite(risk) or risk<=0:return {"valid":False,"reason":"INVALID_RISK"}
    # RR remains fixed at exactly 1:2. Strategy evidence cannot override TP.
    tp=entry+rr*risk if direction=="BUY" else entry-rr*risk
    if not all(math.isfinite(v) for v in (sl,tp,risk)) or min(entry,sl,tp)<=0:return {"valid":False,"reason":"INVALID_RISK"}
    effective_rr=abs(tp-entry)/risk
    valid=effective_rr>=MIN_RISK_REWARD and ((direction=="BUY" and sl<entry<tp) or (direction=="SELL" and sl>entry>tp))
    return {"valid":bool(valid),"entry":entry,"sl":sl,"tp":tp,"risk":risk,"risk_reward":round(effective_rr,4),"effective_rr":round(effective_rr,4),"target_rr":MIN_RISK_REWARD,"structure_level":raw,"structure_type":level_name,"sl_buffer":buffer,"strategy":strategy}
