"""Structure V7: trade only after directional structure, location, sweep, MSS and retest confirmation.
No ATR fallback is allowed. Every live/replay trade must have causal invalidation and >=2R room.
"""
from __future__ import annotations
import math, os
import pandas as pd
from flask import Flask
import engine_v42 as base

ENGINE_VERSION = "7.0"
app = Flask(__name__)
SYMBOL = os.getenv("SYMBOL", "XAU/USD")
SPREAD = float(os.getenv("SPREAD", "0.2"))
SLIPPAGE = float(os.getenv("SLIPPAGE", "0.05"))
MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
RISK_REWARD = MIN_RISK_REWARD
FORWARD_BARS = int(os.getenv("FORWARD_BARS", "24"))
SIGNAL_HISTORY_POINTS = int(os.getenv("SIGNAL_HISTORY_POINTS", "200"))


def _f(v, d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError, ValueError): return d


def _atr(df, i, period=14):
    h,l,c=[pd.to_numeric(df[x],errors="coerce") for x in ("high","low","close")]
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return max(_f(tr.rolling(period).mean().iloc[i]), _f(h.iloc[i]-l.iloc[i]), 1e-9)


def _ema_bias(df):
    if df is None or len(df)<60: return "NEUTRAL"
    c=pd.to_numeric(df.close,errors="coerce")
    e20=c.ewm(span=20,adjust=False).mean().iloc[-1]; e50=c.ewm(span=50,adjust=False).mean().iloc[-1]; last=_f(c.iloc[-1])
    return "BUY" if last>e20>e50 else "SELL" if last<e20<e50 else "NEUTRAL"


def _structure(df, lookback=30):
    if df is None or len(df)<60: return {"bias":"NEUTRAL","high":None,"low":None}
    prior=df.iloc[:-1].tail(lookback); hi,lo=_f(prior.high.max()),_f(prior.low.min()); ema=_ema_bias(df); close=_f(df.iloc[-1].close)
    bias=ema
    if close>hi and ema=="BUY": bias="BUY"
    if close<lo and ema=="SELL": bias="SELL"
    return {"bias":bias,"high":hi,"low":lo}


def _location(df, direction, lookback=48):
    if df is None or len(df)<30: return {"valid":False,"zone":"INSUFFICIENT_DATA"}
    x=df.tail(lookback); hi,lo=_f(x.high.max()),_f(x.low.min()); width=max(hi-lo,1e-9); c=_f(df.iloc[-1].close)
    if direction=="BUY": valid=c<=lo+width*0.45; zone="DISCOUNT" if valid else "PREMIUM"
    else: valid=c>=hi-width*0.45; zone="PREMIUM" if valid else "DISCOUNT"
    return {"valid":valid,"zone":zone,"range_high":hi,"range_low":lo,"mid":lo+width*.5}


def _find_sweep(df, direction, window=12):
    if len(df)<30: return None
    start=max(2,len(df)-window)
    for j in range(len(df)-1,start-1,-1):
        prior=df.iloc[max(0,j-window):j]
        if len(prior)<6: continue
        r=df.iloc[j]; ph,pl=_f(prior.high.max()),_f(prior.low.min()); h,l,c=_f(r.high),_f(r.low),_f(r.close)
        if direction=="BUY" and l<pl and c>pl: return {"index":j,"type":"LIQUIDITY_SWEEP_LOW","level":pl,"extreme":l}
        if direction=="SELL" and h>ph and c<ph: return {"index":j,"type":"LIQUIDITY_SWEEP_HIGH","level":ph,"extreme":h}
    return None


def _find_mss(df, sweep, direction, window=8):
    if not sweep: return None
    for j in range(sweep["index"]+1,min(len(df),sweep["index"]+window+1)):
        prior=df.iloc[max(0,j-5):j]
        if len(prior)<3: continue
        r=df.iloc[j]; ph,pl=_f(prior.high.max()),_f(prior.low.min()); c=_f(r.close)
        if direction=="BUY" and c>ph: return {"index":j,"type":"BULLISH_MSS_BOS","level":ph}
        if direction=="SELL" and c<pl: return {"index":j,"type":"BEARISH_MSS_BOS","level":pl}
    return None


def _retest(df, mss, direction, tolerance_atr=.30):
    if not mss or mss["index"]>=len(df)-1: return {"valid":False,"reason":"WAITING_FOR_RETEST"}
    i=len(df)-1; r=df.iloc[i]; level=_f(mss["level"]); tol=_atr(df,i)*tolerance_atr
    if direction=="BUY": touched=_f(r.low)<=level+tol; held=_f(r.close)>level; confirm=_f(r.close)>_f(r.open)
    else: touched=_f(r.high)>=level-tol; held=_f(r.close)<level; confirm=_f(r.close)<_f(r.open)
    return {"valid":bool(touched and held and confirm),"level":level,"touched":bool(touched),"held":bool(held),"confirmation":bool(confirm),"reason":None if touched and held and confirm else "RETEST_NOT_CONFIRMED"}


