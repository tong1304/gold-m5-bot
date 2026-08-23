"""V9.1 signal engine: H1 structure + M15 S/R/location + M5 multi-candle price-action trigger.
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

def _candle_quality(row,direction,atr):
    o,h,l,c=map(_num,(row.open,row.high,row.low,row.close)); body=abs(c-o); rng=max(h-l,1e-12); upper=h-max(o,c); lower=min(o,c)-l
    body_ratio=body/rng; close_location=(c-l)/rng
    directional=(c>o) if direction=="BUY" else (c<o)
    return {"body":body,"range":rng,"upper_wick":upper,"lower_wick":lower,"body_ratio":body_ratio,"close_location":close_location,"directional":directional,"atr":atr}

def _m5_pattern_v91(df,direction):
    """Detect an actionable pattern using a recent M5 window, not only the last candle.

    The last closed candle must still be the trigger/confirmation candle. Earlier
    candles are used to build the pattern context so we do not enter on stale setups.
    """
    if df is None or len(df)<25:return None
    x=df.reset_index(drop=True); i=len(x)-1; r=x.iloc[i]; q=x.iloc[i-1]; p3=x.iloc[i-2]; atr=max(_v9._atr(x,i),1e-9)
    rq=_candle_quality(r,direction,atr)
    o,h,l,c=map(_num,(r.open,r.high,r.low,r.close)); qh,ql=map(_num,(q.high,q.low)); p3h,p3l=_num(p3.high),_num(p3.low)

    # Keep engulfing/pin-bar strict on the latest candle. A plain breakout is
    # intentionally evaluated later because it may actually be a breakout-retest.
    p=_v9._candle_pattern(x,direction)
    if p and p.get("name") not in ("BULLISH_BREAKOUT","BEARISH_BREAKOUT"):
        p["quality"]="CLEAR"; p["context_bars"]=2; return p

    # Inside-bar breakout: the previous candle is inside the candle before it,
    # and the latest candle closes through the mother bar with a decisive body.
    if qh<p3h and ql>p3l and rq["directional"] and rq["body_ratio"]>=0.30:
        if direction=="BUY" and c>p3h and c>qh:
            return {"name":"INSIDE_BAR_BREAKOUT","direction":"BUY","index":i,"strength":"CLEAR","quality":"CLEAR","context_bars":3}
        if direction=="SELL" and c<p3l and c<ql:
            return {"name":"INSIDE_BAR_BREAKOUT","direction":"SELL","index":i,"strength":"CLEAR","quality":"CLEAR","context_bars":3}

    # Breakout + retest: search recent candles for a real level break, then
    # require the current candle to retest and hold that level. This uses 5-12 bars.
    start=max(3,i-12)
    for j in range(start,i-1):
        base=x.iloc[max(0,j-4):j]
        if len(base)<3: continue
        level=_num(base.high.max()) if direction=="BUY" else _num(base.low.min())
        b=x.iloc[j]; bo,bh,bl,bc=map(_num,(b.open,b.high,b.low,b.close)); bq=_candle_quality(b,direction,max(_v9._atr(x,j),1e-9))
        broke=(bc>level and bq["body_ratio"]>=0.30 and bc>bo) if direction=="BUY" else (bc<level and bq["body_ratio"]>=0.30 and bc<bo)
        if not broke: continue
        if direction=="BUY":
            retest_touch=l<=level+atr*.55; held=c>=level; confirm=c>o and rq["body_ratio"]>=0.25
        else:
            retest_touch=h>=level-atr*.55; held=c<=level; confirm=c<o and rq["body_ratio"]>=0.25
        if retest_touch and held and confirm and i-j<=5:
            return {"name":"BULLISH_BREAKOUT_RETEST" if direction=="BUY" else "BEARISH_BREAKOUT_RETEST","direction":direction,"index":i,"strength":"CLEAR","quality":"CLEAR","context_bars":i-j+1,"level":level,"breakout_index":j}

    # If the latest candle is itself a clean breakout and no retest structure
    # exists, retain the original V9 breakout pattern.
    if p:
        p["quality"]="CLEAR"; p["context_bars"]=2; return p

    # Double bottom/top: two nearby swing extremes plus a neckline break on the
    # latest candle. This prevents a mere two-touch resemblance from becoming a trade.
    window=x.iloc[max(0,i-18):i+1].reset_index(drop=True); wi=len(window)-1
    if len(window)>=10:
        swings_low=[]; swings_high=[]
        for k in range(2,wi-2):
            lo_k=_num(window.iloc[k].low); hi_k=_num(window.iloc[k].high)
            if lo_k<=min(_num(v) for v in window.low.iloc[k-2:k+3]): swings_low.append(k)
            if hi_k>=max(_num(v) for v in window.high.iloc[k-2:k+3]): swings_high.append(k)
        tol=atr*.75
        if direction=="BUY" and len(swings_low)>=2:
            a,b=swings_low[-2],swings_low[-1]; la,lb=_num(window.iloc[a].low),_num(window.iloc[b].low)
            neckline=_num(window.iloc[a:b+1].high.max())
            if abs(la-lb)<=tol and wi-b<=3 and c>neckline and c>o and rq["body_ratio"]>=.25:
                return {"name":"DOUBLE_BOTTOM_BREAKOUT","direction":"BUY","index":i,"strength":"CLEAR","quality":"CLEAR","context_bars":wi-a+1,"neckline":neckline}
        if direction=="SELL" and len(swings_high)>=2:
            a,b=swings_high[-2],swings_high[-1]; ha,hb=_num(window.iloc[a].high),_num(window.iloc[b].high)
            neckline=_num(window.iloc[a:b+1].low.min())
            if abs(ha-hb)<=tol and wi-b<=3 and c<neckline and c<o and rq["body_ratio"]>=.25:
                return {"name":"DOUBLE_TOP_BREAKOUT","direction":"SELL","index":i,"strength":"CLEAR","quality":"CLEAR","context_bars":wi-a+1,"neckline":neckline}

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
    if levels.get("reason")=="RR_BELOW_2R": levels["reason"]="RR_BELOW_1R"
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

    # Pattern-first risk evaluation: do not calculate or report RR until a
    # valid M5 pattern exists. This prevents misleading RR_BELOW_1R on a
    # setup that has no actionable entry/invalidation yet.
    sweep=None; mss=None; retest={"valid":False,"reason":"NO_MSS_BOS_CONFIRMATION"}; target=None; invalidation=None
    levels={"valid":False,"reason":None}
    if pattern and not any(r in reasons for r in ("M15_OPPOSES_H1","M15_LOCATION_INVALID","PATTERN_DIRECTION_MISMATCH")):
        sweep=_v9._find_sweep(m5,direction); mss=_v9._find_mss(m5,sweep,direction)
        if sweep and not mss:mss=_v9._find_mss(m5,sweep,direction,window=16)
        retest=_v9._retest(m5,mss,direction) if mss else {"valid":False,"reason":"NO_MSS_BOS_CONFIRMATION"}
        if pattern.get("name") not in ("BULLISH_BREAKOUT","BEARISH_BREAKOUT","INSIDE_BAR_BREAKOUT","BULLISH_BREAKOUT_RETEST","BEARISH_BREAKOUT_RETEST","DOUBLE_BOTTOM_BREAKOUT","DOUBLE_TOP_BREAKOUT") and mss is None:reasons.append("NO_M5_CONFIRMATION")
        entry=_num(m5.iloc[-1].close); target=_v9._target_liquidity(m5,direction,entry)
        if target is None:reasons.append("NO_LIQUIDITY_TARGET")
        invalidation=sweep["extreme"] if sweep else (loc.get("support") if direction=="BUY" else loc.get("resistance"))
        if target is not None and invalidation is not None:
            levels=build_trade_levels(m5,len(m5)-1,direction,invalidation,target,pattern)
            if not levels.get("valid"):reasons.append(levels.get("reason","LEVELS_INVALID"))

    indicators=_indicator_context_flags(m5,direction); confirmations=[]
    if pattern:confirmations.append("CLEAR_M5_PATTERN")
    if sweep:confirmations.append("LIQUIDITY_SWEEP")
    if mss:confirmations.append("MSS_BOS")
    if retest.get("valid"):confirmations.append("M5_RETEST_CONFIRMATION")
    signal=direction if not reasons else "NO_TRADE"
    return {"signal":signal,"engine_version":ENGINE_VERSION,"valid":signal in ("BUY","SELL") and levels.get("valid",False),"structure_bias":h1s,"m15_structure":m15s,"location":loc,"pattern":pattern,"pattern_valid":bool(pattern),"confirmations":confirmations,"liquidity_event":sweep,"m5_trigger":mss,"pullback":retest,"target_liquidity":target,"invalidation":invalidation,"trade_levels":levels,"indicator_context":indicators,"setup_key":f"{direction}:{(pattern or {}).get('name','NONE')}:{sweep.get('index') if sweep else 'NO_SWEEP'}:{mss.get('index') if mss else 'NO_MSS'}","rejection_reasons":reasons}

def calculate_indicators(df):return _indicator_context(df)
