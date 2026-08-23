"""V9.1 signal engine: H1 structure + M15 S/R/location + M5 price-action trigger.
Indicators are context/risk tools only; no weighted scoring. Minimum RR is 1.0R.
"""
from __future__ import annotations
import math
import os
import pandas as pd
import engine_v9_standalone as _v9
from engine_v9_standalone import *

ENGINE_VERSION="9.1"
MIN_RISK_REWARD=max(float(os.getenv("MIN_RISK_REWARD","1.0")),1.0)
RISK_REWARD=max(float(os.getenv("RISK_REWARD",str(MIN_RISK_REWARD))),1.0)

def _num(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d

def _swing_structure(df,left=2,right=2,lookback=80):
    if df is None or len(df)<20:return {"bias":"NEUTRAL","highs":[],"lows":[],"support":None,"resistance":None}
    x=df.reset_index(drop=True).tail(lookback).reset_index(drop=True); highs=[]; lows=[]
    for i in range(left,len(x)-right):
        h=_num(x.iloc[i].high); l=_num(x.iloc[i].low)
        window_h=max(_num(v) for v in x.high.iloc[i-left:i+right+1]); window_l=min(_num(v) for v in x.low.iloc[i-left:i+right+1])
        if h>=window_h and h>max(_num(v) for v in x.high.iloc[i-left:i]): highs.append((i,h))
        if l<=window_l and l<min(_num(v) for v in x.low.iloc[i-left:i]): lows.append((i,l))
    highs=highs[-5:]; lows=lows[-5:]; bias="NEUTRAL"
    if len(highs)>=2 and len(lows)>=2:
        hh=highs[-1][1]>highs[-2][1]; hl=lows[-1][1]>lows[-2][1]; lh=highs[-1][1]<highs[-2][1]; ll=lows[-1][1]<lows[-2][1]
        if hh and hl:bias="BUY"
        elif lh and ll:bias="SELL"
    return {"bias":bias,"highs":[v for _,v in highs],"lows":[v for _,v in lows],"support":lows[-1][1] if lows else None,"resistance":highs[-1][1] if highs else None}

def _sr_location(df,direction,lookback=64):
    if df is None or len(df)<30:return {"valid":False,"zone":"INSUFFICIENT_DATA"}
    x=df.tail(lookback).reset_index(drop=True); hi=_num(x.high.max()); lo=_num(x.low.min()); width=max(hi-lo,1e-12); close=_num(x.iloc[-1].close); mid=lo+width*.5; swing=_swing_structure(x)
    support=swing.get("support") or lo; resistance=swing.get("resistance") or hi; atr=max(_v9._atr(x,len(x)-1),1e-9)
    near_support=abs(close-support)<=max(atr,width*.10); near_resistance=abs(close-resistance)<=max(atr,width*.10)
    if direction=="BUY": valid=close<=mid or near_support; zone="DISCOUNT_SUPPORT" if valid else "PREMIUM"
    else: valid=close>=mid or near_resistance; zone="PREMIUM_RESISTANCE" if valid else "DISCOUNT"
    return {"valid":bool(valid),"zone":zone,"range_high":hi,"range_low":lo,"mid":mid,"support":support,"resistance":resistance,"near_support":near_support,"near_resistance":near_resistance}

def _m5_pattern_v91(df,direction):
    p=_v9._candle_pattern(df,direction)
    if p:p["quality"]="CLEAR"; return p
    if df is None or len(df)<25:return None
    x=df.reset_index(drop=True); r=x.iloc[-1]; q=x.iloc[-2]; p3=x.iloc[-3]; o,h,l,c=map(float,(r.open,r.high,r.low,r.close)); qo,qh,ql,qc=map(float,(q.open,q.high,q.low,q.close)); body=abs(c-o); rng=max(h-l,1e-12); atr=_v9._atr(x,len(x)-1)
    if direction=="BUY":
        if qh<p3.high and ql>p3.low and c>qh and body>=max(atr*.18,rng*.30):return {"name":"INSIDE_BAR_BREAKOUT","direction":"BUY","index":len(x)-1,"strength":"CLEAR","quality":"CLEAR"}
        if c>o and qc<qo and c>qc and abs(c-o)>abs(qc-qo)*1.15:return {"name":"BULLISH_BREAKOUT_RETEST","direction":"BUY","index":len(x)-1,"strength":"CLEAR","quality":"CLEAR"}
    else:
        if qh<p3.high and ql>p3.low and c<ql and body>=max(atr*.18,rng*.30):return {"name":"INSIDE_BAR_BREAKOUT","direction":"SELL","index":len(x)-1,"strength":"CLEAR","quality":"CLEAR"}
        if c<o and qc>qo and c<qc and abs(c-o)>abs(qc-qo)*1.15:return {"name":"BEARISH_BREAKOUT_RETEST","direction":"SELL","index":len(x)-1,"strength":"CLEAR","quality":"CLEAR"}
    return None

def _indicator_context(df):
    x=df.copy(); c=pd.to_numeric(x.close,errors="coerce"); x["ema20"]=c.ewm(span=20,adjust=False).mean(); x["ema50"]=c.ewm(span=50,adjust=False).mean(); delta=c.diff(); gain=delta.clip(lower=0).rolling(14,min_periods=5).mean(); loss=(-delta.clip(upper=0)).rolling(14,min_periods=5).mean(); rs=gain/loss.replace(0,float("nan")); x["rsi14"]=100-(100/(1+rs)); ema12=c.ewm(span=12,adjust=False).mean(); ema26=c.ewm(span=26,adjust=False).mean(); x["macd"]=ema12-ema26; x["macd_signal"]=x["macd"].ewm(span=9,adjust=False).mean(); x["atr14"]=_v9.calculate_indicators(x)["atr14"]; return x

def _indicator_context_flags(df,direction):
    x=_indicator_context(df); r=x.iloc[-1]; ema_ok=(_num(r.close)>=_num(r.ema20)) if direction=="BUY" else (_num(r.close)<=_num(r.ema20)); macd_ok=(_num(r.macd)>=_num(r.macd_signal)) if direction=="BUY" else (_num(r.macd)<=_num(r.macd_signal)); rsi=_num(r.rsi14,50.0)
    return {"ema20_ok":bool(ema_ok),"macd_ok":bool(macd_ok),"rsi14":round(rsi,2),"rsi_extreme":bool(rsi>=75 or rsi<=25),"role":"CONTEXT_ONLY"}

def build_trade_levels(df,index,direction,invalidation,target,pattern=None):
    old_min=_v9.MIN_RISK_REWARD; _v9.MIN_RISK_REWARD=1.0
    try: levels=_v9.build_trade_levels(df,index,direction,invalidation,target,pattern)
    finally: _v9.MIN_RISK_REWARD=old_min
    if levels.get("valid"): levels["source"]="structure_v9_1"
    return levels

def analyze_structure_setup(m5,m15,h1,index=None):
    if index is None:index=len(m5)-1
    m5=m5.iloc[:index+1].reset_index(drop=True)
    if len(m5)<80 or len(m15)<60 or len(h1)<60:return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    h1s=_swing_structure(h1); direction=h1s["bias"]
    if direction not in ("BUY","SELL"):return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["H1_NEUTRAL"],"structure_bias":h1s}
    m15s=_swing_structure(m15); loc=_sr_location(m15,direction); reasons=[]
    if m15s["bias"] in ("BUY","SELL") and m15s["bias"]!=direction:reasons.append("M15_OPPOSES_H1")
    if not loc["valid"]:reasons.append("M15_LOCATION_INVALID")
    pattern=_m5_pattern_v91(m5,direction)
    if not pattern:reasons.append("NO_CLEAR_M5_PATTERN")
    if pattern and pattern.get("direction")!=direction:reasons.append("PATTERN_DIRECTION_MISMATCH")
    sweep=_v9._find_sweep(m5,direction); mss=_v9._find_mss(m5,sweep,direction)
    if sweep and not mss:mss=_v9._find_mss(m5,sweep,direction,window=16)
    retest=_v9._retest(m5,mss,direction) if mss else {"valid":False,"reason":"NO_MSS_BOS_CONFIRMATION"}
    if pattern and pattern.get("name") not in ("BULLISH_BREAKOUT","BEARISH_BREAKOUT","INSIDE_BAR_BREAKOUT","BULLISH_BREAKOUT_RETEST","BEARISH_BREAKOUT_RETEST") and mss is None:reasons.append("NO_M5_CONFIRMATION")
    entry=_num(m5.iloc[-1].close); target=_v9._target_liquidity(m5,direction,entry)
    if target is None:reasons.append("NO_LIQUIDITY_TARGET")
    invalidation=sweep["extreme"] if sweep else (loc.get("support") if direction=="BUY" else loc.get("resistance")); levels=build_trade_levels(m5,len(m5)-1,direction,invalidation,target,pattern)
    if not levels.get("valid"):reasons.append("RR_BELOW_1R" if levels.get("risk_reward",0)<1 else levels.get("reason","LEVELS_INVALID"))
    indicators=_indicator_context_flags(m5,direction); confirmations=[]
    if pattern:confirmations.append("CLEAR_M5_PATTERN")
    if sweep:confirmations.append("LIQUIDITY_SWEEP")
    if mss:confirmations.append("MSS_BOS")
    if retest.get("valid"):confirmations.append("M5_RETEST_CONFIRMATION")
    signal=direction if not reasons else "NO_TRADE"
    return {"signal":signal,"engine_version":ENGINE_VERSION,"valid":signal in ("BUY","SELL") and levels.get("valid",False),"structure_bias":h1s,"m15_structure":m15s,"location":loc,"pattern":pattern,"pattern_valid":bool(pattern),"confirmations":confirmations,"liquidity_event":sweep,"m5_trigger":mss,"pullback":retest,"target_liquidity":target,"invalidation":invalidation,"trade_levels":levels,"indicator_context":indicators,"setup_key":f"{direction}:{(pattern or {}).get('name','NONE')}:{sweep.get('index') if sweep else 'NO_SWEEP'}:{mss.get('index') if mss else 'NO_MSS'}","rejection_reasons":reasons}

def calculate_indicators(df):return _indicator_context(df)
