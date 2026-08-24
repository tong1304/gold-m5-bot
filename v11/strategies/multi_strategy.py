from __future__ import annotations
import pandas as pd
from ..contracts import StrategyResult
from ..common import num, ema, atr14, candle_metrics

STRATEGIES=("TREND_PULLBACK","BREAKOUT_RETEST","LIQUIDITY_SWEEP","VWAP_MOMENTUM_PULLBACK","OPENING_RANGE_BREAKOUT")
MIN_BODY_RATIO=.45
MAX_STRUCTURE_BARS=100

def _x(m5): return m5.tail(MAX_STRUCTURE_BARS).reset_index(drop=True).copy()
def _atr(x):
    a=atr14(x).dropna()
    return num(a.iloc[-1]) if len(a) else num((x.high-x.low).tail(14).mean(),1e-12)
def _pivot_points(x):
    highs=[]; lows=[]
    for i in range(2,len(x)-2):
        h=num(x.high.iloc[i]); l=num(x.low.iloc[i])
        if h>=max(num(v) for v in x.high.iloc[i-2:i+3]): highs.append((i,h))
        if l<=min(num(v) for v in x.low.iloc[i-2:i+3]): lows.append((i,l))
    return highs,lows
def _confirm(last,prev,direction):
    if direction=="BUY": return last["bull"] and last["body_ratio"]>=MIN_BODY_RATIO and last["close"]>prev["high"]
    return last["bear"] and last["body_ratio"]>=MIN_BODY_RATIO and last["close"]<prev["low"]

def trend_pullback(m5,direction,ctx):
    x=_x(m5); a=_atr(x); last=candle_metrics(x.iloc[-1]); prev=candle_metrics(x.iloc[-2]); e20=ema(x,20); e50=ema(x,50); td=(ctx.get("m15") or {}).get("direction","NEUTRAL")
    if td!=direction:return StrategyResult.fail("TREND_PULLBACK",direction,["M15_TREND_MISMATCH"])
    c=last["close"]; trend=(c>e20.iloc[-1]>e50.iloc[-1]) if direction=="BUY" else (c<e20.iloc[-1]<e50.iloc[-1])
    highs,lows=_pivot_points(x)
    if direction=="BUY":
        anchor=lows[-1][1] if lows else num(x.low.min()); touched=x.low.tail(8).min()<=max(float(e20.tail(8).max()),anchor)+.25*a; protected=anchor
        future=[v for _,v in highs if v>c]; room=(max(future)-c) if future else a*3
    else:
        anchor=highs[-1][1] if highs else num(x.high.max()); touched=x.high.tail(8).max()>=min(float(e20.tail(8).min()),anchor)-.25*a; protected=anchor
        future=[v for _,v in lows if v<c]; room=(c-min(future)) if future else a*3
    if not trend:return StrategyResult.fail("TREND_PULLBACK",direction,["EMA20_EMA50_TREND_FAILED"])
    if not touched:return StrategyResult.fail("TREND_PULLBACK",direction,["PULLBACK_NOT_IN_SAFE_ZONE"])
    if not _confirm(last,prev,direction):return StrategyResult.fail("TREND_PULLBACK",direction,["CANDLE_CONFIRMATION_FAILED"])
    if room<2*a:return StrategyResult.fail("TREND_PULLBACK",direction,["OPPOSING_STRUCTURE_TOO_CLOSE"])
    return StrategyResult.pass_("TREND_PULLBACK",direction,{"support":protected if direction=="BUY" else None,"resistance":protected if direction=="SELL" else None,"ema20":num(e20.iloc[-1]),"ema50":num(e50.iloc[-1]),"atr":a,"setup_anchor":protected},84,0)

