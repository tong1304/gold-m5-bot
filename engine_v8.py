"""Structure V8 - live/replay shared signal engine for BTC + GOLD.

Flow: Structure -> Location -> Liquidity Sweep -> MSS/BOS -> Pullback -> Confirmation.
The stages are causal and may occur across multiple closed M5 candles; they do not
have to occur on one candle. No weighted score is used. Minimum RR is 2R.
"""
from __future__ import annotations
import math, os
import pandas as pd
from flask import Flask
import engine_v42 as base

ENGINE_VERSION = "8.0"
app = Flask(__name__)
SYMBOL = os.getenv("SYMBOL", "XAU/USDT")
SPREAD = float(os.getenv("SPREAD", "0.20"))
SLIPPAGE = float(os.getenv("SLIPPAGE", "0.05"))
MINIMUM_ATR = float(os.getenv("MINIMUM_ATR", "0"))
MIN_STOP_ATR = float(os.getenv("MIN_STOP_ATR", "0"))
MAX_STOP_ATR = float(os.getenv("MAX_STOP_ATR", "4"))
MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
RISK_REWARD = MIN_RISK_REWARD
FORWARD_BARS = int(os.getenv("FORWARD_BARS", "24"))
SIGNAL_HISTORY_POINTS = int(os.getenv("SIGNAL_HISTORY_POINTS", "200"))


