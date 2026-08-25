from __future__ import annotations
import math
import pandas as pd
from .common import ema, atr14, structure
from .h1_gate import allows_trend_direction, gate_reason

# V12 asset-specific regime layer. Regime selects which asset-specific strategy
# family may run; it is not a universal indicator gate for every strategy.
TREND_ENGINES={"E1","E2","E5"}
RANGE_ENGINES={"E6","E7","E8"}
TRANSITION_ENGINES={"E3","E4","E7"}
TREND_ADX_THRESHOLD=20.0
TREND_EMA_FAST="EMA20"
TREND_EMA_SLOW="EMA50"

ASSET_STRATEGY_REGIMES={
    "G1":{"asset":"GOLD","regimes":{"TREND"}},
    "G2":{"asset":"GOLD","regimes":{"TREND","EXPANSION"}},
    "G3":{"asset":"GOLD","regimes":{"TREND","BREAKOUT_RETEST","EXPANSION"}},
    "B1":{"asset":"BTC","regimes":{"EXPANSION"}},
    "B2":{"asset":"BTC","regimes":{"BREAKOUT_RETEST","EXPANSION"}},
    "B3":{"asset":"BTC","regimes":{"RANGE","TRANSITION"}},
}

def _normal_asset(asset: str) -> str:
    asset=str(asset or "").upper()
    if asset in ("XAU","XAUUSD","XAU/USD","XAU/USDT"):return "GOLD"
    if asset in ("BTCUSD","BTC/USD","BTC/USDT"):return "BTC"
    return asset

def native_strategy_ids(asset: str, regime: str) -> list[str]:
    target=_normal_asset(asset);regime=str(regime or "").upper()
    return [engine for engine,profile in ASSET_STRATEGY_REGIMES.items() if profile.get("asset")==target and regime in profile.get("regimes",set())]

def allowed_engines_for_regime(regime:str)->set[str]:
    regime=str(regime).upper()
    if regime=="TREND":return set(TREND_ENGINES)
    if regime=="RANGE":return set(RANGE_ENGINES)
    if regime=="TRANSITION":return set(TRANSITION_ENGINES)
    return set()

def strategy_allowed_by_regime(asset: str, strategy: str, regime: str) -> bool:
    asset=_normal_asset(asset);strategy=str(strategy).upper();regime=str(regime).upper()
    profile=ASSET_STRATEGY_REGIMES.get(strategy)
    return bool(profile and profile["asset"]==asset and regime in profile["regimes"])

def _finite(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):
        return None

def _atr(frame):
    value=_finite(atr14(frame).iloc[-1]) if len(frame)>=14 else None
    if value is None or value<=0:value=_finite((frame.high-frame.low).tail(14).mean())
    return value if value is not None and value>0 else None

def _adx(frame,period=14):
    h=pd.to_numeric(frame.high,errors="coerce");l=pd.to_numeric(frame.low,errors="coerce");c=pd.to_numeric(frame.close,errors="coerce")
    up=h.diff();down=-l.diff();plus_dm=up.where((up>down)&(up>0),0.0);minus_dm=down.where((down>up)&(down>0),0.0)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    plus=100*plus_dm.ewm(alpha=1/period,adjust=False,min_periods=period).mean()/atr.replace(0,pd.NA)
    minus=100*minus_dm.ewm(alpha=1/period,adjust=False,min_periods=period).mean()/atr.replace(0,pd.NA)
    dx=(100*(plus-minus).abs()/(plus+minus).replace(0,pd.NA)).fillna(0)
    adx=dx.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    return _finite(adx.iloc[-1]),_finite(plus.iloc[-1]),_finite(minus.iloc[-1])

def _bollinger_width(frame,period=20,std_mult=2.0):
    c=pd.to_numeric(frame.close,errors="coerce");mid=c.rolling(period,min_periods=period).mean();std=c.rolling(period,min_periods=period).std(ddof=0)
    return (mid+std_mult*std)-(mid-std_mult*std)