def _target_liquidity(df, direction, entry, lookback=80):
    prior=df.iloc[:-1].tail(lookback)
    if direction=="BUY":
        vals=sorted(set(_f(x) for x in prior.high if _f(x)>entry)); return vals[0] if vals else None
    vals=sorted(set(_f(x) for x in prior.low if _f(x)<entry),reverse=True); return vals[0] if vals else None


def execution_price(raw, side):
    adverse=_f(SPREAD)/2+_f(SLIPPAGE); p=_f(raw); return p+adverse if side=="BUY" else p-adverse


def build_trade_levels(df,index,direction,invalidation,target):
    entry=execution_price(df.iloc[index].close,direction); atr=_atr(df,index); buffer=max(atr*.10,1e-9)
    sl=_f(invalidation)-buffer if direction=="BUY" else _f(invalidation)+buffer; tp=_f(target)
    if direction=="BUY" and not sl<entry<tp: return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    if direction=="SELL" and not sl>entry>tp: return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    risk=abs(entry-sl); reward=abs(tp-entry); rr=reward/risk if risk else 0
    if rr<MIN_RISK_REWARD: return {"valid":False,"reason":"RR_BELOW_2R","entry":entry,"sl":sl,"tp":tp,"risk":risk,"reward":reward,"risk_reward":rr}
    return {"valid":True,"entry":round(entry,8),"sl":round(sl,8),"tp":round(tp,8),"risk":round(risk,8),"reward":round(reward,8),"risk_reward":round(rr,3),"effective_rr":round(rr,3),"source":"structure_v7"}


def analyze_structure_setup(m5,m15,h1,index=None):
    if index is None: index=len(m5)-1
    m5=m5.iloc[:index+1].reset_index(drop=True)
    if len(m5)<80 or len(m15)<60 or len(h1)<60: return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    h1s=_structure(h1); m15s=_structure(m15); direction=h1s["bias"]; reasons=[]
    if direction not in ("BUY","SELL"): return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["H1_NOT_DIRECTIONAL"],"structure_bias":h1s,"m15_structure":m15s}
    if m15s["bias"] not in (direction,"NEUTRAL"): reasons.append("M15_OPPOSES_H1")
    loc=_location(m15,direction)
    if not loc["valid"]: reasons.append("M15_LOCATION_INVALID")
    sweep=_find_sweep(m5,direction)
    if not sweep: reasons.append("NO_LIQUIDITY_SWEEP")
    mss=_find_mss(m5,sweep,direction)
    if not mss: reasons.append("NO_MSS_BOS_AFTER_SWEEP")
    retest=_retest(m5,mss,direction)
    if not retest["valid"]: reasons.append(retest["reason"])
    entry=_f(m5.iloc[-1].close); target=_target_liquidity(m5,direction,entry)
    if target is None: reasons.append("NO_LIQUIDITY_TARGET")
    levels=build_trade_levels(m5,len(m5)-1,direction,sweep["extreme"],target) if sweep and target else {"valid":False,"reason":"LEVELS_UNAVAILABLE"}
    if not levels.get("valid"): reasons.append(levels.get("reason","LEVELS_INVALID"))
    signal=direction if not reasons else "NO_TRADE"; setup_key=f"{direction}:{sweep['index']}:{mss['index']}" if sweep and mss else None
    return {"signal":signal,"engine_version":ENGINE_VERSION,"valid":signal in ("BUY","SELL") and levels.get("valid",False),"structure_bias":h1s,"m15_structure":m15s,"location":loc,"liquidity_event":sweep,"m5_trigger":mss,"pullback":retest,"target_liquidity":target,"invalidation":sweep["extreme"] if sweep else None,"trade_levels":levels,"setup_key":setup_key,"rejection_reasons":reasons}


def resolve_trade(direction,entry,sl,tp,future):
    risk=abs(float(entry)-float(sl)); rr=abs(float(tp)-float(entry))/risk if risk else 0
    for _,r in future.iterrows():
        h,l=float(r.high),float(r.low); hit_sl=(l<=sl) if direction=="BUY" else (h>=sl); hit_tp=(h>=tp) if direction=="BUY" else (l<=tp); when=str(r.get("datetime",""))
        if hit_sl and hit_tp: return "AMBIGUOUS",0.0,when
        if hit_tp: return "WIN",rr,when
        if hit_sl: return "LOSS",-1.0,when
    return "OPEN",None,None


def calculate_trade_levels(df,i,direction,entry_price=None):
    setup=analyze_structure_setup(df,df,df,i)
    if setup.get("valid") and setup.get("signal")==direction: return setup["trade_levels"]
    return {"valid":False,"reason":"NO_VALID_STRUCTURE_SETUP"}

def evaluate_live_risk_guard(**kwargs): return base.evaluate_live_risk_guard(**kwargs)
def send_telegram(message): return base.send_telegram(message)
def calculate_indicators(df): return base.calculate_indicators(df)
def remove_incomplete_last_candle(df): return base.remove_incomplete_last_candle(df)
def safe_float(v,default=0.0): return _f(v,default)
