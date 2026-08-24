from __future__ import annotations
import math
from .common import num, atr14

# V12.1: RR is strategy-specific.
# Trend engines (E1/E2/E4/E5) require >= 2.0R.
# Transition/Range engines (E3/E6/E7/E8) require >= 1.5R.
MIN_RISK_REWARD=1.5
TREND_MIN_RISK_REWARD=2.0
MIN_PIVOT_BARS=2
MAX_STRUCTURE_BARS=100
SL_BUFFER_ATR=.10
MIN_STRUCTURE_RISK_ATR=.50
SAFE_ZONE_ATR=.20
MAX_TP_LEVELS=3

_STRATEGY_MIN_RR={"IMPULSE_PULLBACK":2.0,"TREND_PULLBACK":2.0,"BREAK_RETEST_CONTINUATION":2.0,"MOMENTUM_EXPANSION":2.0,"RANGE_BREAK_EXPANSION":1.5,"EXTREME_REJECTION_MEAN_RETURN":1.5,"SWEEP_REJECTION_REVERSAL":1.5,"RANGE_REJECTION":1.5}

def min_rr_for_strategy(strategy:str, fallback:float=MIN_RISK_REWARD)->float:
    return float(_STRATEGY_MIN_RR.get(str(strategy or "").upper(), fallback))

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

def _strategy_tp_candidates(m5,direction,strategy,evidence,entry,risk):
    strategy=strategy.upper();out=[]
    def add(v):
        v=num(v,None)
        if v is not None and ((direction=="BUY" and v>entry) or (direction=="SELL" and v<entry)):out.append(v)
    if strategy=="RANGE_BREAK_EXPANSION":
        width=num(evidence.get("range_width"),0);level=num(evidence.get("range_high" if direction=="BUY" else "range_low"),None)
        if level is not None and width>0:
            add(level+width*1.0 if direction=="BUY" else level-width*1.0);add(level+width*1.5 if direction=="BUY" else level-width*1.5)
    elif strategy=="BREAK_RETEST_CONTINUATION":
        add(evidence.get("breakout_target"));add(evidence.get("range_high" if direction=="BUY" else "range_low"))
    elif strategy=="MOMENTUM_EXPANSION": add(entry+2*risk if direction=="BUY" else entry-2*risk)
    elif strategy=="EXTREME_REJECTION_MEAN_RETURN": add(evidence.get("bb_mid"));add(evidence.get("range_opposite"))
    elif strategy=="SWEEP_REJECTION_REVERSAL": add(evidence.get("opposite_liquidity"));add(evidence.get("mid_range"))
    elif strategy=="RANGE_REJECTION": add(evidence.get("range_high" if direction=="BUY" else "range_low"))
    elif strategy=="TREND_PULLBACK": add(evidence.get("swing_target"));add(evidence.get("fib_extension_1272"))
    elif strategy=="IMPULSE_PULLBACK": add(evidence.get("swing_target"))
    return list(dict.fromkeys(out))

def calculate(m5,direction:str,strategy:str,evidence:dict|None=None,*,rr:float=MIN_RISK_REWARD):
    evidence=evidence or {};direction=str(direction).upper();strategy=str(strategy).upper()
    if direction not in ("BUY","SELL"):return {"valid":False,"reason":"INVALID_DIRECTION"}
    target_rr=max(float(rr),min_rr_for_strategy(strategy))
    x=m5.reset_index(drop=True);entry=num(x.close.iloc[-1]);a=num(atr14(x).iloc[-1])
    if not math.isfinite(a) or a<=0:return {"valid":False,"reason":"ATR_UNAVAILABLE"}
    sl_level,tp_levels=_nearest_levels(x,direction,entry,a);evidence_level=evidence.get("support") if direction=="BUY" else evidence.get("resistance")
    if evidence_level is not None:
        ev=num(evidence_level)
        if direction=="BUY" and ev<entry and (sl_level is None or ev>sl_level):sl_level=ev
        if direction=="SELL" and ev>entry and (sl_level is None or ev<sl_level):sl_level=ev
    if sl_level is None:return {"valid":False,"reason":"NO_STRUCTURAL_SL","entry":entry,"atr":a,"strategy":strategy,"target_rr":target_rr}
    buffer=a*SL_BUFFER_ATR;sl=sl_level-buffer if direction=="BUY" else sl_level+buffer;risk=abs(entry-sl)
    if risk<=0:return {"valid":False,"reason":"INVALID_RISK","entry":entry,"sl":sl,"target_rr":target_rr}
    preferred=_strategy_tp_candidates(x,direction,strategy,evidence,entry,risk);candidates=[]
    for level in preferred+tp_levels:
        reward=(level-entry) if direction=="BUY" else (entry-level)
        if reward>0 and level not in [p[0] for p in candidates]:candidates.append((level,reward/risk))
    if not candidates:return {"valid":False,"reason":"NO_OPPOSING_STRUCTURE","entry":entry,"sl":sl,"risk":risk,"strategy":strategy,"target_rr":target_rr}
    qualifying=[item for item in candidates if item[1]>=target_rr]
    if not qualifying:
        first_level,first_rr=candidates[0]
        return {"valid":False,"reason":f"STRUCTURE_RR_BELOW_{target_rr:g}","entry":entry,"sl":sl,"risk":risk,"first_tp":first_level,"first_tp_rr":round(first_rr,4),"target_rr":target_rr,"strategy":strategy}
    first_level,first_rr=qualifying[0];out=[{"price":first_level,"risk_reward":round(first_rr,4),"type":"PRIMARY"}];previous=first_level;safe_limit=a*SAFE_ZONE_ATR
    for level,level_rr in candidates:
        if level==first_level:continue
        if abs(level-previous)>=safe_limit and level_rr>=target_rr:
            out.append({"price":level,"risk_reward":round(level_rr,4),"type":"EXTENSION"});previous=level
        if len(out)>=MAX_TP_LEVELS:break
    tp=first_level;effective_rr=abs(tp-entry)/risk
    result={"valid":True,"entry":entry,"sl":sl,"tp":tp,"risk":risk,"risk_reward":round(effective_rr,4),"effective_rr":round(effective_rr,4),"target_rr":target_rr,"minimum_rr":target_rr,"structure_level":sl_level,"structure_type":"support" if direction=="BUY" else "resistance","sl_buffer":buffer,"safe_zone_buffer":safe_limit,"tp_levels":out,"tp_structure_levels":[v["price"] for v in out],"atr":a,"strategy":strategy,"tp_selection":"ENGINE_STRUCTURE_THEN_NEAREST_STRUCTURE"}
    result["support" if direction=="BUY" else "resistance"]=sl_level;return result
