"""Deterministic price-pattern evidence engine.

Patterns are evidence only. A live signal requires a confirmed M5 setup plus
aligned M15/H1 context in live_scanner.py. No pattern is treated as guaranteed.

M5 trigger policy:
- One confirmed directional pattern is sufficient.
- Any confirmed pattern in the opposite direction blocks the M5 setup.
- No weighted confluence score is used to decide direction.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _atr(df, period=14):
    h,l,c=df.high,df.low,df.close
    tr=pd.concat([(h-l).abs(),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(period,min_periods=period).mean()

def _body(r): return abs(float(r.close)-float(r.open))
def _rng(r): return max(float(r.high)-float(r.low),1e-12)

def _pivots(df, left=2, right=2):
    hi=df.high.to_numpy(); lo=df.low.to_numpy(); highs=[]; lows=[]
    for j in range(left,len(df)-right):
        if hi[j]>=max(hi[j-left:j]) and hi[j]>max(hi[j+1:j+right+1]): highs.append((j,float(hi[j])))
        if lo[j]<=min(lo[j-left:j]) and lo[j]<min(lo[j+1:j+right+1]): lows.append((j,float(lo[j])))
    return highs,lows

def detect_price_action(df,i):
    if i<3:return []
    a,b=df.iloc[i-1],df.iloc[i]; out=[]; ba=_body(a); bb=_body(b)
    if b.close>b.open and a.close<a.open and b.open<=a.close and b.close>=a.open:
        out.append({"name":"Bullish Engulfing","category":"PRICE_ACTION","direction":"BUY","confirmed":True})
    if b.close<b.open and a.close>a.open and b.open>=a.close and b.close<=a.open:
        out.append({"name":"Bearish Engulfing","category":"PRICE_ACTION","direction":"SELL","confirmed":True})
    upper=float(b.high)-max(float(b.open),float(b.close)); lower=min(float(b.open),float(b.close))-float(b.low)
    if lower>=max(bb*2,_rng(b)*.45) and b.close>b.open:
        out.append({"name":"Hammer / Rejection","category":"PRICE_ACTION","direction":"BUY","confirmed":True})
    if upper>=max(bb*2,_rng(b)*.45) and b.close<b.open:
        out.append({"name":"Shooting Star / Rejection","category":"PRICE_ACTION","direction":"SELL","confirmed":True})
    if float(b.high)<=float(a.high) and float(b.low)>=float(a.low):
        out.append({"name":"Inside Bar","category":"PRICE_ACTION","direction":"NEUTRAL","confirmed":True})
    return out

def detect_chart_patterns(df,i,lookback=80):
    if i<25:return []
    s=df.iloc[max(0,i-lookback):i+1].copy(); atr_series=_atr(s); atr=float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else float(np.mean((s.high-s.low).tail(14)))
    if atr<=0:return []
    highs,lows=_pivots(s); out=[]
    if len(lows)>=2:
        l1,l2=lows[-2],lows[-1]; tol=atr*1.5; neck=float(s.high.iloc[l1[0]+1:l2[0]+1].max()) if l2[0]>l1[0]+1 else float(s.high.max())
        if abs(l1[1]-l2[1])<=tol and float(s.close.iloc[-1])>neck:
            out.append({"name":"Double Bottom","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
    if len(highs)>=2:
        h1,h2=highs[-2],highs[-1]; tol=atr*1.5; neck=float(s.low.iloc[h1[0]+1:h2[0]+1].min()) if h2[0]>h1[0]+1 else float(s.low.min())
        if abs(h1[1]-h2[1])<=tol and float(s.close.iloc[-1])<neck:
            out.append({"name":"Double Top","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
    if len(lows)>=3:
        a,b,c=lows[-3:]; neck=float(s.high.iloc[a[0]+1:c[0]+1].max())
        if max(abs(a[1]-b[1]),abs(b[1]-c[1]))<=atr*2 and float(s.close.iloc[-1])>neck:
            out.append({"name":"Triple Bottom","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
    if len(highs)>=3:
        a,b,c=highs[-3:]; neck=float(s.low.iloc[a[0]+1:c[0]+1].min())
        if max(abs(a[1]-b[1]),abs(b[1]-c[1]))<=atr*2 and float(s.close.iloc[-1])<neck:
            out.append({"name":"Triple Top","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
    if len(highs)>=3 and len(lows)>=2:
        hs=highs[-3:]; ls=lows[-2:]
        if hs[1][1]>hs[0][1] and hs[1][1]>hs[2][1] and abs(hs[0][1]-hs[2][1])<=atr*2:
            neck=float(np.mean([ls[-2][1],ls[-1][1]]))
            if float(s.close.iloc[-1])<neck: out.append({"name":"Head and Shoulders","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
    if len(lows)>=3 and len(highs)>=2:
        ls=lows[-3:]; hs=highs[-2:]
        if ls[1][1]<ls[0][1] and ls[1][1]<ls[2][1] and abs(ls[0][1]-ls[2][1])<=atr*2:
            neck=float(np.mean([hs[-2][1],hs[-1][1]]))
            if float(s.close.iloc[-1])>neck: out.append({"name":"Inverted Head and Shoulders","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
    recent=s.tail(30); x=np.arange(len(recent))
    if len(recent)>=15:
        hslope=np.polyfit(x,recent.high.to_numpy(),1)[0]; lslope=np.polyfit(x,recent.low.to_numpy(),1)[0]
        if hslope<0 and lslope<0 and lslope>hslope and float(s.close.iloc[-1])>float(recent.high.iloc[:-1].max()): out.append({"name":"Falling Wedge","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
        if hslope>0 and lslope>0 and hslope>lslope and float(s.close.iloc[-1])<float(recent.low.iloc[:-1].min()): out.append({"name":"Rising Wedge","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
        if hslope<0 and lslope>0:
            if float(s.close.iloc[-1])>float(recent.high.iloc[:-1].max()): out.append({"name":"Bullish Symmetrical Triangle","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
            elif float(s.close.iloc[-1])<float(recent.low.iloc[:-1].min()): out.append({"name":"Bearish Symmetrical Triangle","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
        hflat=abs(hslope)<=atr/20; lflat=abs(lslope)<=atr/20
        if hflat and lslope>0 and float(s.close.iloc[-1])>float(recent.high.iloc[:-1].max()): out.append({"name":"Ascending Triangle","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
        if lflat and hslope<0 and float(s.close.iloc[-1])<float(recent.low.iloc[:-1].min()): out.append({"name":"Descending Triangle","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
        pre=s.iloc[-25:-10]; flag=s.iloc[-10:-1]
        if len(pre)>=8 and len(flag)>=5:
            impulse=float(pre.close.iloc[-1]-pre.close.iloc[0]); fhs=np.polyfit(np.arange(len(flag)),flag.high,1)[0]; fls=np.polyfit(np.arange(len(flag)),flag.low,1)[0]
            if impulse>atr*4 and fhs<0 and fls<0 and float(s.close.iloc[-1])>float(flag.high.max()): out.append({"name":"Bullish Flag","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
            if impulse<-atr*4 and fhs>0 and fls>0 and float(s.close.iloc[-1])<float(flag.low.min()): out.append({"name":"Bearish Flag","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
    mid=s.tail(40); third=max(len(mid)//3,5); left=float(mid.close.iloc[:third].mean()); center=float(mid.close.iloc[third:2*third].mean()); right=float(mid.close.iloc[-third:].mean())
    if center<left-atr and center<right-atr and float(mid.close.iloc[-1])>float(mid.high.iloc[:2*third].max()): out.append({"name":"Rounding Bottom","category":"CHART_PATTERN","direction":"BUY","confirmed":True})
    if center>left+atr and center>right+atr and float(mid.close.iloc[-1])<float(mid.low.iloc[:2*third].min()): out.append({"name":"Rounding Top","category":"CHART_PATTERN","direction":"SELL","confirmed":True})
    return out

def detect_smc(df,i,swing=3):
    if i<swing*2+2:return []
    out=[]; prev=df.iloc[i-2*swing:i-swing]; recent=df.iloc[i-swing:i]; row=df.iloc[i]
    hp=float(prev.high.max()); lp=float(prev.low.min()); hr=float(recent.high.max()); lr=float(recent.low.min())
    if float(row.high)>hp and float(row.close)<hp: out.append({"name":"Liquidity Sweep High","category":"SMC_ICT","direction":"SELL","confirmed":True})
    if float(row.low)<lp and float(row.close)>lp: out.append({"name":"Liquidity Sweep Low","category":"SMC_ICT","direction":"BUY","confirmed":True})
    if float(row.close)>hr: out.append({"name":"Bullish BOS / MSS","category":"SMC_ICT","direction":"BUY","confirmed":True})
    if float(row.close)<lr: out.append({"name":"Bearish BOS / MSS","category":"SMC_ICT","direction":"SELL","confirmed":True})
    if i>=2:
        a,b,c=df.iloc[i-2],df.iloc[i-1],df.iloc[i]
        if float(a.high)<float(c.low): out.append({"name":"Bullish FVG","category":"SMC_ICT","direction":"BUY","confirmed":True})
        if float(a.low)>float(c.high): out.append({"name":"Bearish FVG","category":"SMC_ICT","direction":"SELL","confirmed":True})
    return out

def detect_supply_demand(df,i):
    if i<15:return []
    atr=_atr(df).iloc[i]
    if pd.isna(atr) or atr<=0:return []
    a,b=df.iloc[i-1],df.iloc[i]; impulse=abs(float(b.close)-float(a.close)); out=[]
    if impulse>=float(atr)*1.5: out.append({"name":"Demand Impulse / Base Candidate" if b.close>b.open else "Supply Impulse / Base Candidate","category":"SUPPLY_DEMAND","direction":"BUY" if b.close>b.open else "SELL","confirmed":True})
    return out

def detect_trend_breakout(df,i):
    if i<55:return []
    c=df.close; e20=c.ewm(span=20,adjust=False).mean(); e50=c.ewm(span=50,adjust=False).mean(); row=df.iloc[i]; out=[]
    if e20.iloc[i]>e50.iloc[i] and c.iloc[i]>e20.iloc[i]: out.append({"name":"Uptrend / EMA20-50 Alignment","category":"TREND_BREAKOUT","direction":"BUY","confirmed":True})
    if e20.iloc[i]<e50.iloc[i] and c.iloc[i]<e20.iloc[i]: out.append({"name":"Downtrend / EMA20-50 Alignment","category":"TREND_BREAKOUT","direction":"SELL","confirmed":True})
    ph=float(df.high.iloc[i-20:i].max()); pl=float(df.low.iloc[i-20:i].min())
    if float(row.close)>ph: out.append({"name":"20-Bar Breakout","category":"TREND_BREAKOUT","direction":"BUY","confirmed":True})
    if float(row.close)<pl: out.append({"name":"20-Bar Breakdown","category":"TREND_BREAKOUT","direction":"SELL","confirmed":True})
    return out

def detect_fibonacci(df,i):
    if i<30:return []
    s=df.iloc[i-30:i+1]; hi=float(s.high.max()); lo=float(s.low.min()); px=float(df.close.iloc[i]); span=hi-lo
    if span<=0:return []
    for n,r in (("38.2",.382),("50.0",.5),("61.8",.618)):
        level=hi-span*r
        if abs(px-level)<=span*.012:return [{"name":f"Fibonacci {n}% Zone","category":"FIBONACCI_HARMONIC","direction":"BUY" if px<(hi+lo)/2 else "SELL","confirmed":True}]
    return []

def detect_indicators_session(df,i):
    if i<30:return []
    d=df.close.diff(); gain=d.clip(lower=0).rolling(14).mean(); loss=(-d.clip(upper=0)).rolling(14).mean(); r=100-(100/(1+gain/loss.replace(0,np.nan))); v=float(r.iloc[i]) if pd.notna(r.iloc[i]) else 50
    if v<30:return [{"name":"RSI Oversold","category":"INDICATOR_SESSION","direction":"BUY","confirmed":True}]
    if v>70:return [{"name":"RSI Overbought","category":"INDICATOR_SESSION","direction":"SELL","confirmed":True}]
    return []

def detect_all(df,i):
    groups={"PRICE_ACTION":detect_price_action(df,i),"CHART_PATTERN":detect_chart_patterns(df,i),"SMC_ICT":detect_smc(df,i),"SUPPLY_DEMAND":detect_supply_demand(df,i),"TREND_BREAKOUT":detect_trend_breakout(df,i),"FIBONACCI_HARMONIC":detect_fibonacci(df,i),"INDICATOR_SESSION":detect_indicators_session(df,i)}
    patterns=[p for vals in groups.values() for p in vals]
    return {"groups":groups,"patterns":patterns,"pattern_count":len(patterns)}

def confluence(patterns,minimum=1):
    """Compatibility summary only; never used as a weighted trigger.

    Direction is determined strictly by the presence of confirmed directional
    evidence. A single clean BUY or SELL pattern is enough. If both directions
    are present, the result is NO_TRADE because the M5 evidence is contested.
    The returned score is a plain evidence count, not a weighted score.
    """
    buy=[p for p in patterns if p.get("direction")=="BUY"]
    sell=[p for p in patterns if p.get("direction")=="SELL"]
    bc={p.get("category") for p in buy if p.get("category")}
    sc={p.get("category") for p in sell if p.get("category")}
    if buy and not sell:
        direction="BUY"
    elif sell and not buy:
        direction="SELL"
    else:
        direction="NO_TRADE"
    score=len(buy) if direction=="BUY" else len(sell) if direction=="SELL" else max(len(buy),len(sell))
    return {
        "signal": direction,
        "score": score,
        "buy_evidence": buy,
        "sell_evidence": sell,
        "buy_categories": sorted(bc),
        "sell_categories": sorted(sc),
        "minimum_confluence": 1,
        "weighted": False,
    }
