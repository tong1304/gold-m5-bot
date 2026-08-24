from __future__ import annotations
import pandas as pd
from ..contracts import StrategyResult
from ..common import num, ema, atr14

STRATEGIES=("TREND_PULLBACK","LIQUIDITY_SWEEP","MSS_PULLBACK","BREAKOUT_RETEST","OPENING_RANGE_BREAKOUT","VWAP_MEAN_REVERSION","SWEEP_MSS_FVG")
def _x(m5,n=80): return m5.tail(n).reset_index(drop=True).copy()
def _atr(x):
    try:return max(num(atr14(x).iloc[-1]),1e-12)
    except Exception:return max(num((x.high-x.low).tail(14).mean()),1e-12)
def _candle(x,i=-1):
    r=x.iloc[i]; o,h,l,c=map(float,(r.open,r.high,r.low,r.close)); rng=max(h-l,1e-12); return o,h,l,c,rng,(c-o)/rng
def _swing_levels(x,lookback=20):
    z=x.iloc[:-2].tail(lookback); return num(z.low.min()),num(z.high.max())
def _pass(name,direction,evidence,quality=70,freshness=0): return StrategyResult.pass_(name,direction,evidence,quality,freshness)
def _fail(name,direction,reason): return StrategyResult.fail(name,direction,[reason])

def trend_pullback(m5,direction,ctx):
    x=_x(m5,60)
    if len(x)<30:return _fail("TREND_PULLBACK",direction,"INSUFFICIENT_M5_CONTEXT")
    td=(ctx.get("m15") or {}).get("direction","NEUTRAL"); e20=ema(x,20); e50=ema(x,50); c=num(x.close.iloc[-1]); a=_atr(x)
    if direction!=td:return _fail("TREND_PULLBACK",direction,"M15_DIRECTION_MISMATCH")
    if direction=="BUY": trend=c>e20.iloc[-1]>e50.iloc[-1]; touched=x.low.tail(5).min()<=e20.tail(5).max()+.25*a; confirm=_candle(x)[5]>.20; support=num(x.low.tail(8).min())
    else: trend=c<e20.iloc[-1]<e50.iloc[-1]; touched=x.high.tail(5).max()>=e20.tail(5).min()-.25*a; confirm=_candle(x)[5]<-.20; support=num(x.high.tail(8).max())
    return _pass("TREND_PULLBACK",direction,{"support":support,"atr":a,"ema20":num(e20.iloc[-1]),"ema50":num(e50.iloc[-1])},82,0) if trend and touched and confirm else _fail("TREND_PULLBACK",direction,"PULLBACK_CONFIRMATION_NOT_FOUND")

def liquidity_sweep(m5,direction,ctx):
    x=_x(m5,40)
    if len(x)<25:return _fail("LIQUIDITY_SWEEP",direction,"INSUFFICIENT_M5_CONTEXT")
    a=_atr(x); o,h,l,c,rng,body=_candle(x); low,high=_swing_levels(x,20)
    if direction=="BUY": ok=l<low and c>low and body>.20; support=l-.10*a
    else: ok=h>high and c<high and body<-.20; support=h+.10*a
    return _pass("LIQUIDITY_SWEEP",direction,{"support":support,"sweep_level":low if direction=="BUY" else high,"atr":a},86,0) if ok else _fail("LIQUIDITY_SWEEP",direction,"NO_LIQUIDITY_SWEEP")

def mss_pullback(m5,direction,ctx):
    x=_x(m5,45)
    if len(x)<30:return _fail("MSS_PULLBACK",direction,"INSUFFICIENT_M5_CONTEXT")
    a=_atr(x); prior=x.iloc[-12:-3]; last=x.iloc[-3:]; ph=num(prior.high.max()); pl=num(prior.low.min()); c=num(x.close.iloc[-1]); o,h,l,cc,rng,body=_candle(x)
    if direction=="BUY": broken=c>ph; pullback=num(last.low.min())>pl; support=num(last.low.min())-.10*a; displacement=body>.25
    else: broken=c<pl; pullback=num(last.high.max())<ph; support=num(last.high.max())+.10*a; displacement=body<-.25
    return _pass("MSS_PULLBACK",direction,{"support":support,"broken_level":ph if direction=="BUY" else pl,"atr":a},84,0) if broken and pullback and displacement else _fail("MSS_PULLBACK",direction,"MSS_PULLBACK_NOT_CONFIRMED")

def breakout_retest(m5,direction,ctx):
    x=_x(m5,45)
    if len(x)<25:return _fail("BREAKOUT_RETEST",direction,"INSUFFICIENT_M5_CONTEXT")
    a=_atr(x); lo,hi=_swing_levels(x,18); prev=x.iloc[-4:-1]; c=num(x.close.iloc[-1]); o,h,l,cc,rng,body=_candle(x)
    if direction=="BUY": level=hi; broke=num(prev.close.max())>level; retest=l<=level+.20*a and c>level; support=min(l,level-.10*a); confirm=body>.10
    else: level=lo; broke=num(prev.close.min())<level; retest=h>=level-.20*a and c<level; support=max(h,level+.10*a); confirm=body<-.10
    return _pass("BREAKOUT_RETEST",direction,{"support":support,"breakout_level":level,"atr":a},80,0) if broke and retest and confirm else _fail("BREAKOUT_RETEST",direction,"BREAKOUT_RETEST_NOT_CONFIRMED")