def _vwap(frame):
    typical=(pd.to_numeric(frame.high,errors="coerce")+pd.to_numeric(frame.low,errors="coerce")+pd.to_numeric(frame.close,errors="coerce"))/3
    volume=pd.to_numeric(frame.get("volume",pd.Series(1.0,index=frame.index)),errors="coerce").fillna(1.0).clip(lower=1e-9)
    ts=pd.to_datetime(frame.get("datetime"),errors="coerce",utc=True)
    if ts.notna().any():
        d=ts.dt.date
        return (typical*volume).groupby(d).cumsum()/volume.groupby(d).cumsum()
    return (typical*volume).cumsum()/volume.cumsum()

def _direction(frame):
    x=frame.tail(100).reset_index(drop=True)
    if len(x)<60:return "NEUTRAL"
    e20,e50,e200=ema(x,20).iloc[-1],ema(x,50).iloc[-1],ema(x,200).iloc[-1];s=structure(x,min(80,len(x)));c=_finite(x.close.iloc[-1]);adx,di_plus,di_minus=_adx(x)
    if c is None:return "NEUTRAL"
    if c>e20>e50>e200 and s["bias"]=="BUY" and (adx or 0)>25 and (di_plus or 0)>(di_minus or 0):return "BUY"
    if c<e20<e50<e200 and s["bias"]=="SELL" and (adx or 0)>25 and (di_minus or 0)>(di_plus or 0):return "SELL"
    return "NEUTRAL"

def _mtf_trend_direction(h1):
    if h1 is None or len(h1)<60:return "NEUTRAL"
    return _direction(h1)

def _classify_m15(m15):
    x=m15.tail(100).reset_index(drop=True).copy()
    if len(x)<60:return {"regime":"UNKNOWN","direction":"NEUTRAL","trend_direction":"NEUTRAL","reason":"INSUFFICIENT_M15_CONTEXT","trend_threshold_adx":TREND_ADX_THRESHOLD,"trend_ema_alignment":f"{TREND_EMA_FAST}>{TREND_EMA_SLOW}"}
    a=_atr(x);e20,e50,e200=ema(x,20),ema(x,50),ema(x,200);close=_finite(x.close.iloc[-1]);adx,di_plus,di_minus=_adx(x);s=structure(x,min(80,len(x)));atr_now=a or 1e-12
    slope=(_finite(e20.iloc[-1])-_finite(e20.iloc[-6]))/atr_now
    trend_up=bool(close and close>e20.iloc[-1]>e50.iloc[-1] and s["bias"]=="BUY" and (adx or 0)>TREND_ADX_THRESHOLD and (di_plus or 0)>(di_minus or 0))
    trend_down=bool(close and close<e20.iloc[-1]<e50.iloc[-1] and s["bias"]=="SELL" and (adx or 0)>TREND_ADX_THRESHOLD and (di_minus or 0)>(di_plus or 0))
    trend_direction="BUY" if trend_up else "SELL" if trend_down else "NEUTRAL"
    bw=_bollinger_width(x,20,2.0);lowest50=bool(len(bw)>=50 and pd.notna(bw.iloc[-1]) and bw.iloc[-1]<=bw.tail(50).min()*1.02)
    ema_flat=abs(_finite(e20.iloc[-1])-_finite(e20.iloc[-6]))<=0.20*atr_now
    range_regime=bool((adx or 0)<20 and ema_flat)
    if trend_up:regime="TREND"
    elif trend_down:regime="TREND"
    elif lowest50:regime="TRANSITION"
    elif range_regime:regime="RANGE"
    else:regime="TRANSITION"
    return {"regime":regime,"direction":trend_direction,"trend_direction":trend_direction,"adx14":adx,"di_plus":di_plus,"di_minus":di_minus,"ema20":_finite(e20.iloc[-1]),"ema50":_finite(e50.iloc[-1]),"ema200":_finite(e200.iloc[-1]),"ema20_slope_atr":_finite(slope),"ema20_flat":ema_flat,"atr14":a,"bb_width":_finite(bw.iloc[-1]) if len(bw) else None,"bb_width_lowest50":lowest50,"range_filter":range_regime,"structure":s,"trend_up":trend_up,"trend_down":trend_down,"trend_threshold_adx":TREND_ADX_THRESHOLD,"trend_ema_alignment":f"{TREND_EMA_FAST}>{TREND_EMA_SLOW}"}

