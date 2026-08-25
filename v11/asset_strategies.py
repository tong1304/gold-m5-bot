from __future__ import annotations

import math
import pandas as pd

from .common import atr14, ema
from .regime import strategy_allowed_by_regime
from .strategy_scoring import score_setup


MIN_RR = {"G1": 2.0, "G2": 2.0, "G3": 1.5, "B1": 2.0, "B2": 3.0, "B3": 1.5}
STRATEGY_NAMES = {
    "G1": "G1_TREND_PULLBACK",
    "G2": "G2_EMA_MOMENTUM_CONTINUATION",
    "G3": "G3_STRUCTURE_BREAK_CONTINUATION",
    "B1": "B1_VOLATILITY_EXPANSION_BREAKOUT",
    "B2": "B2_BREAKOUT_RETEST",
    "B3": "B3_LIQUIDITY_SWEEP_BREAKOUT",
}


def _n(v, default=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _body(c): return abs(_n(c.close) - _n(c.open))
def _range(c): return max(_n(c.high) - _n(c.low), 1e-12)
def _bull(c): return _n(c.close) > _n(c.open)
def _bear(c): return _n(c.close) < _n(c.open)


def _atr(x):
    a = atr14(x).dropna() if len(x) >= 14 else pd.Series(dtype=float)
    return _n(a.iloc[-1], 1.0) if len(a) else max(_n((x.high - x.low).tail(14).mean(), 1.0), 1e-12)


def _avg_body(x, n=20):
    return max(_n(pd.Series([_body(x.iloc[i]) for i in range(max(0, len(x)-n), len(x)-1)]).mean(), 0.0), 1e-12)


def _ema_alignment(x, direction):
    e20, e50 = ema(x, 20), ema(x, 50)
    if len(e20) == 0 or len(e50) == 0: return False, 0.0
    a, b = _n(e20.iloc[-1]), _n(e50.iloc[-1])
    slope = (_n(e20.iloc[-1]) - _n(e20.iloc[-6])) / max(_atr(x), 1e-12) if len(e20) >= 6 else 0.0
    ok = (a > b and slope > 0) if direction == "BUY" else (a < b and slope < 0)
    return ok, min(1.0, abs(slope) / 0.75)


def _rsi(x, period=14):
    d=pd.to_numeric(x.close,errors="coerce").diff();gain=d.clip(lower=0).ewm(alpha=1/period,adjust=False).mean();loss=(-d.clip(upper=0)).ewm(alpha=1/period,adjust=False).mean();rs=gain/loss.replace(0,pd.NA);rsi=100-(100/(1+rs));return _n(rsi.iloc[-1],50.0)


def _volume_ratio(x):
    if "volume" not in x:return 1.0
    avg=_n(pd.to_numeric(x.volume.iloc[-21:-1],errors="coerce").mean(),0);v=_n(x.volume.iloc[-1],0)
    return v/max(avg,1e-12) if avg else 1.0


def _filters(entry, sl, atr, ema20):
    risk=abs(entry-sl)
    return {
        "atr_too_low": atr <= 0,
        "sl_too_tight": risk < 0.25*atr,
        "sl_too_wide": risk > 2.5*atr,
        "overextended": abs(entry-ema20) > 1.8*atr,
    }


def _base_result(eid, direction, evidence, core_gate, components, filters, entry_type):
    scored=score_setup(eid,components,core_gate,filters)
    evidence=dict(evidence); evidence["core_gate"]=core_gate; evidence["score_detail"]=scored; evidence["filters"]=filters
    if not scored["qualified"]:
        return {"status":"FAIL","engine":eid,"strategy":STRATEGY_NAMES[eid],"direction":direction,"quality":scored["score"],"score_detail":scored,"evidence":evidence,"rejection_reasons":scored["failed_gate"] + scored["filter_rejections"]}
    return {"status":"PASS","engine":eid,"strategy":STRATEGY_NAMES[eid],"direction":direction,"quality":scored["score"],"score_detail":scored,"evidence":evidence,"entry_type_hint":entry_type,"setup_anchor":evidence.get("setup_anchor"),"trigger_signature":f"{eid}|{direction}|{evidence.get('entry_price')}","rejection_reasons":[]}


def _direction_context(regime, direction):
    h1=str(regime.get("h1_bias") or "NEUTRAL").upper(); m15=str(regime.get("m15_trend") or "NEUTRAL").upper()
    if h1 in ("BUY","SELL") and h1 != direction:return False
    if m15 in ("BUY","SELL") and m15 != direction:return False
    return True


def _g1(x, direction, regime):
    a=_atr(x); e20,e50=ema(x,20),ema(x,50); close=_n(x.close.iloc[-1]); ema20=_n(e20.iloc[-1]); aligned,align_strength=_ema_alignment(x,direction)
    recent=x.tail(12); pullback=bool(((recent.low<=e20.tail(12)).any()) if direction=="BUY" else ((recent.high>=e20.tail(12)).any()))
    if direction=="BUY":
        swing_low=_n(x.low.iloc[-12:-3].min()); structure_ok=close>swing_low; trigger=_bull(x.iloc[-1]) and _n(x.close.iloc[-1])>=_n(x.high.iloc[-1])-0.25*_range(x.iloc[-1])
        entry=close; sl=swing_low-0.10*a
    else:
        swing_high=_n(x.high.iloc[-12:-3].max()); structure_ok=close<swing_high; trigger=_bear(x.iloc[-1]) and _n(x.close.iloc[-1])<=_n(x.low.iloc[-1])+0.25*_range(x.iloc[-1])
        entry=close; sl=swing_high+0.10*a
    trend_ok=aligned and _direction_context(regime,direction)
    pull_quality=max(0.0,1.0-min(abs(close-ema20)/(1.2*a),1.0))
    structure_quality=1.0 if structure_ok else 0.0
    momentum=max(0.0,min(1.0,_body(x.iloc[-1])/max(_avg_body(x),1e-12)))
    location=max(0.0,1.0-min(abs(close-ema20)/(1.5*a),1.0))
    rsi=_rsi(x); rsi_score=(rsi/70.0 if direction=="BUY" else (100-rsi)/70.0); rsi_score=max(0.0,min(1.0,rsi_score))
    components={"trend_strength":15*min(1.0,align_strength+0.25),"ema_alignment":15 if aligned else 0,"pullback_quality":25*pull_quality,"structure_quality":15*structure_quality,"momentum":10*momentum,"location":10*location,"rsi":5*rsi_score,"atr":5*min(1.0,a/max(_avg_body(x),a))}
    filters=_filters(entry,sl,a,ema20)
    return _base_result("G1",direction,{"entry_price":entry,"sl_price":sl,"tp_price":entry+(MIN_RR["G1"]*abs(entry-sl) if direction=="BUY" else -MIN_RR["G1"]*abs(entry-sl)),"atr":a,"ema20":ema20,"ema50":_n(e50.iloc[-1]),"setup_anchor":ema20}, {"trend_direction":trend_ok,"pullback":pullback,"structure_intact":structure_ok,"entry_trigger":trigger}, components, filters,"MARKET")


def _g2(x, direction, regime):
    a=_atr(x); e20,e50=ema(x,20),ema(x,50); close=_n(x.close.iloc[-1]); ema20=_n(e20.iloc[-1]); aligned,_=_ema_alignment(x,direction); c=x.iloc[-1]; avg=_avg_body(x); body_ratio=_body(c)/max(avg,1e-12); close_quality=1.0-((_n(c.high)-_n(c.close))/_range(c) if direction=="BUY" else (_n(c.close)-_n(c.low))/_range(c)); close_quality=max(0.0,min(1.0,close_quality)); momentum_candle=body_ratio>=1.15 and ((_bull(c)) if direction=="BUY" else _bear(c)); confirmation=(_n(c.close)>_n(c.open)) if direction=="BUY" else (_n(c.close)<_n(c.open));
    entry=close; sl=(_n(x.low.iloc[-5:].min())-0.10*a) if direction=="BUY" else (_n(x.high.iloc[-5:].max())+0.10*a)
    components={"momentum_strength":25*min(1.0,body_ratio/1.8),"candle_body_quality":20*min(1.0,body_ratio/1.6),"ema_alignment":15 if aligned else 0,"price_location":10*max(0.0,1.0-min(abs(close-ema20)/(1.8*a),1.0)),"atr_expansion":10*min(1.0,_range(c)/max(1.35*a,1e-12)),"structure":10*(1.0 if _direction_context(regime,direction) else 0.0),"rsi":5*max(0.0,min(1.0,(_rsi(x)/70 if direction=="BUY" else (100-_rsi(x))/70))),"volume_activity":5*min(1.0,_volume_ratio(x)/1.5)}
    filters=_filters(entry,sl,a,ema20)
    return _base_result("G2",direction,{"entry_price":entry,"sl_price":sl,"tp_price":entry+(MIN_RR["G2"]*abs(entry-sl) if direction=="BUY" else -MIN_RR["G2"]*abs(entry-sl)),"atr":a,"ema20":ema20,"setup_anchor":ema20}, {"ema_direction":aligned and _direction_context(regime,direction),"momentum_candle":momentum_candle,"confirmation_close":confirmation}, components, filters,"MARKET")


def _g3(x, direction, regime):
    a=_atr(x); close=_n(x.close.iloc[-1]); prior_high=_n(x.high.iloc[-21:-3].max()); prior_low=_n(x.low.iloc[-21:-3].min());
    if direction=="BUY":
        bos=bool(close>prior_high); pull=bool(_n(x.low.iloc[-2])<=prior_high or _n(x.low.iloc[-1])<=prior_high); intact=bool(_n(x.low.iloc[-3:].min())>prior_low); trigger=_bull(x.iloc[-1]) and close>prior_high; entry=close; sl=_n(x.low.iloc[-3:].min())-0.10*a; anchor=prior_high
    else:
        bos=bool(close<prior_low); pull=bool(_n(x.high.iloc[-2])>=prior_low or _n(x.high.iloc[-1])>=prior_low); intact=bool(_n(x.high.iloc[-3:].max())<prior_high); trigger=_bear(x.iloc[-1]) and close<prior_low; entry=close; sl=_n(x.high.iloc[-3:].max())+0.10*a; anchor=prior_low
    body_ratio=_body(x.iloc[-1])/max(_avg_body(x),1e-12); ema_ok,_=_ema_alignment(x,direction)
    components={"bos_strength":20*min(1.0,body_ratio/1.5),"structure_quality":20*(1.0 if intact else 0.0),"pullback_quality":20*(1.0 if pull else 0.0),"continuation_momentum":15*min(1.0,body_ratio/1.5),"location":10*max(0.0,1.0-min(abs(close-anchor)/(2*a),1.0)),"atr":10*min(1.0,_range(x.iloc[-1])/max(a,1e-12)),"ema_alignment":5 if ema_ok else 0}
    filters=_filters(entry,sl,a,_n(ema(x,20).iloc[-1]))
    return _base_result("G3",direction,{"entry_price":entry,"sl_price":sl,"tp_price":entry+(MIN_RR["G3"]*abs(entry-sl) if direction=="BUY" else -MIN_RR["G3"]*abs(entry-sl)),"atr":a,"bos_level":anchor,"setup_anchor":anchor}, {"swing_structure":True,"bos":bos,"pullback_after_bos":pull,"structure_intact":intact,"continuation_trigger":trigger}, components, filters,"MARKET")


def _b1(x, direction, regime):
    a=_atr(x); c=x.iloc[-1]; close=_n(c.close); mid=pd.to_numeric(x.close).rolling(20).mean(); sd=pd.to_numeric(x.close).rolling(20).std(ddof=0); upper=mid+2*sd; lower=mid-2*sd; width=upper-lower; compressed=bool(len(width)>=30 and _n(width.iloc[-5])<=_n(width.tail(30).quantile(.25))); rh=_n(x.high.iloc[-21:-1].max()); rl=_n(x.low.iloc[-21:-1].min()); breakout=(_bull(c) and close>rh) if direction=="BUY" else (_bear(c) and close<rl); body_ratio=_body(c)/max(_avg_body(x),1e-12); expansion=_range(c)>=1.25*a and _n(width.iloc[-1])>_n(width.iloc[-2]); entry=close; sl=(_n(x.low.iloc[-4:].min())-0.10*a) if direction=="BUY" else (_n(x.high.iloc[-4:].max())+0.10*a); level=rh if direction=="BUY" else rl; filters=_filters(entry,sl,a,_n(ema(x,20).iloc[-1]));
    components={"breakout_strength":20*min(1.0,body_ratio/1.5),"volatility_expansion":20*(1.0 if expansion else 0.0),"momentum":15*min(1.0,body_ratio/1.5),"candle_quality":10*min(1.0,1-((_n(c.high)-close)/_range(c) if direction=="BUY" else (close-_n(c.low))/_range(c))),"location":10*max(0.0,1.0-min(abs(close-level)/(1.5*a),1.0)),"distance_from_breakout":10*max(0.0,1.0-min(abs(close-level)/(1.2*a),1.0)),"trend_alignment":10*(1.0 if _direction_context(regime,direction) else 0.0),"volume_activity":5*min(1.0,_volume_ratio(x)/1.5)}
    return _base_result("B1",direction,{"entry_price":entry,"sl_price":sl,"tp_price":entry+(MIN_RR["B1"]*abs(entry-sl) if direction=="BUY" else -MIN_RR["B1"]*abs(entry-sl)),"atr":a,"range_high":rh,"range_low":rl,"setup_anchor":level}, {"compression":compressed,"breakout":breakout,"breakout_close":breakout}, components, filters,"MARKET")


def _b2(x, direction, regime):
    a=_atr(x); close=_n(x.close.iloc[-1]); level=_n(x.high.iloc[-21:-6].max()) if direction=="BUY" else _n(x.low.iloc[-21:-6].min()); breakout_idx=None
    for i in range(len(x)-6,len(x)-1):
        if direction=="BUY" and _n(x.close.iloc[i])>level: breakout_idx=i; break
        if direction=="SELL" and _n(x.close.iloc[i])<level: breakout_idx=i; break
    retest=bool(breakout_idx is not None and ((_n(x.low.iloc[-2])<=level) if direction=="BUY" else (_n(x.high.iloc[-2])>=level)))
    holds=bool(close>level if direction=="BUY" else close<level); trigger=(_bull(x.iloc[-1]) if direction=="BUY" else _bear(x.iloc[-1])) and holds
    entry=close; sl=(_n(x.low.iloc[-4:].min())-0.10*a) if direction=="BUY" else (_n(x.high.iloc[-4:].max())+0.10*a); body_ratio=_body(x.iloc[-1])/max(_avg_body(x),1e-12); filters=_filters(entry,sl,a,_n(ema(x,20).iloc[-1]))
    components={"retest_quality":20*(1.0 if retest else 0.0),"momentum":15*min(1.0,body_ratio/1.5),"structure":15*(1.0 if holds else 0.0),"breakout_strength":15*min(1.0,body_ratio/1.5),"location":10*max(0.0,1.0-min(abs(close-level)/(1.5*a),1.0)),"atr":10*min(1.0,_range(x.iloc[-1])/max(a,1e-12)),"volume_activity":10*min(1.0,_volume_ratio(x)/1.5),"rsi":5*max(0.0,min(1.0,(_rsi(x)/70 if direction=="BUY" else (100-_rsi(x))/70)))}
    return _base_result("B2",direction,{"entry_price":entry,"sl_price":sl,"tp_price":entry+(MIN_RR["B2"]*abs(entry-sl) if direction=="BUY" else -MIN_RR["B2"]*abs(entry-sl)),"atr":a,"breakout_level":level,"setup_anchor":level}, {"key_level":True,"breakout":breakout_idx is not None,"retest":retest,"retest_holds":holds,"confirmation_candle":trigger}, components, filters,"MARKET")


def _b3(x, direction, regime):
    a=_atr(x); close=_n(x.close.iloc[-1]); level=_n(x.low.iloc[-10:-2].min()) if direction=="BUY" else _n(x.high.iloc[-10:-2].max()); sweep_idx=None
    for i in range(len(x)-7,len(x)-1):
        if direction=="BUY" and _n(x.low.iloc[i])<level and _n(x.close.iloc[i])>level:sweep_idx=i;break
        if direction=="SELL" and _n(x.high.iloc[i])>level and _n(x.close.iloc[i])<level:sweep_idx=i;break
    reclaim=bool(sweep_idx is not None and (close>level if direction=="BUY" else close<level)); confirmation=(_bull(x.iloc[-1]) if direction=="BUY" else _bear(x.iloc[-1])) and reclaim; depth=abs((_n(x.low.iloc[sweep_idx]) if direction=="BUY" else _n(x.high.iloc[sweep_idx]))-level)/max(a,1e-12) if sweep_idx is not None else 0.0; body_ratio=_body(x.iloc[-1])/max(_avg_body(x),1e-12); entry=close; sl=(_n(x.low.iloc[sweep_idx])-0.10*a) if direction=="BUY" and sweep_idx is not None else (_n(x.high.iloc[sweep_idx])+0.10*a if sweep_idx is not None else close); filters=_filters(entry,sl,a,_n(ema(x,20).iloc[-1]));
    components={"rejection_quality":20*(1.0 if reclaim else 0.0),"displacement":20*min(1.0,body_ratio/1.5),"structure_shift":20*(1.0 if confirmation else 0.0),"sweep_depth":15*min(1.0,depth/1.0),"momentum":10*min(1.0,body_ratio/1.5),"location":10*max(0.0,1.0-min(abs(close-level)/(1.5*a),1.0)),"rsi":5*max(0.0,min(1.0,(_rsi(x)/70 if direction=="BUY" else (100-_rsi(x))/70)))}
    return _base_result("B3",direction,{"entry_price":entry,"sl_price":sl,"tp_price":entry+(MIN_RR["B3"]*abs(entry-sl) if direction=="BUY" else -MIN_RR["B3"]*abs(entry-sl)),"atr":a,"sweep_level":level,"setup_anchor":level}, {"liquidity_level":True,"sweep":sweep_idx is not None,"reclaim":reclaim,"confirmation":confirmation}, components, filters,"MARKET")


REGISTRY={"G1":_g1,"G2":_g2,"G3":_g3,"B1":_b1,"B2":_b2,"B3":_b3}


def evaluate_asset_strategies(asset, m5, regime):
    asset=str(asset).upper(); ids=("G1","G2","G3") if asset=="GOLD" else ("B1","B2","B3")
    x=m5.tail(120).reset_index(drop=True).copy(); out=[]; trace=[]; current_regime=str(regime.get("m5_regime") or regime.get("regime") or "TRANSITION").upper()
    for eid in ids:
        if not strategy_allowed_by_regime(asset,eid,current_regime):
            trace.append({"status":"NOT_APPLICABLE","engine":eid,"strategy":STRATEGY_NAMES[eid],"regime":current_regime,"reason":"REGIME_NOT_COMPATIBLE"})
            continue
        for direction in ("BUY","SELL"):
            try:item=REGISTRY[eid](x,direction,regime)
            except Exception as exc:item={"status":"FAIL","engine":eid,"strategy":STRATEGY_NAMES[eid],"direction":direction,"quality":0.0,"rejection_reasons":[f"ENGINE_ERROR:{type(exc).__name__}:{exc}"]}
            item["asset"]=asset;item["regime"]=current_regime;trace.append(item)
            if item.get("status")=="PASS":out.append(item)
    out.sort(key=lambda z:(-float((z.get("score_detail") or {}).get("score",0)),z["engine"]))
    return out,trace
