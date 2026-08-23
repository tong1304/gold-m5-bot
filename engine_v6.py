"""Structure-first trading engine v6.

Decision model: H1 structure -> M15 location/liquidity -> M5 liquidity sweep
-> M5 MSS/BOS -> pullback/retest -> 2R+ target.  All structure calculations
are causal: a decision at index i only reads candles at or before i.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from flask import Flask

import engine_v42 as base

ENGINE_VERSION = "6.0"
app = Flask(__name__)

SYMBOL = os.getenv("SYMBOL", "XAU/USD")
TIMEFRAME = "5min"
MINIMUM_ATR = float(os.getenv("MINIMUM_ATR", "0.5"))
MIN_STOP_ATR = float(os.getenv("MIN_STOP_ATR", "0.8"))
MAX_STOP_ATR = float(os.getenv("MAX_STOP_ATR", "2.5"))
SPREAD = float(os.getenv("SPREAD", "0.2"))
SLIPPAGE = float(os.getenv("SLIPPAGE", "0.05"))
RISK_REWARD = max(float(os.getenv("RISK_REWARD", "2.0")), 2.0)
MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
FORWARD_BARS = int(os.getenv("FORWARD_BARS", "24"))
SIGNAL_HISTORY_POINTS = int(os.getenv("SIGNAL_HISTORY_POINTS", "200"))
BREAK_EVEN = False
BREAK_EVEN_R = 1.0


def _f(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _atr(df, i, period=14):
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    tr = pd.concat([(h-l), (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return max(_f(tr.rolling(period).mean().iloc[i], 0.0), _f(h.iloc[i]-l.iloc[i], 0.0), 1e-9)


def _ema_bias(df, i=None):
    if df is None or len(df) < 20:
        return "NEUTRAL"
    i = len(df)-1 if i is None else min(i, len(df)-1)
    close = pd.to_numeric(df["close"], errors="coerce")
    e20 = close.ewm(span=20, adjust=False).mean()
    e50 = close.ewm(span=50, adjust=False).mean()
    c, a, b = _f(close.iloc[i]), _f(e20.iloc[i]), _f(e50.iloc[i])
    if c > a > b:
        return "BUY"
    if c < a < b:
        return "SELL"
    return "NEUTRAL"


def _structure(df, i=None, lookback=20):
    if df is None or len(df) < 25:
        return {"bias":"NEUTRAL", "swing_high":None, "swing_low":None, "range_high":None, "range_low":None}
    i = len(df)-1 if i is None else min(i, len(df)-1)
    start = max(0, i-lookback)
    prior = df.iloc[start:i]  # deliberately excludes current candle
    if prior.empty:
        return {"bias":"NEUTRAL", "swing_high":None, "swing_low":None, "range_high":None, "range_low":None}
    rh, rl = _f(prior["high"].max()), _f(prior["low"].min())
    close = _f(df.iloc[i]["close"])
    ema = _ema_bias(df.iloc[:i+1], len(df.iloc[:i+1])-1)
    if close > rh and ema == "BUY": bias = "BUY"
    elif close < rl and ema == "SELL": bias = "SELL"
    else: bias = ema if ema != "NEUTRAL" else "NEUTRAL"
    return {"bias":bias, "swing_high":rh, "swing_low":rl, "range_high":rh, "range_low":rl}


def _location(df, i, direction, lookback=40):
    if df is None or len(df) < 10:
        return {"valid":False, "zone":"NEUTRAL", "range_high":None, "range_low":None, "mid":None}
    i = min(i, len(df)-1)
    prior = df.iloc[max(0, i-lookback):i+1]
    hi, lo = _f(prior["high"].max()), _f(prior["low"].min())
    width = max(hi-lo, 1e-9)
    mid = lo + width*0.5
    close = _f(df.iloc[i]["close"])
    if direction == "BUY":
        valid = close <= lo + width*0.45
        zone = "DISCOUNT_DEMAND" if valid else "PREMIUM"
    else:
        valid = close >= hi - width*0.45
        zone = "PREMIUM_SUPPLY" if valid else "DISCOUNT"
    return {"valid":valid, "zone":zone, "range_high":hi, "range_low":lo, "mid":mid, "distance_to_mid":round(abs(close-mid),6)}


def _find_sweep(df, i, direction, window=10):
    """Find the most recent causal liquidity sweep before/at i."""
    first = max(2, i-window)
    for j in range(i, first-1, -1):
        if j < 1:
            continue
        prior = df.iloc[max(0,j-window):j]
        if len(prior) < 5:
            continue
        row = df.iloc[j]
        ph, pl = _f(prior["high"].max()), _f(prior["low"].min())
        o, h, l, c = map(_f, (row["open"], row["high"], row["low"], row["close"]))
        if direction == "BUY" and l < pl and c > pl:
            return {"index":j,"type":"LIQUIDITY_SWEEP_LOW","level":pl,"extreme":l,"close":c}
        if direction == "SELL" and h > ph and c < ph:
            return {"index":j,"type":"LIQUIDITY_SWEEP_HIGH","level":ph,"extreme":h,"close":c}
    return None


def _find_mss(df, sweep_index, i, direction, window=8):
    start = sweep_index + 1
    end = min(i, sweep_index + window)
    if start > end:
        return None
    for j in range(start, end+1):
        row = df.iloc[j]
        prior = df.iloc[max(0,j-5):j]
        if len(prior) < 3:
            continue
        ph, pl = _f(prior["high"].max()), _f(prior["low"].min())
        c = _f(row["close"])
        if direction == "BUY" and c > ph:
            return {"index":j,"type":"BULLISH_MSS_BOS","level":ph,"close":c}
        if direction == "SELL" and c < pl:
            return {"index":j,"type":"BEARISH_MSS_BOS","level":pl,"close":c}
    return None


def _pullback(df, i, mss, direction):
    if not mss or i <= mss["index"]:
        return {"valid":False,"reason":"WAITING_FOR_PULLBACK"}
    row = df.iloc[i]
    atr = _atr(df, i)
    level = _f(mss["level"])
    tolerance = max(atr*0.35, 1e-9)
    high, low, close = _f(row["high"]), _f(row["low"]), _f(row["close"])
    if direction == "BUY":
        touched = low <= level + tolerance
        held = close > level
    else:
        touched = high >= level - tolerance
        held = close < level
    return {"valid":bool(touched and held), "level":level, "tolerance":tolerance, "touched":bool(touched), "held":bool(held), "reason":None if touched and held else "PULLBACK_NOT_CONFIRMED"}


def _target(df, i, direction, lookback=40):
    prior = df.iloc[max(0,i-lookback):i]
    if len(prior) < 5:
        return None
    close = _f(df.iloc[i]["close"])
    if direction == "BUY":
        candidates = sorted({_f(x) for x in prior["high"].tolist() if _f(x) > close})
        return candidates[0] if candidates else _f(prior["high"].max())
    candidates = sorted({_f(x) for x in prior["low"].tolist() if _f(x) < close}, reverse=True)
    return candidates[0] if candidates else _f(prior["low"].min())


def calculate_execution_price(raw_price, side, spread=None, slippage=None, is_entry=True):
    spread = _f(SPREAD if spread is None else spread)
    slippage = _f(SLIPPAGE if slippage is None else slippage)
    adverse = spread/2.0 + slippage
    p = _f(raw_price)
    if side == "BUY": return p + adverse if is_entry else p - adverse
    if side == "SELL": return p - adverse if is_entry else p + adverse
    raise ValueError("Invalid side")


def build_v6_trade_levels(df, index, direction, invalidation, target):
    entry_raw = _f(df.iloc[index]["close"])
    entry = calculate_execution_price(entry_raw, direction)
    atr = _atr(df, index)
    buffer = max(atr*0.10, 1e-9)
    if direction == "BUY":
        sl = _f(invalidation) - buffer
        tp = _f(target)
        if not tp > entry: return {"valid":False,"reason":"NO_UPSIDE_LIQUIDITY"}
    else:
        sl = _f(invalidation) + buffer
        tp = _f(target)
        if not tp < entry: return {"valid":False,"reason":"NO_DOWNSIDE_LIQUIDITY"}
    risk, reward = abs(entry-sl), abs(tp-entry)
    rr = reward/risk if risk else 0.0
    if risk <= 0 or rr < MIN_RISK_REWARD:
        return {"valid":False,"reason":"RR_BELOW_2R","entry":entry,"sl":sl,"tp":tp,"risk":risk,"reward":reward,"risk_reward":rr}
    return {"valid":True,"entry":round(entry,8),"sl":round(sl,8),"tp":round(tp,8),"risk":round(risk,8),"reward":round(reward,8),"risk_reward":round(rr,3),"effective_rr":round(rr,3),"source":"structure_v6"}


def analyze_structure_setup(m5, m15, h1, index=None):
    index = len(m5)-1 if index is None else int(index)
    reasons = []
    h1s = _structure(h1)
    m15s = _structure(m15)
    candidates = [d for d in ("BUY","SELL") if h1s["bias"] == d]
    if not candidates:
        return {"signal":"NO_TRADE","engine_version":ENGINE_VERSION,"rejection_reasons":["H1_STRUCTURE_NOT_DIRECTIONAL"],"structure_bias":h1s,"m15_structure":m15s}
    direction = candidates[0]
    location = _location(m15, len(m15)-1, direction)
    if not location["valid"]:
        reasons.append("M15_LOCATION_INVALID")
    sweep = _find_sweep(m5, index, direction)
    if not sweep:
        reasons.append("NO_LIQUIDITY_SWEEP")
    mss = _find_mss(m5, sweep["index"], index, direction) if sweep else None
    if not mss:
        reasons.append("NO_MSS_BOS_AFTER_SWEEP")
    pullback = _pullback(m5, index, mss, direction)
    if not pullback["valid"]:
        reasons.append(pullback.get("reason","PULLBACK_NOT_CONFIRMED"))
    target = _target(m5, index, direction)
    invalidation = sweep["extreme"] if sweep else None
    levels = build_v6_trade_levels(m5, index, direction, invalidation, target) if invalidation is not None and target is not None else {"valid":False,"reason":"LEVELS_UNAVAILABLE"}
    if not levels.get("valid"): reasons.append(levels.get("reason","LEVELS_INVALID"))
    signal = direction if not reasons else "NO_TRADE"
    setup_key = None
    if sweep and mss:
        setup_key = f"{direction}:{sweep['index']}:{mss['index']}:{round(_f(sweep['level']),8)}"
    return {
        "signal":signal,"engine_version":ENGINE_VERSION,"structure_bias":h1s,"m15_structure":m15s,
        "location":location,"liquidity_event":sweep,"m5_trigger":mss,"pullback":pullback,
        "target_liquidity":target,"invalidation":invalidation,"trade_levels":levels,
        "setup_key":setup_key,"rejection_reasons":reasons,
        "valid":signal in ("BUY","SELL") and bool(levels.get("valid")),
    }


def calculate_trade_levels(df, i, direction, entry_price=None):
    setup = analyze_structure_setup(df, df, df, i)
    if setup.get("signal") == direction and setup.get("trade_levels"):
        levels = dict(setup["trade_levels"])
        if entry_price is not None:
            return build_v6_trade_levels(df, i, direction, setup.get("invalidation"), setup.get("target_liquidity"))
        return levels
    atr = _atr(df, i)
    entry = calculate_execution_price(_f(df.iloc[i]["close"]) if entry_price is None else entry_price, direction)
    risk = atr * max(MIN_STOP_ATR, 1.0)
    return {"entry":entry,"sl":entry-risk if direction=="BUY" else entry+risk,"tp":entry+risk*RISK_REWARD if direction=="BUY" else entry-risk*RISK_REWARD,"risk_reward":RISK_REWARD,"effective_rr":RISK_REWARD,"risk":risk,"reward":risk*RISK_REWARD,"valid":True,"source":"atr_fallback_v6"}


def validate_trade_levels(entry, sl, tp, spread=None, slippage=None):
    risk, reward = abs(_f(entry)-_f(sl)), abs(_f(tp)-_f(entry))
    cost = _f(SPREAD if spread is None else spread) + 2*_f(SLIPPAGE if slippage is None else slippage)
    rr = max(0.0,reward-cost)/risk if risk else 0.0
    return {"valid":risk>0 and rr>=MIN_RISK_REWARD,"risk":risk,"reward":reward,"effective_rr":rr,"minimum_rr":MIN_RISK_REWARD,"reason":None if rr>=MIN_RISK_REWARD else "INVALID_OR_LOW_EFFECTIVE_RR"}


def evaluate_live_risk_guard(**kwargs):
    return base.evaluate_live_risk_guard(**kwargs)


def send_telegram(message):
    return base.send_telegram(message)


def calculate_indicators(df):
    return base.calculate_indicators(df)


def remove_incomplete_last_candle(df):
    return base.remove_incomplete_last_candle(df)


def safe_float(v, default=0.0):
    return _f(v, default)