def _f(v, d=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else d
    except (TypeError, ValueError):
        return d


def _atr(df, i, period=14):
    if i < 1 or len(df) == 0: return 1e-9
    h = pd.to_numeric(df.high, errors="coerce")
    l = pd.to_numeric(df.low, errors="coerce")
    c = pd.to_numeric(df.close, errors="coerce")
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    value = _f(tr.rolling(period, min_periods=3).mean().iloc[i])
    return max(value, _f(h.iloc[i]-l.iloc[i]), 1e-9)


def _ema_bias(df):
    if df is None or len(df) < 50: return "NEUTRAL"
    c = pd.to_numeric(df.close, errors="coerce")
    e20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
    e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
    last = _f(c.iloc[-1])
    if last > e20 and e20 >= e50: return "BUY"
    if last < e20 and e20 <= e50: return "SELL"
    slope = _f(e20 - c.ewm(span=20, adjust=False).mean().iloc[-6])
    return "BUY" if slope > 0 else "SELL" if slope < 0 else "NEUTRAL"


def _structure(df, lookback=30):
    if df is None or len(df) < 50: return {"bias":"NEUTRAL","high":None,"low":None}
    x = df.iloc[:-1].tail(lookback)
    hi, lo = _f(x.high.max()), _f(x.low.min())
    bias = _ema_bias(df)
    c = _f(df.iloc[-1].close)
    if c > hi: bias = "BUY"
    elif c < lo: bias = "SELL"
    return {"bias":bias,"high":hi,"low":lo}


def _location(df, direction, lookback=48):
    if df is None or len(df) < 30: return {"valid":False,"zone":"INSUFFICIENT_DATA"}
    x = df.tail(lookback)
    hi, lo = _f(x.high.max()), _f(x.low.min())
    width = max(hi-lo, 1e-9)
    c = _f(df.iloc[-1].close)
    if direction == "BUY":
        valid = c <= lo + width * 0.60
        zone = "DISCOUNT" if c <= lo + width * 0.50 else "MID_DISCOUNT"
    else:
        valid = c >= hi - width * 0.60
        zone = "PREMIUM" if c >= hi - width * 0.50 else "MID_PREMIUM"
    return {"valid":bool(valid),"zone":zone if valid else ("PREMIUM" if direction=="BUY" else "DISCOUNT"),"range_high":hi,"range_low":lo,"mid":lo+width*.5}


def _find_sweep(df, direction, window=18):
    if df is None or len(df) < 35: return None
    start = max(2, len(df)-window)
    for j in range(len(df)-1, start-1, -1):
        prior = df.iloc[max(0,j-window):j]
        if len(prior) < 6: continue
        r = df.iloc[j]
        ph, pl = _f(prior.high.max()), _f(prior.low.min())
        h, l, c, o = _f(r.high), _f(r.low), _f(r.close), _f(r.open)
        if direction == "BUY" and l < pl and c >= pl:
            return {"index":j,"type":"LIQUIDITY_SWEEP_LOW","level":pl,"extreme":l,"close":c,"confirmed":True}
        if direction == "SELL" and h > ph and c <= ph:
            return {"index":j,"type":"LIQUIDITY_SWEEP_HIGH","level":ph,"extreme":h,"close":c,"confirmed":True}
    return None


def _find_mss(df, sweep, direction, window=10):
    if not sweep: return None
    start = sweep["index"] + 1
    end = min(len(df), sweep["index"] + window + 1)
    for j in range(start, end):
        prior = df.iloc[max(0,j-6):j]
        if len(prior) < 3: continue
        r = df.iloc[j]
        ph, pl = _f(prior.high.max()), _f(prior.low.min())
        c = _f(r.close)
        if direction == "BUY" and c > ph:
            return {"index":j,"type":"BULLISH_MSS_BOS","level":ph}
        if direction == "SELL" and c < pl:
            return {"index":j,"type":"BEARISH_MSS_BOS","level":pl}
    return None


def _find_latest_mss(df, direction, lookback=24):
    start=max(6,len(df)-lookback)
    for j in range(len(df)-1,start-1,-1):
        prior=df.iloc[max(0,j-6):j]
        if len(prior)<3: continue
        r=df.iloc[j]; ph,pl=_f(prior.high.max()),_f(prior.low.min()); c=_f(r.close)
        if direction=="BUY" and c>ph: return {"index":j,"type":"BULLISH_MSS_BOS","level":ph}
        if direction=="SELL" and c<pl: return {"index":j,"type":"BEARISH_MSS_BOS","level":pl}
    return None


def _retest(df, mss, direction, tolerance_atr=0.45):
    if not mss: return {"valid":False,"reason":"NO_MSS_BOS"}
    level=_f(mss["level"]); i=len(df)-1; r=df.iloc[i]; tol=_atr(df,i)*tolerance_atr
    if direction=="BUY":
        touched=_f(r.low)<=level+tol; held=_f(r.close)>=level; confirm=_f(r.close)>_f(r.open)
    else:
        touched=_f(r.high)>=level-tol; held=_f(r.close)<=level; confirm=_f(r.close)<_f(r.open)
    continuation = i > mss["index"] and ((direction=="BUY" and _f(r.close)>level) or (direction=="SELL" and _f(r.close)<level))
    valid=bool(touched and held and confirm) or bool(continuation and i-mss["index"]<=3 and confirm)
    return {"valid":valid,"level":level,"touched":bool(touched),"held":bool(held),"confirmation":bool(confirm),"continuation":bool(continuation),"reason":None if valid else "WAITING_FOR_PULLBACK_CONFIRMATION"}


def _target_liquidity(df, direction, entry, lookback=120):
    x=df.iloc[:-1].tail(lookback)
    if direction=="BUY":
        candidates=sorted([_f(v) for v in x.high if _f(v)>entry])
    else:
        candidates=sorted([_f(v) for v in x.low if _f(v)<entry], reverse=True)
    return candidates[0] if candidates else None


def execution_price(raw, side):
    adverse=max(_f(SPREAD)/2+_f(SLIPPAGE),0.0); p=_f(raw)
    return p+adverse if side=="BUY" else p-adverse


def build_trade_levels(df,index,direction,invalidation,target):
    entry=execution_price(df.iloc[index].close,direction); atr=_atr(df,index)
    buffer=max(atr*.12,1e-9)
    sl=_f(invalidation)-buffer if direction=="BUY" else _f(invalidation)+buffer
    tp=_f(target)
    if direction=="BUY" and not sl<entry<tp: return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    if direction=="SELL" and not sl>entry>tp: return {"valid":False,"reason":"INVALID_LEVEL_ORDER"}
    risk=abs(entry-sl); reward=abs(tp-entry); rr=reward/risk if risk else 0
    if rr<MIN_RISK_REWARD: return {"valid":False,"reason":"RR_BELOW_2R","entry":entry,"sl":sl,"tp":tp,"risk":risk,"reward":reward,"risk_reward":rr}
    return {"valid":True,"entry":round(entry,8),"sl":round(sl,8),"tp":round(tp,8),"risk":round(risk,8),"reward":round(reward,8),"risk_reward":round(rr,3),"effective_rr":round(rr,3),"source":"structure_v8"}


def analyze_structure_setup(m5,m15,h1,index=None):
    if index is None: index=len(m5)-1
    m5=m5.iloc[:index+1].reset_index(drop=True)
    if len(m5)<80 or len(m15)<60 or len(h1)<60:
        return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    h1s=_structure(h1); m15s=_structure(m15)
    direction=h1s["bias"] if h1s["bias"] in ("BUY","SELL") else m15s["bias"]
    if direction not in ("BUY","SELL"):
        return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"valid":False,"rejection_reasons":["NO_DIRECTIONAL_STRUCTURE"],"structure_bias":h1s,"m15_structure":m15s}
    reasons=[]
    if m15s["bias"] in ("BUY","SELL") and m15s["bias"] != direction:
        reasons.append("M15_OPPOSES_H1")
    loc=_location(m15,direction)
    if not loc["valid"]: reasons.append("M15_LOCATION_INVALID")
    sweep=_find_sweep(m5,direction)
    mss=_find_mss(m5,sweep,direction)
    if sweep and not mss:
        mss=_find_mss(m5,sweep,direction,window=16)
    if not sweep: reasons.append("NO_LIQUIDITY_SWEEP")
    if not mss: reasons.append("NO_MSS_BOS_AFTER_SWEEP")
    retest=_retest(m5,mss,direction)
    if not retest["valid"]: reasons.append(retest["reason"])
    entry=_f(m5.iloc[-1].close); target=_target_liquidity(m5,direction,entry)
    if target is None: reasons.append("NO_LIQUIDITY_TARGET")
    invalidation=sweep["extreme"] if sweep else None
    levels=build_trade_levels(m5,len(m5)-1,direction,invalidation,target) if invalidation is not None and target is not None else {"valid":False,"reason":"LEVELS_UNAVAILABLE"}
    if not levels.get("valid"): reasons.append(levels.get("reason","LEVELS_INVALID"))
    signal=direction if not reasons else "NO_TRADE"
    setup_key=f"{direction}:{sweep['index']}:{mss['index']}" if sweep and mss else None
    return {"signal":signal,"engine_version":ENGINE_VERSION,"valid":signal in ("BUY","SELL") and levels.get("valid",False),"structure_bias":h1s,"m15_structure":m15s,"location":loc,"liquidity_event":sweep,"m5_trigger":mss,"pullback":retest,"target_liquidity":target,"invalidation":invalidation,"trade_levels":levels,"setup_key":setup_key,"rejection_reasons":reasons}


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


