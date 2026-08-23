from __future__ import annotations
import math
import pandas as pd


def num(v, default=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else default
    except (TypeError, ValueError): return default


def candle_metrics(row):
    o,h,l,c=map(num,(row.open,row.high,row.low,row.close)); rng=max(h-l,1e-12); body=abs(c-o)
    return {"open":o,"high":h,"low":l,"close":c,"body":body,"range":rng,"body_ratio":body/rng,"bull":c>o,"bear":c<o,"upper_wick":h-max(o,c),"lower_wick":min(o,c)-l}


def atr14(df):
    h=pd.to_numeric(df.high,errors="coerce"); l=pd.to_numeric(df.low,errors="coerce"); c=pd.to_numeric(df.close,errors="coerce")
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(14,min_periods=14).mean()


def ema(df, span): return pd.to_numeric(df.close,errors="coerce").ewm(span=span,adjust=False).mean()


def momentum_move(df, bars=5):
    if len(df)<=bars:return 0.0
    return num(df.close.iloc[-1])-num(df.close.iloc[-1-bars])


def structure(df, lookback=50):
    x=df.tail(lookback).reset_index(drop=True); highs=[]; lows=[]
    for i in range(2,max(2,len(x)-2)):
        if num(x.high.iloc[i])>=max(num(v) for v in x.high.iloc[i-2:i+3]): highs.append(num(x.high.iloc[i]))
        if num(x.low.iloc[i])<=min(num(v) for v in x.low.iloc[i-2:i+3]): lows.append(num(x.low.iloc[i]))
    hh=len(highs)>=2 and highs[-1]>highs[-2]; hl=len(lows)>=2 and lows[-1]>lows[-2]
    lh=len(highs)>=2 and highs[-1]<highs[-2]; ll=len(lows)>=2 and lows[-1]<lows[-2]
    return {"bias":"BUY" if hh and hl else "SELL" if lh and ll else "NEUTRAL","support":lows[-1] if lows else num(x.low.min()),"resistance":highs[-1] if highs else num(x.high.max()),"hh":hh,"hl":hl,"lh":lh,"ll":ll}


def breakout(df, direction, lookback=20):
    x=df.tail(lookback+1).reset_index(drop=True); last=candle_metrics(x.iloc[-1]); p=x.iloc[:-1].tail(lookback)
    level=num(p.high.max()) if direction=="BUY" else num(p.low.min())
    broken=last["close"]>level if direction=="BUY" else last["close"]<level
    return broken, level, last
