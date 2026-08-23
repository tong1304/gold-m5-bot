"""Multi-Strategy Engine v1 for BTC and XAU/USD.

Design: M15 context -> M5 structure -> strategy selection -> 1-3 candle trigger.
No H1 dependency and no weighted confluence. Exactly one strategy may become
active for a setup. Only closed candles are evaluated by callers.
"""
from __future__ import annotations

import math
import pandas as pd

BTC_STRATEGIES = ("TREND_PULLBACK", "BREAKOUT_RETEST", "RANGE_BREAKOUT", "MOMENTUM", "VOLATILITY_BREAKOUT")
GOLD_STRATEGIES = ("TREND_PULLBACK", "BREAKOUT_RETEST", "EMA_PULLBACK", "LIQUIDITY_SWEEP", "SR_REVERSAL", "VOLATILITY_BREAKOUT")

REGIME_STRATEGIES = {
    "TREND_UP": {"BTC": ["TREND_PULLBACK", "MOMENTUM", "BREAKOUT_RETEST"], "GOLD": ["TREND_PULLBACK", "EMA_PULLBACK", "BREAKOUT_RETEST"]},
    "TREND_DOWN": {"BTC": ["TREND_PULLBACK", "MOMENTUM", "BREAKOUT_RETEST"], "GOLD": ["TREND_PULLBACK", "EMA_PULLBACK", "BREAKOUT_RETEST"]},
    "BREAKOUT": {"BTC": ["BREAKOUT_RETEST", "RANGE_BREAKOUT", "VOLATILITY_BREAKOUT"], "GOLD": ["BREAKOUT_RETEST", "VOLATILITY_BREAKOUT", "SR_REVERSAL"]},
    "RANGE": {"BTC": ["RANGE_BREAKOUT", "BREAKOUT_RETEST"], "GOLD": ["SR_REVERSAL", "LIQUIDITY_SWEEP", "BREAKOUT_RETEST"]},
    "VOLATILITY_EXPANSION": {"BTC": ["VOLATILITY_BREAKOUT", "MOMENTUM", "BREAKOUT_RETEST"], "GOLD": ["VOLATILITY_BREAKOUT", "BREAKOUT_RETEST", "LIQUIDITY_SWEEP"]},
    "NEUTRAL": {"BTC": [], "GOLD": []},
}