def breakout_retest(m5,direction,ctx):
    x=_x(m5); a=_atr(x); last=candle_metrics(x.iloc[-1]); highs,lows=_pivot_points(x); level=None; breakout_i=None
    levels=[v for _,v in (highs if direction=="BUY" else lows)]
    for lv in reversed(levels):
        if sum(abs(v-lv)<=.30*a for v in levels)>=2: level=lv; break
    if level is None:return StrategyResult.fail("BREAKOUT_RETEST",direction,["NO_REPEATED_STRUCTURE_LEVEL"])
    for i in range(len(x)-2,0,-1):
        cm=candle_metrics(x.iloc[i]); broke=(cm["close"]>level and cm["bull"]) if direction=="BUY" else (cm["close"]<level and cm["bear"])
        if broke: breakout_i=i; break
    if breakout_i is None:return StrategyResult.fail("BREAKOUT_RETEST",direction,["NO_CONFIRMED_BREAKOUT"])
    retest=x.iloc[breakout_i+1:]
    touched=(num(retest.low.min())<=level+.25*a and last["close"]>level) if direction=="BUY" else (num(retest.high.max())>=level-.25*a and last["close"]<level)
    if not touched:return StrategyResult.fail("BREAKOUT_RETEST",direction,["RETEST_ZONE_NOT_REACHED"])
    if not _confirm(last,candle_metrics(x.iloc[-2]),direction):return StrategyResult.fail("BREAKOUT_RETEST",direction,["RETEST_CONFIRMATION_FAILED"])
    return StrategyResult.pass_("BREAKOUT_RETEST",direction,{"breakout_level":level,"support":level if direction=="BUY" else None,"resistance":level if direction=="SELL" else None,"retest_low":num(retest.low.min()),"retest_high":num(retest.high.max()),"atr":a,"setup_anchor":level},86,0)

def liquidity_sweep(m5,direction,ctx):
    x=_x(m5); a=_atr(x); highs,lows=_pivot_points(x)
    if direction=="BUY":
        if not lows:return StrategyResult.fail("LIQUIDITY_SWEEP",direction,["NO_LIQUIDITY_LOW"])
        level=lows[-1][1]; sweep=candle_metrics(x.iloc[-2]); confirm=candle_metrics(x.iloc[-1]); ok=sweep["low"]<level and sweep["close"]>level and sweep["lower_wick"]>=max(sweep["body"],a*.15) and confirm["bull"] and confirm["close"]>sweep["high"]
        evidence={"sweep_level":level,"support":sweep["low"]-.10*a,"atr":a,"setup_anchor":level}
    else:
        if not highs:return StrategyResult.fail("LIQUIDITY_SWEEP",direction,["NO_LIQUIDITY_HIGH"])
        level=highs[-1][1]; sweep=candle_metrics(x.iloc[-2]); confirm=candle_metrics(x.iloc[-1]); ok=sweep["high"]>level and sweep["close"]<level and sweep["upper_wick"]>=max(sweep["body"],a*.15) and confirm["bear"] and confirm["close"]<sweep["low"]
        evidence={"sweep_level":level,"resistance":sweep["high"]+.10*a,"atr":a,"setup_anchor":level}
    return StrategyResult.pass_("LIQUIDITY_SWEEP",direction,evidence,90,0) if ok else StrategyResult.fail("LIQUIDITY_SWEEP",direction,["SWEEP_RECLAIM_NOT_CONFIRMED"])

def _session_vwap(x):
    if "datetime" not in x:return None
    ts=pd.to_datetime(x.datetime,utc=True,errors="coerce"); typical=(x.high+x.low+x.close)/3; vol=pd.to_numeric(x.get("volume",pd.Series(1.0,index=x.index)),errors="coerce").fillna(1).clip(lower=1e-9)
    if ts.notna().any():
        d=ts.dt.date; return (typical*vol).groupby(d).cumsum()/vol.groupby(d).cumsum()
    return (typical*vol).cumsum()/vol.cumsum()