def _m5_range(c):return max(_finite(c.high)-_finite(c.low),0.0)

def detect_m5_regime(m5):
    x=m5.tail(80).reset_index(drop=True).copy()
    if len(x)<30:return "TRANSITION"
    a=_atr(x) or 1e-12;e20=ema(x,20);close=_finite(x.close.iloc[-1])
    if close is None:return "TRANSITION"
    bw=_bollinger_width(x,20,2.0);squeeze=bool(len(bw)>=40 and _finite(bw.iloc[-5]) is not None and _finite(bw.iloc[-5])<=_finite(bw.tail(40).quantile(.25)))
    last_range=_m5_range(x.iloc[-1]);expansion=last_range>=1.35*a and len(bw)>=2 and _finite(bw.iloc[-1]) is not None and _finite(bw.iloc[-2]) is not None and bw.iloc[-1]>bw.iloc[-2]
    rh=_finite(x.high.iloc[-21:-1].max());rl=_finite(x.low.iloc[-21:-1].min());breakout=bool((close>rh or close<rl) and last_range>=0.6*a);retest=False
    if breakout and len(x)>=3:
        level=rh if close>rh else rl;retest=bool(_finite(x.low.iloc[-2])<=level<=_finite(x.high.iloc[-2]))
    adx,_,_=_adx(x);slope=abs((_finite(e20.iloc[-1])-_finite(e20.iloc[-6]))/a) if len(e20)>=6 else 0
    if expansion and breakout:return "EXPANSION"
    if retest:return "BREAKOUT_RETEST"
    if squeeze and breakout:return "EXPANSION"
    if (adx or 0)<20 and slope<0.25:return "RANGE"
    if (adx or 0)>20 and slope>=0.25:return "TREND"
    return "TRANSITION"

def classify_regime(m5,m15=None,h1=None):
    """Asset-neutral M5 regime plus H1/M15 context; strategy gates are asset-specific."""
    x=m5.tail(100).reset_index(drop=True).copy();h1_bias=_mtf_trend_direction(h1)
    m15_info=_classify_m15(m15) if m15 is not None else {"regime":"UNKNOWN","direction":"NEUTRAL","trend_direction":"NEUTRAL","reason":"M15_REQUIRED"}
    m5_regime=detect_m5_regime(x)
    if len(x)<60:return {"regime":"UNKNOWN","m5_regime":m5_regime,"allowed_engines":[],"direction":"NEUTRAL","h1_bias":h1_bias,"m15_regime":m15_info.get("regime"),"m15_trend":m15_info.get("trend_direction"),"m15_context":m15_info,"reason":"INSUFFICIENT_M5_CONTEXT"}
    direction=m15_info.get("trend_direction","NEUTRAL");h1_gate={"bias":h1_bias,"mode":"DIRECTIONAL_CONTEXT","directional_constraint":h1_bias if h1_bias in ("BUY","SELL") else None}
    return {"regime":m5_regime,"m5_regime":m5_regime,"allowed_engines":[],"direction":direction,"h1_bias":h1_bias,"h1_gate":h1_gate,"m15_regime":m15_info.get("regime"),"m15_trend":direction,"m15_context":m15_info,"m5_context_bars":min(100,len(x)),"m15_regime_filter_enabled":False,"m15_role":"TREND_CONTEXT"}

def build_regime_context(m5,m15=None,h1=None):return classify_regime(m5,m15,h1)