def opening_range_breakout(m5,direction,ctx):
    x=_x(m5,100)
    if len(x)<20:return _fail("OPENING_RANGE_BREAKOUT",direction,"INSUFFICIENT_M5_CONTEXT")
    ts=pd.to_datetime(x["datetime"],errors="coerce",utc=True) if "datetime" in x else None; dayx=x
    if ts is not None and ts.notna().any(): dayx=x.loc[ts.dt.date==ts.iloc[-1].date()].reset_index(drop=True)
    if len(dayx)<8:return _fail("OPENING_RANGE_BREAKOUT",direction,"OPENING_RANGE_NOT_READY")
    orb=dayx.iloc[:6]; rh=num(orb.high.max()); rl=num(orb.low.min()); c=num(dayx.close.iloc[-1]); a=_atr(x); o,h,l,cc,rng,body=_candle(x)
    if direction=="BUY": ok=c>rh and body>.15; support=rh-.10*a
    else: ok=c<rl and body<-.15; support=rl+.10*a
    return _pass("OPENING_RANGE_BREAKOUT",direction,{"support":support,"opening_range_high":rh,"opening_range_low":rl,"atr":a},78,0) if ok else _fail("OPENING_RANGE_BREAKOUT",direction,"OPENING_RANGE_BREAK_NOT_CONFIRMED")

def vwap_mean_reversion(m5,direction,ctx):
    x=_x(m5,80)
    if len(x)<30:return _fail("VWAP_MEAN_REVERSION",direction,"INSUFFICIENT_M5_CONTEXT")
    if (ctx.get("m15") or {}).get("direction","NEUTRAL")!="NEUTRAL":return _fail("VWAP_MEAN_REVERSION",direction,"TREND_REGIME_NOT_RANGE")
    typical=(x.high+x.low+x.close)/3; vol=pd.to_numeric(x.get("volume",pd.Series(1.0,index=x.index)),errors="coerce").fillna(1.0).clip(lower=1e-9); ts=pd.to_datetime(x["datetime"],errors="coerce",utc=True) if "datetime" in x else None
    if ts is not None and ts.notna().any(): vwap=(typical*vol).groupby(ts.dt.date).cumsum()/vol.groupby(ts.dt.date).cumsum()
    else:vwap=(typical*vol).cumsum()/vol.cumsum()
    vw=num(vwap.iloc[-1]); c=num(x.close.iloc[-1]); a=_atr(x); o,h,l,cc,rng,body=_candle(x); distance=abs(c-vw)/a
    if direction=="BUY": ok=distance>=1.80 and c<vw-1.80*a and body>.10; support=l-.10*a
    else: ok=distance>=1.80 and c>vw+1.80*a and body<-.10; support=h+.10*a
    return _pass("VWAP_MEAN_REVERSION",direction,{"support":support,"vwap":vw,"target_price":vw,"atr":a,"distance_atr":distance},76,0) if ok else _fail("VWAP_MEAN_REVERSION",direction,"VWAP_REVERSION_NOT_CONFIRMED")

def sweep_mss_fvg(m5,direction,ctx):
    x=_x(m5,50)
    if len(x)<30:return _fail("SWEEP_MSS_FVG",direction,"INSUFFICIENT_M5_CONTEXT")
    a=_atr(x); low,high=_swing_levels(x,20); r1=x.iloc[-3]; r2=x.iloc[-2]; r3=x.iloc[-1]; c=float(r3.close); o2,h2,l2,c2=map(float,(r2.open,r2.high,r2.low,r2.close))
    if direction=="BUY": sweep=float(r1.low)<low and float(r1.close)>low; displacement=c2>o2 and c2-o2>.45*a and float(r2.low)>float(r1.low); fvg=float(r3.low)>float(r1.high); retest=float(r3.low)<=float(r1.high)+.20*a and c>float(r1.high); support=float(r1.low)-.10*a
    else: sweep=float(r1.high)>high and float(r1.close)<high; displacement=c2<o2 and o2-c2>.45*a and float(r2.high)<float(r1.high); fvg=float(r3.high)<float(r1.low); retest=float(r3.high)>=float(r1.low)-.20*a and c<float(r1.low); support=float(r1.high)+.10*a
    return _pass("SWEEP_MSS_FVG",direction,{"support":support,"fvg_high":float(r1.high),"fvg_low":float(r1.low),"atr":a},90,0) if sweep and displacement and fvg and retest else _fail("SWEEP_MSS_FVG",direction,"SWEEP_MSS_FVG_NOT_CONFIRMED")

REGISTRY={"TREND_PULLBACK":trend_pullback,"LIQUIDITY_SWEEP":liquidity_sweep,"MSS_PULLBACK":mss_pullback,"BREAKOUT_RETEST":breakout_retest,"OPENING_RANGE_BREAKOUT":opening_range_breakout,"VWAP_MEAN_REVERSION":vwap_mean_reversion,"SWEEP_MSS_FVG":sweep_mss_fvg}
