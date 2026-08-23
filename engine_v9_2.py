"""Multi-Strategy Engine v10.0.

Keeps the V9 standalone infrastructure/risk/Telegram API while replacing the
single pattern gate with regime-aware strategy selection for BTC and GOLD.
"""
from __future__ import annotations
import math
import os
import pandas as pd
import engine_v9_standalone as _v9
from engine_v9_standalone import *
import strategy_engine as _ms

ENGINE_VERSION = "10.0-MULTI"
MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "1.0")), 1.0)
RISK_REWARD = max(float(os.getenv("RISK_REWARD", str(MIN_RISK_REWARD))), 1.0)
H1_ATR_MIN_RATIO = float(os.getenv("H1_ATR_MIN_RATIO", "0.50"))
H1_ATR_MAX_RATIO = float(os.getenv("H1_ATR_MAX_RATIO", "2.00"))


def _num(v, d=0.0):
    try:
        x=float(v)
        return x if math.isfinite(x) else d
    except (TypeError, ValueError):
        return d


def _structure(df, lookback=80):
    x=df.tail(lookback).reset_index(drop=True)
    if len(x)<20:return {"bias":"NEUTRAL","highs":[],"lows":[],"support":None,"resistance":None}
    highs=[]; lows=[]
    for i in range(2,len(x)-2):
        h=_num(x.high.iloc[i]); l=_num(x.low.iloc[i])
        if h>=max(_num(v) for v in x.high.iloc[i-2:i+3]):highs.append(h)
        if l<=min(_num(v) for v in x.low.iloc[i-2:i+3]):lows.append(l)
    hh=len(highs)>=2 and highs[-1]>highs[-2]; hl=len(lows)>=2 and lows[-1]>lows[-2]
    lh=len(highs)>=2 and highs[-1]<highs[-2]; ll=len(lows)>=2 and lows[-1]<lows[-2]
    bias="BUY" if hh and hl else "SELL" if lh and ll else "NEUTRAL"
    return {"bias":bias,"highs":highs[-5:],"lows":lows[-5:],"support":lows[-1] if lows else None,"resistance":highs[-1] if highs else None}


def _indicator_context(df):
    x=df.copy(); c=pd.to_numeric(x.close,errors="coerce")
    x["ema20"]=c.ewm(span=20,adjust=False).mean(); x["ema50"]=c.ewm(span=50,adjust=False).mean()
    d=c.diff(); gain=d.clip(lower=0).rolling(14,min_periods=5).mean(); loss=(-d.clip(upper=0)).rolling(14,min_periods=5).mean()
    rs=gain/loss.replace(0,float("nan")); x["rsi14"]=100-(100/(1+rs))
    e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean(); x["macd"]=e12-e26; x["macd_signal"]=x["macd"].ewm(span=9,adjust=False).mean(); x["atr14"]=_v9.calculate_indicators(x)["atr14"]
    return x


def _indicator_context_flags(df,direction):
    x=_indicator_context(df); r=x.iloc[-1]; rsi=_num(r.rsi14,50)
    return {"ema20_ok":bool((_num(r.close)>=_num(r.ema20)) if direction=="BUY" else (_num(r.close)<=_num(r.ema20))),"macd_ok":bool((_num(r.macd)>=_num(r.macd_signal)) if direction=="BUY" else (_num(r.macd)<=_num(r.macd_signal))),"rsi14":round(rsi,2),"rsi_extreme":bool(rsi>=75 or rsi<=25),"role":"CONTEXT_ONLY"}


def _location(m15,direction):
    x=m15.tail(64).reset_index(drop=True); hi=_num(x.high.max()); lo=_num(x.low.min()); close=_num(x.close.iloc[-1]); width=max(hi-lo,1e-12); mid=lo+width*.5
    s=_structure(x); support=s.get("support") or lo; resistance=s.get("resistance") or hi
    atr=max(_num(_v9._atr(x,len(x)-1)),1e-9); near_s=abs(close-support)<=max(atr,width*.1); near_r=abs(close-resistance)<=max(atr,width*.1)
    valid=(close<=mid or near_s) if direction=="BUY" else (close>=mid or near_r)
    return {"valid":bool(valid),"zone":"DISCOUNT_SUPPORT" if direction=="BUY" and valid else "PREMIUM_RESISTANCE" if direction=="SELL" and valid else "PREMIUM" if direction=="BUY" else "DISCOUNT","range_high":hi,"range_low":lo,"mid":mid,"support":support,"resistance":resistance,"near_support":near_s,"near_resistance":near_r}


