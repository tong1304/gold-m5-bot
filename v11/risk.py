from __future__ import annotations
import math
from .common import num, atr14
MIN_RISK_REWARD=2.0
MIN_PIVOT_BARS=2
MAX_STRUCTURE_BARS=100
SL_BUFFER_ATR=.10
MIN_STRUCTURE_RISK_ATR=.50
SAFE_ZONE_ATR=.20
MAX_TP_LEVELS=3

def _pivots(df):
    x=df.tail(MAX_STRUCTURE_BARS).reset_index(drop=True);supports=[];resistances=[]
    for i in range(MIN_PIVOT_BARS,len(x)-MIN_PIVOT_BARS):
        h=num(x.high.iloc[i]);l=num(x.low.iloc[i]);window=x.iloc[i-MIN_PIVOT_BARS:i+MIN_PIVOT_BARS+1]
        if h>=num(window.high.max()):resistances.append((i,h))
        if l<=num(window.low.min()):supports.append((i,l))
    return supports,resistances

def _nearest_levels(df,direction,entry,atr):
    supports,resistances=_pivots(df);gap=max(atr*MIN_STRUCTURE_RISK_ATR,1e-12)
    if direction=="BUY":
        below=sorted({v for _,v in supports if v<entry and entry-v>=gap},reverse=True);above=sorted({v for _,v in resistances if v>entry});return (below[0] if below else None),above
    above=sorted({v for _,v in resistances if v>entry and v-entry>=gap});below=sorted({v for _,v in supports if v<entry},reverse=True);return (above[0] if above else None),below

def calculate(m5,direction:str,strategy:str,evidence:dict|None=None,*,rr:float=MIN_RISK_REWARD):
    evidence=evidence or {};direction=str(direction).upper()
    if direction not in ("BUY","SELL"):return {"valid":False,"reason":"INVALID_DIRECTION"}
    x=m5.reset_index(drop=True);entry=num(x.close.iloc[-1]);a=num(atr14(x).iloc[-1])
    if not math.isfinite(a) or a<=0:return {"valid":False,"reason":"ATR_UNAVAILABLE"}
    sl_level,tp_levels=_nearest_levels(x,direction,entry,a);evidence_level=evidence.get("support") if direction=="BUY" else evidence.get("resistance")
    if evidence_level is not None:
        ev=num(evidence_level)
        if direction=="BUY" and ev<entry and (sl_level is None or ev>sl_level):sl_level=ev
        if direction=="SELL" and ev>entry and (sl_level is None or ev<sl_level):sl_level=ev
    if sl_level is None:return {"valid":False,"reason":"NO_STRUCTURAL_SL","entry":entry,"atr":a,"strategy":strategy}
    buffer=a*SL_BUFFER_ATR;sl=sl_level-buffer if direction=="BUY" else sl_level+buffer;risk=abs(entry-sl)
    if risk<=0:return {"valid":False,"reason":"INVALID_RISK","entry":entry,"sl":sl}
    candidates=[]
    for level in tp_levels:
        reward=(level-entry) if direction=="BUY" else (entry-level)
        if reward>0:candidates.append((level,reward/risk))
    if not candidates:return {"valid":False,"reason":"NO_OPPOSING_STRUCTURE","entry":entry,"sl":sl,"risk":risk,"strategy":strategy}
    first_level,first_rr=candidates[0]
    if first_rr<MIN_RISK_REWARD:return {"valid":False,"reason":"STRUCTURE_RR_BELOW_2","entry":entry,"sl":sl,"risk":risk,"first_tp":first_level,"first_tp_rr":round(first_rr,4),"target_rr":MIN_RISK_REWARD,"strategy":strategy}
    out=[{"price":first_level,"risk_reward":round(first_rr,4),"type":"PRIMARY"}];previous=first_level;safe_limit=a*SAFE_ZONE_ATR
    for level,level_rr in candidates[1:]:
        if abs(level-previous)>=safe_limit:out.append({"price":level,"risk_reward":round(level_rr,4),"type":"EXTENSION"});previous=level
        if len(out)>=MAX_TP_LEVELS:break
    tp=first_level;effective_rr=abs(tp-entry)/risk;result={"valid":True,"entry":entry,"sl":sl,"tp":tp,"risk":risk,"risk_reward":round(effective_rr,4),"effective_rr":round(effective_rr,4),"target_rr":MIN_RISK_REWARD,"structure_level":sl_level,"structure_type":"support" if direction=="BUY" else "resistance","sl_buffer":buffer,"safe_zone_buffer":safe_limit,"tp_levels":out,"tp_structure_levels":[v["price"] for v in out],"atr":a,"strategy":strategy};result["support" if direction=="BUY" else "resistance"]=sl_level;return result