def evaluate_live_risk_guard(*args, **kwargs):
    """V8-native live risk guard.

    Kept as a stable compatibility interface for app.py. All limits are opt-in
    through arguments or LIVE_* environment variables; zero means disabled.
    """
    def num(name, default=0.0):
        value = kwargs.get(name, default)
        try:
            value = float(value)
            return value if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default

    def integer(name, default=0):
        try:
            return int(kwargs.get(name, default))
        except (TypeError, ValueError):
            return default

    price_jump_atr = num("price_jump_atr", 0.0)
    daily_loss_r = num("daily_loss_r", 0.0)
    consecutive_losses = integer("consecutive_losses", 0)
    trades_today = integer("trades_today", 0)
    slippage = num("slippage", 0.0)

    max_price_jump_atr = num("max_price_jump_atr", float(os.getenv("LIVE_MAX_PRICE_JUMP_ATR", "0")))
    max_daily_loss_r = num("max_daily_loss_r", float(os.getenv("LIVE_MAX_DAILY_LOSS_R", "0")))
    max_consecutive_losses = integer("max_consecutive_losses", int(os.getenv("LIVE_MAX_CONSECUTIVE_LOSSES", "0")))
    max_trades_per_day = integer("max_trades_per_day", int(os.getenv("LIVE_MAX_TRADES_PER_DAY", "0")))
    max_slippage = num("max_slippage", float(os.getenv("LIVE_MAX_SLIPPAGE", "0")))

    reasons = []
    if max_price_jump_atr > 0 and price_jump_atr >= max_price_jump_atr:
        reasons.append("PRICE_JUMP_ATR")
    if max_daily_loss_r > 0 and daily_loss_r <= -abs(max_daily_loss_r):
        reasons.append("MAX_DAILY_LOSS_R")
    if max_consecutive_losses > 0 and consecutive_losses >= max_consecutive_losses:
        reasons.append("MAX_CONSECUTIVE_LOSSES")
    if max_trades_per_day > 0 and trades_today >= max_trades_per_day:
        reasons.append("MAX_TRADES_PER_DAY")
    if max_slippage > 0 and slippage > max_slippage:
        reasons.append("MAX_SLIPPAGE")

    return {
        "allowed": not reasons,
        "blocked": bool(reasons),
        "reasons": reasons,
        "price_jump_atr": price_jump_atr,
        "daily_loss_r": daily_loss_r,
        "consecutive_losses": consecutive_losses,
        "trades_today": trades_today,
        "slippage": slippage,
    }


send_telegram = base.send_telegram
calculate_indicators = base.calculate_indicators
remove_incomplete_last_candle = base.remove_incomplete_last_candle
safe_float = _f
