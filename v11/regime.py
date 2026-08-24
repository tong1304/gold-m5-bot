from __future__ import annotations

import math
import pandas as pd
from .common import num, ema, atr14, structure

TREND_ENGINES = {"E1", "E2", "E3", "E4", "E5"}
RANGE_ENGINES = {"E6", "E7", "E8"}
TRANSITION_ENGINES = {"E3", "E4", "E7"}


def allowed_engines_for_regime(regime: str) -> set[str]:
    regime = str(regime).upper()
    if regime == "TREND": return set(TREND_ENGINES)
    if regime == "RANGE": return set(RANGE_ENGINES)
    if regime == "TRANSITION": return set(TRANSITION_ENGINES)
    return set()


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _atr(frame):
    value = _finite(atr14(frame).iloc[-1]) if len(frame) >= 14 else None
    if value is None or value <= 0: value = _finite((frame.high-frame.low).tail(14).mean())
    return value if value is not None and value > 0 else None


def _adx(frame, period=14):
    h=pd.to_numeric(frame.high,errors="coerce"); l=pd.to_numeric(frame.low,errors="coerce"); c=pd.to_numeric(frame.close,errors="coerce")
    up=h.diff(); down=-l.diff(); plus_dm=up.where((up>down)&(up>0),0.0); minus_dm=down.where((down>up)&(down>0),0.0)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    plus=100*plus_dm.ewm(alpha=1/period,adjust=False,min_periods=period).mean()/atr.replace(0,pd.NA)
    minus=100*minus_dm.ewm(alpha=1/period,adjust=False,min_periods=period).mean()/atr.replace(0,pd.NA)
    dx=(100*(plus-minus).abs()/(plus+minus).replace(0,pd.NA)).fillna(0)
    adx=dx.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    return _finite(adx.iloc[-1]),_finite(plus.iloc[-1]),_finite(minus.iloc[-1])


def _vwap(frame):
    typical=(pd.to_numeric(frame.high,errors="coerce")+pd.to_numeric(frame.low,errors="coerce")+pd.to_numeric(frame.close,errors="coerce"))/3
    volume=pd.to_numeric(frame.get("volume",pd.Series(1.0,index=frame.index)),errors="coerce").fillna(1.0).clip(lower=1e-9)
    if "datetime" in frame:
        ts=pd.to_datetime(frame["datetime"],errors="coerce",utc=True)
        if ts.notna().any():
            d=ts.dt.date;return (typical*volume).groupby(d).cumsum()/volume.groupby(d).cumsum()
    return (typical*volume).cumsum()/volume.cumsum()


def _direction(m15):
    x=m15.tail(100).reset_index(drop=True)
    if len(x)<60:return "NEUTRAL"
    e20,e50,e200=ema(x,20).iloc[-1],ema(x,50).iloc[-1],ema(x,200).iloc[-1]; s=structure(x,min(80,len(x))); c=_finite(x.close.iloc[-1])
    if c is None:return "NEUTRAL"
    if c>e20>e50>e200 and s["bias"]=="BUY":return "BUY"
    if c<e20<e50<e200 and s["bias"]=="SELL":return "SELL"
    return "NEUTRAL"


def classify_regime(m5,m15):
    x=m5.tail(100).reset_index(drop=True).copy()
    if len(x)<60:return {"regime":"RANGE","allowed_engines":sorted(RANGE_ENGINES),"reason":"INSUFFICIENT_CONTEXT","direction":"NEUTRAL"}
    a=_atr(x); e20,e50,e200=ema(x,20),ema(x,50),ema(x,200); close=_finite(x.close.iloc[-1]); adx,di_plus,di_minus=_adx(x)
    slope=(_finite(e20.iloc[-1])-_finite(e20.iloc[-6]))/max(a or 1e-12,1e-12); s=structure(x,min(80,len(x)))
    recent_range=_finite(x.high.tail(12).max()-x.low.tail(12).min()); prior_range=_finite(x.high.iloc[-36:-12].max()-x.low.iloc[-36:-12].min()) if len(x)>=36 else None
    compression=recent_range/prior_range if prior_range and prior_range>0 else None; atr_now=a or 1e-12; atr_prev=_finite(atr14(x).iloc[-6]) if len(x)>=20 else None
    expansion=atr_now/atr_prev if atr_prev and atr_prev>0 else 1.0; vw=_vwap(x); vwap=_finite(vw.iloc[-1]) if len(vw) else None; m15_direction=_direction(m15)
    trend_up=bool(close and close>e20.iloc[-1]>e50.iloc[-1]>e200.iloc[-1] and s["bias"]=="BUY" and (di_plus or 0)>(di_minus or 0) and (adx or 0)>=25 and slope>0)
    trend_down=bool(close and close<e20.iloc[-1]<e50.iloc[-1]<e200.iloc[-1] and s["bias"]=="SELL" and (di_minus or 0)>(di_plus or 0) and (adx or 0)>=25 and slope<0)
    transition=bool(((adx or 0)>=20 and expansion>=1.10) or (compression is not None and compression<=0.75 and expansion>=1.05)) and not (trend_up or trend_down)
    if trend_up or trend_down: regime,direction="TREND","BUY" if trend_up else "SELL"
    elif transition: regime,direction="TRANSITION","BUY" if close and vwap and close>vwap else "SELL" if close and vwap and close<vwap else "NEUTRAL"
    else: regime,direction="RANGE","NEUTRAL"
    return {"regime":regime,"allowed_engines":sorted(allowed_engines_for_regime(regime)),"direction":direction,"m15_direction":m15_direction,"adx14":adx,"di_plus":di_plus,"di_minus":di_minus,"ema20":_finite(e20.iloc[-1]),"ema50":_finite(e50.iloc[-1]),"ema200":_finite(e200.iloc[-1]),"ema20_slope_atr":_finite(slope),"atr14":a,"atr_expansion":_finite(expansion),"range_ratio_atr":_finite(recent_range/atr_now) if recent_range is not None else None,"compression_ratio":_finite(compression),"vwap":vwap,"structure":s,"trend_up":trend_up,"trend_down":trend_down,"transition":transition}


def build_regime_context(m5,m15):
    return classify_regime(m5,m15)