def _levels(df,index,direction,invalidation,target,pattern=None):
    old=MIN_RISK_REWARD
    globals()["MIN_RISK_REWARD"]=1.0
    _v9.MIN_RISK_REWARD=1.0
    try: out=_v9.build_trade_levels(df,index,direction,invalidation,target,pattern)
    finally: globals()["MIN_RISK_REWARD"]=old; _v9.MIN_RISK_REWARD=old
    if out.get("valid"):out["source"]="multi_strategy_structure"
    return out


def _invalidation(m5,m15,direction,strategy):
    x=m5.tail(20).reset_index(drop=True); atr=max(_num(_v9._atr(x,len(x)-1)),1e-9)
    if strategy=="LIQUIDITY_SWEEP":
        return _num(x.low.min())-atr*.10 if direction=="BUY" else _num(x.high.max())+atr*.10
    s=_structure(m15); return (s.get("support") if direction=="BUY" else s.get("resistance")) or (_num(x.low.min()) if direction=="BUY" else _num(x.high.max()))


def analyze_structure_setup(m5,m15,h1,index=None):
    if index is None:index=len(m5)-1
    m5=m5.iloc[:index+1].reset_index(drop=True); symbol=str(globals().get("SYMBOL","BTC/USDT")).upper()
    if len(m5)<80 or len(m15)<100 or len(h1)<50:
        return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"strategy":"NONE","regime":"NEUTRAL","rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    ms=_ms.analyze(m5,m15,h1,symbol)
    direction=ms.get("signal") if ms.get("signal") in ("BUY","SELL") else None
    out=dict(ms); out["engine_version"]=ENGINE_VERSION
    out["structure_bias"]={"decision":direction or "NEUTRAL","bias":ms.get("regime_detail",{}).get("direction","NEUTRAL"),"ema_context":ms.get("regime_detail",{}).get("direction","NEUTRAL"),"volatility_state":ms.get("regime")}
    out["m15_structure"]=_structure(m15,100); out["location"]=_location(m15,direction) if direction else {"valid":False,"zone":"NO_DIRECTION"}
    out["indicator_context"]=_indicator_context_flags(m5,direction) if direction else {"role":"CONTEXT_ONLY"}
    if not direction:
        out.update({"pattern":None,"pattern_valid":False,"trade_levels":{"valid":False,"reason":"NO_STRATEGY_SETUP"},"confirmations":[]})
        return out
    target=_v9._target_liquidity(m5,direction); invalidation=_invalidation(m5,m15,direction,ms.get("strategy")); levels=_levels(m5,len(m5)-1,direction,invalidation,target,ms.get("strategy")) if target is not None and invalidation is not None else {"valid":False,"reason":"NO_LEVELS"}
    reasons=list(out.get("rejection_reasons") or [])
    if target is None:reasons.append("NO_LIQUIDITY_TARGET")
    if not levels.get("valid"):reasons.append(levels.get("reason","LEVELS_INVALID"))
    out["rejection_reasons"]=reasons; out["trade_levels"]=levels; out["target_liquidity"]=target; out["invalidation"]=invalidation
    out["pattern"]={"name":ms.get("strategy"),"direction":direction,"quality":"CLEAR","context_bars":ms.get("analysis_window",{}).get("m5_setup_bars",20)}
    out["pattern_valid"]=bool(ms.get("valid")); out["m5_trigger"]={"strategy":ms.get("strategy"),"direction":direction,"trigger_candles":ms.get("trigger_candle_count",3)}
    out["pullback"]={"strategy":ms.get("strategy"),"valid":ms.get("strategy") in ("TREND_PULLBACK","EMA_PULLBACK")}
    out["liquidity_event"]={"strategy":ms.get("strategy"),"detected":ms.get("strategy")=="LIQUIDITY_SWEEP"}
    out["confirmations"]=["REGIME_SELECTED",f"STRATEGY_{ms.get('strategy')}","CLOSED_M5_TRIGGER"]
    out["valid"]=bool(ms.get("valid")) and bool(levels.get("valid")) and not reasons
    out["signal"]=direction if out["valid"] else "NO_TRADE"
    out["setup_key"]=f"{direction}:{ms.get('strategy','NONE')}:{index}"
    if not out["valid"] and not reasons:out["rejection_reasons"]=["TRADE_LEVELS_INVALID"]
    return out


def calculate_indicators(df):
    return _indicator_context(df)