def _num(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default

def _atr(df, period=14):
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def _ema(df, span):
    return pd.to_numeric(df["close"], errors="coerce").ewm(span=span, adjust=False).mean()

def _structure(df, lookback=50):
    x = df.tail(lookback).reset_index(drop=True)
    if len(x) < 20:
        return {"bias":"NEUTRAL","support":None,"resistance":None,"hh":False,"hl":False,"lh":False,"ll":False}
    highs, lows = [], []
    for i in range(2, len(x)-2):
        if _num(x.high.iloc[i]) >= max(_num(v) for v in x.high.iloc[i-2:i+3]): highs.append(_num(x.high.iloc[i]))
        if _num(x.low.iloc[i]) <= min(_num(v) for v in x.low.iloc[i-2:i+3]): lows.append(_num(x.low.iloc[i]))
    hh = len(highs) >= 2 and highs[-1] > highs[-2]
    hl = len(lows) >= 2 and lows[-1] > lows[-2]
    lh = len(highs) >= 2 and highs[-1] < highs[-2]
    ll = len(lows) >= 2 and lows[-1] < lows[-2]
    bias = "BUY" if hh and hl else "SELL" if lh and ll else "NEUTRAL"
    return {"bias":bias,"support":lows[-1] if lows else _num(x.low.min()),"resistance":highs[-1] if highs else _num(x.high.max()),"hh":hh,"hl":hl,"lh":lh,"ll":ll}

def _regime(m15, m5):
    x = m15.tail(100).reset_index(drop=True)
    y = m5.tail(50).reset_index(drop=True)
    if len(x) < 100 or len(y) < 50:
        return {"name":"NEUTRAL","direction":"NEUTRAL","reason":"INSUFFICIENT_CONTEXT"}
    c15 = _num(x.close.iloc[-1]); e20 = _num(_ema(x,20).iloc[-1]); e50 = _num(_ema(x,50).iloc[-1])
    a15 = _atr(x,14).iloc[-1]; med15 = _atr(x,14).dropna().tail(30).median(); ratio = _num(a15)/_num(med15) if _num(med15)>0 else 0
    s15 = _structure(x,100)
    direction = "BUY" if c15 > e20 > e50 and s15["bias"] == "BUY" else "SELL" if c15 < e20 < e50 and s15["bias"] == "SELL" else "NEUTRAL"
    ay = _atr(y,14); atr = _num(ay.iloc[-1]); med5 = _num(ay.dropna().tail(30).median()); vr = atr/med5 if med5>0 else 0
    prior = y.iloc[:-1].tail(20); hi = _num(prior.high.max()); lo = _num(prior.low.min()); close = _num(y.close.iloc[-1])
    range_width = hi-lo; range_atr = range_width/max(atr,1e-9)
    if vr >= 1.35 and (close > hi or close < lo): name="VOLATILITY_EXPANSION"
    elif close > hi or close < lo: name="BREAKOUT"
    elif direction in ("BUY","SELL") and 0.5 <= ratio <= 2.0: name="TREND_UP" if direction=="BUY" else "TREND_DOWN"
    elif range_atr <= 8.0: name="RANGE"
    else: name="NEUTRAL"
    return {"name":name,"direction":direction,"m15_close":c15,"m15_ema20":e20,"m15_ema50":e50,"m15_atr_ratio":round(ratio,3),"m5_atr_ratio":round(vr,3),"m5_range_high":hi,"m5_range_low":lo,"m5_range_atr":round(range_atr,3),"structure":s15}

def _candle(df, i=-1):
    r=df.iloc[i]; o,h,l,c=map(_num,(r.open,r.high,r.low,r.close)); rng=max(h-l,1e-12); body=abs(c-o)
    return {"open":o,"high":h,"low":l,"close":c,"body":body,"range":rng,"body_ratio":body/rng,"bull":c>o,"bear":c<o,"upper":h-max(o,c),"lower":min(o,c)-l}

def _trend_pullback(m5,direction):
    x=m5.tail(30).reset_index(drop=True); e20=_ema(x,20); e50=_ema(x,50); c=_num(x.close.iloc[-1]); a=_num(_atr(x,14).iloc[-1]); touched=False
    for i in range(max(0,len(x)-10),len(x)):
        if direction=="BUY" and _num(x.low.iloc[i]) <= _num(e20.iloc[i])+a*.35: touched=True
        if direction=="SELL" and _num(x.high.iloc[i]) >= _num(e20.iloc[i])-a*.35: touched=True
    last=_candle(x,-1); aligned=(c>_num(e20.iloc[-1])>_num(e50.iloc[-1])) if direction=="BUY" else (c<_num(e20.iloc[-1])<_num(e50.iloc[-1]))
    confirm=(last["bull"] and last["body_ratio"]>=.25) if direction=="BUY" else (last["bear"] and last["body_ratio"]>=.25)
    return touched and aligned and confirm

def _ema_pullback(m5,direction):
    x=m5.tail(25).reset_index(drop=True); e20=_ema(x,20); a=_num(_atr(x,14).iloc[-1]); last=_candle(x,-1); prev=x.iloc[-2]
    touch=(_num(prev.low)<=_num(e20.iloc[-2])+a*.35) if direction=="BUY" else (_num(prev.high)>=_num(e20.iloc[-2])-a*.35)
    confirm=(last["bull"] and last["close"]>_num(e20.iloc[-1])) if direction=="BUY" else (last["bear"] and last["close"]<_num(e20.iloc[-1]))
    return touch and confirm

def _breakout_retest(m5,direction):
    x=m5.tail(30).reset_index(drop=True); a=_num(_atr(x,14).iloc[-1]); last=_candle(x,-1)
    for j in range(max(5,len(x)-8),len(x)-1):
        base=x.iloc[max(0,j-20):j]; level=_num(base.high.max()) if direction=="BUY" else _num(base.low.min()); b=_candle(x,j)
        broke=(b["close"]>level and b["bull"] and b["body_ratio"]>=.30) if direction=="BUY" else (b["close"]<level and b["bear"] and b["body_ratio"]>=.30)
        if not broke: continue
        retest=(last["low"]<=level+a*.55 and last["close"]>=level and last["bull"]) if direction=="BUY" else (last["high"]>=level-a*.55 and last["close"]<=level and last["bear"])
        if retest:return True
    return False

def _range_breakout(m5,direction):
    x=m5.tail(30).reset_index(drop=True); prior=x.iloc[:-1].tail(20); last=_candle(x,-1); hi=_num(prior.high.max()); lo=_num(prior.low.min())
    return (last["close"]>hi and last["bull"] and last["body_ratio"]>=.30) if direction=="BUY" else (last["close"]<lo and last["bear"] and last["body_ratio"]>=.30)

def _momentum(m5,direction):
    x=m5.tail(20).reset_index(drop=True); a=_num(_atr(x,14).iloc[-1]); last=_candle(x,-1); move=_num(x.close.iloc[-1])-_num(x.close.iloc[-6]); threshold=max(a,1e-9)
    return (move>threshold and last["bull"] and last["body_ratio"]>=.45) if direction=="BUY" else (move<-threshold and last["bear"] and last["body_ratio"]>=.45)

def _volatility_breakout(m5,direction):
    x=m5.tail(45).reset_index(drop=True); aa=_atr(x,14); a=_num(aa.iloc[-1]); med=_num(aa.dropna().tail(30).median()); last=_candle(x,-1); prior=x.iloc[:-1].tail(20); hi=_num(prior.high.max()); lo=_num(prior.low.min()); expansion=a/max(med,1e-9)>=1.25
    return expansion and ((last["close"]>hi and last["bull"]) if direction=="BUY" else (last["close"]<lo and last["bear"]))

def _liquidity_sweep(m5,direction):
    x=m5.tail(30).reset_index(drop=True); a=_num(_atr(x,14).iloc[-1]); last=_candle(x,-1); prev=x.iloc[:-1].tail(12); hi=_num(prev.high.max()); lo=_num(prev.low.min())
    return (last["low"]<lo-a*.05 and last["close"]>lo and last["bull"]) if direction=="BUY" else (last["high"]>hi+a*.05 and last["close"]<hi and last["bear"])

def _sr_reversal(m5,direction):
    x=m5.tail(40).reset_index(drop=True); a=_num(_atr(x,14).iloc[-1]); last=_candle(x,-1); prior=x.iloc[:-1].tail(20); hi=_num(prior.high.max()); lo=_num(prior.low.min())
    return (last["low"]<=lo+a*.20 and last["close"]>lo and last["lower"]>=last["body"]*1.2) if direction=="BUY" else (last["high"]>=hi-a*.20 and last["close"]<hi and last["upper"]>=last["body"]*1.2)

def _passes(strategy,m5,direction):
    return {"TREND_PULLBACK":_trend_pullback,"BREAKOUT_RETEST":_breakout_retest,"RANGE_BREAKOUT":_range_breakout,"MOMENTUM":_momentum,"VOLATILITY_BREAKOUT":_volatility_breakout,"EMA_PULLBACK":_ema_pullback,"LIQUIDITY_SWEEP":_liquidity_sweep,"SR_REVERSAL":_sr_reversal}[strategy](m5,direction)

def _candidate_order(symbol,regime):
    return REGIME_STRATEGIES.get(regime,{}).get(symbol,[])

def _candidate_directions(strategy, regime, m5, regime_direction):
    """Choose directions for strategy evaluation without forcing a trend bias.

    TREND regimes use the M15 directional context. RANGE/BREAKOUT regimes are
    allowed to discover BUY or SELL from the closed M5 setup. The strategy must
    still pass its own full conditions; direction discovery is not a signal.
    """
    if regime_direction in ("BUY", "SELL"):
        return [regime_direction]

    x = m5.tail(21).reset_index(drop=True)
    last = _candle(x, -1)
    prior = x.iloc[:-1].tail(20)
    hi = _num(prior.high.max())
    lo = _num(prior.low.min())

    if strategy in ("RANGE_BREAKOUT", "BREAKOUT_RETEST", "VOLATILITY_BREAKOUT"):
        dirs=[]
        if last["close"] > hi: dirs.append("BUY")
        if last["close"] < lo: dirs.append("SELL")
        return dirs or ["BUY", "SELL"]

    if strategy in ("SR_REVERSAL", "LIQUIDITY_SWEEP"):
        return ["BUY", "SELL"] if last["bull"] else ["SELL", "BUY"]

    return ["BUY", "SELL"]

def analyze(m5,m15,h1=None,symbol="BTC"):
    """Analyze using only M15 and M5. h1 is accepted only for API compatibility and ignored."""
    symbol="GOLD" if str(symbol).upper() in ("GOLD","XAU","XAU/USDT","XAU/USD") else "BTC"
    if len(m5)<80 or len(m15)<100:
        return {"signal":"NO_TRADE","valid":False,"strategy":"NONE","regime":"NEUTRAL","rejection_reasons":["INSUFFICIENT_CONTEXT"]}
    regime=_regime(m15,m5); regime_name=regime.get("name","NEUTRAL"); direction=regime.get("direction")
    order=_candidate_order(symbol,regime_name)
    if not order:
        return {"signal":"NO_TRADE","valid":False,"strategy":"NONE","regime":regime_name,"regime_detail":regime,"strategy_candidates":[],"rejection_reasons":["NO_STRATEGIES_FOR_REGIME"]}
    tested=[]
    for strategy in order:
        for candidate_direction in _candidate_directions(strategy,regime_name,m5,direction):
            passed=_passes(strategy,m5,candidate_direction)
            tested.append({"strategy":strategy,"direction":candidate_direction,"passed":bool(passed)})
            if passed:
                return {"signal":candidate_direction,"valid":True,"strategy":strategy,"regime":regime_name,"regime_detail":regime,"strategy_candidates":tested,"analysis_window":{"m15_context_bars":100,"m5_structure_bars":50,"m5_setup_bars":20,"m5_trigger_bars":3},"trigger_candle_count":3,"rejection_reasons":[]}
    return {"signal":"NO_TRADE","valid":False,"strategy":"NONE","regime":regime_name,"regime_detail":regime,"strategy_candidates":tested,"analysis_window":{"m15_context_bars":100,"m5_structure_bars":50,"m5_setup_bars":20,"m5_trigger_bars":3},"rejection_reasons":["NO_STRATEGY_SETUP"]}