def vwap_momentum_pullback(m5,direction,ctx):
    x=_x(m5); a=_atr(x); vw=_session_vwap(x)
    if vw is None or len(vw)==0:return StrategyResult.fail("VWAP_MOMENTUM_PULLBACK",direction,["VWAP_UNAVAILABLE"])
    last=candle_metrics(x.iloc[-1]); prev=candle_metrics(x.iloc[-2]); v=float(vw.iloc[-1]); c=last["close"]; slope=float(vw.iloc[-1]-vw.iloc[max(0,len(vw)-4)]); momentum=abs(c-num(x.close.iloc[max(0,len(x)-6)]))/max(a,1e-12)
    if direction=="BUY": ok=c>v and slope>0 and momentum>=1.0 and prev["low"]<=v+.30*a and last["bull"] and last["body_ratio"]>=MIN_BODY_RATIO and c>prev["high"]; support=prev["low"]-.10*a
    else: ok=c<v and slope<0 and momentum>=1.0 and prev["high"]>=v-.30*a and last["bear"] and last["body_ratio"]>=MIN_BODY_RATIO and c<prev["low"]; support=prev["high"]+.10*a
    if not ok:return StrategyResult.fail("VWAP_MOMENTUM_PULLBACK",direction,["VWAP_MOMENTUM_PULLBACK_NOT_CONFIRMED"])
    return StrategyResult.pass_("VWAP_MOMENTUM_PULLBACK",direction,{"vwap":v,"vwap_slope":slope,"momentum_atr":momentum,"support":support if direction=="BUY" else None,"resistance":support if direction=="SELL" else None,"atr":a,"setup_anchor":v},82,0)

def opening_range_breakout(m5,direction,ctx):
    x=_x(m5); a=_atr(x)
    if "datetime" not in x:return StrategyResult.fail("OPENING_RANGE_BREAKOUT",direction,["DATETIME_REQUIRED"])
    ts=pd.to_datetime(x.datetime,utc=True,errors="coerce"); latest=ts.iloc[-1]; day=x.loc[ts.dt.date==latest.date()].reset_index(drop=True)
    if len(day)<2:return StrategyResult.fail("OPENING_RANGE_BREAKOUT",direction,["OPENING_RANGE_NOT_READY"])
    window=max(10,int(ctx.get("opening_range_minutes",30))); start=pd.Timestamp(day.datetime.iloc[0]); end=start+pd.Timedelta(minutes=window); orb=day[pd.to_datetime(day.datetime,utc=True)<=end]
    if len(orb)<2 or len(day)<=len(orb):return StrategyResult.fail("OPENING_RANGE_BREAKOUT",direction,["OPENING_RANGE_NOT_READY"])
    rh=num(orb.high.max()); rl=num(orb.low.min()); last=candle_metrics(day.iloc[-1]); prior=candle_metrics(day.iloc[-2]); width=rh-rl
    if width<=0 or width>2.0*a:return StrategyResult.fail("OPENING_RANGE_BREAKOUT",direction,["OPENING_RANGE_VOLATILITY_UNSUITABLE"])
    if direction=="BUY": ok=last["close"]>rh and last["bull"] and last["body_ratio"]>=MIN_BODY_RATIO and prior["low"]<=rh+.30*a; support=rh-.10*a
    else: ok=last["close"]<rl and last["bear"] and last["body_ratio"]>=MIN_BODY_RATIO and prior["high"]>=rl-.30*a; support=rl+.10*a
    if not ok:return StrategyResult.fail("OPENING_RANGE_BREAKOUT",direction,["OPENING_RANGE_BREAKOUT_NOT_CONFIRMED"])
    return StrategyResult.pass_("OPENING_RANGE_BREAKOUT",direction,{"opening_range_high":rh,"opening_range_low":rl,"support":support if direction=="BUY" else None,"resistance":support if direction=="SELL" else None,"atr":a,"setup_anchor":rh if direction=="BUY" else rl},80,0)

REGISTRY={"TREND_PULLBACK":trend_pullback,"BREAKOUT_RETEST":breakout_retest,"LIQUIDITY_SWEEP":liquidity_sweep,"VWAP_MOMENTUM_PULLBACK":vwap_momentum_pullback,"OPENING_RANGE_BREAKOUT":opening_range_breakout}
