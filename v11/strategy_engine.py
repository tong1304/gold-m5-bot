from __future__ import annotations
import hashlib
import pandas as pd
import numpy as np
from .common import num, ema, atr14, structure, candle_metrics

ENGINE_NAMES={"E1":"IMPULSE_PULLBACK","E2":"TREND_PULLBACK","E3":"RANGE_BREAK_EXPANSION","E4":"BREAK_RETEST_CONTINUATION","E5":"MOMENTUM_EXPANSION","E6":"EXTREME_REJECTION_MEAN_RETURN","E7":"SWEEP_REJECTION_REVERSAL","E8":"RANGE_REJECTION"}
ENGINE_PRIORITY={"E7":0,"E4":1,"E1":2,"E2":3,"E5":4,"E3":5,"E6":6,"E8":7}

def _stable_id(prefix,*parts):
    raw="|".join("" if p is None else str(p).strip() for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"
def build_setup_id(symbol,regime,engine_id,direction,anchor):return _stable_id("SETUP",symbol,regime,engine_id,direction,round(float(anchor),8) if anchor is not None else "NA")
def build_trigger_id(engine_id,direction,candle_time,trigger_signature):return _stable_id("TRIGGER",engine_id,direction,candle_time,trigger_signature)
def _atr(x):
    a=atr14(x).dropna();return num(a.iloc[-1]) if len(a) else num((x.high-x.low).tail(14).mean(),1e-12)
def _pivots(x):
    highs=[];lows=[]
    for i in range(2,len(x)-2):
        if num(x.high.iloc[i])>=max(num(v) for v in x.high.iloc[i-2:i+3]):highs.append((i,num(x.high.iloc[i])))
        if num(x.low.iloc[i])<=min(num(v) for v in x.low.iloc[i-2:i+3]):lows.append((i,num(x.low.iloc[i])))
    return highs,lows
def _volume_ratio(x,period=20):
    v=pd.to_numeric(x.get("volume",pd.Series(1.0,index=x.index)),errors="coerce").fillna(1.0);return num(v.iloc[-1]/max(num(v.tail(period).mean(),1e-12),1e-12))
def _trend_filter_ok(context,direction):
    m15=context.get("m15_context",{}) or {}
    return bool(context.get("regime")=="TREND" and context.get("direction")==direction and (m15.get("adx14",context.get("adx14",0)) or 0)>20 and context.get("h1_bias")==direction and m15.get("trend_ema_alignment") in (None,"EMA20>EMA50","EMA20<EMA50"))
def _candidate_directions(context):
    direction=context.get("direction")
    if direction in ("BUY","SELL"):
        if context.get("regime")=="TRANSITION" and context.get("h1_bias")=="NEUTRAL":
            return ["BUY","SELL"]
        return [direction]
    return ["BUY","SELL"]
def _bullish_reversal(last,prev):
    engulf=last["bull"] and prev["bear"] and last["open"]<=prev["close"] and last["close"]>=prev["open"];pin=last["bull"] and last["lower_wick"]>=max(last["body"]*1.5,last["range"]*.45) and last["close_location"]>=.65;return engulf or pin
def _bearish_reversal(last,prev):
    engulf=last["bear"] and prev["bull"] and last["open"]>=prev["close"] and last["close"]<=prev["open"];pin=last["bear"] and last["upper_wick"]>=max(last["body"]*1.5,last["range"]*.45) and last["close_location"]<=.35;return engulf or pin
def _with_location(m):m=dict(m);m["close_location"]=(m["close"]-m["low"])/max(m["range"],1e-12);return m
def _e5_momentum_ok(*,body_atr,volume_ratio,marubozu):return bool(body_atr>=2.5 and volume_ratio>=1.5 and marubozu)
def _e3_breakout_ok(*,close_break,volume_ratio):return bool(close_break and volume_ratio>=1.8)
def _rsi(x,period=14):
    c=pd.to_numeric(x.close,errors="coerce");d=c.diff();gain=d.clip(lower=0).rolling(period,min_periods=period).mean();loss=(-d.clip(upper=0)).rolling(period,min_periods=period).mean();rs=gain/loss.replace(0,np.nan);return 100-(100/(1+rs))
def _bollinger(x,period=20,mult=2.5):
    c=pd.to_numeric(x.close,errors="coerce");mid=c.rolling(period,min_periods=period).mean();std=c.rolling(period,min_periods=period).std(ddof=0);return mid+mult*std,mid,mid-mult*std
def _range_levels(x,lookback=20):
    z=x.iloc[-lookback-1:-1] if len(x)>lookback else x.iloc[:-1];return num(z.high.max()),num(z.low.min())
def _equal_level(points,atr):
    if len(points)<2:return None
    a,b=points[-2][1],points[-1][1];return (a+b)/2 if abs(a-b)<=0.35*atr else None
def _result(eid,direction,anchor,evidence,score,trigger_sig):return {"status":"PASS","engine":eid,"strategy":ENGINE_NAMES[eid],"direction":direction,"setup_anchor":anchor,"evidence":evidence,"quality":float(max(0,min(100,score))),"trigger_signature":trigger_sig,"rejection_reasons":[]}
def _fail(eid,direction,reasons):return {"status":"FAIL","engine":eid,"strategy":ENGINE_NAMES[eid],"direction":direction,"rejection_reasons":reasons,"quality":0.0}

def evaluate_strategy(engine_id,m5,context,direction):
    eid=str(engine_id).upper();direction=str(direction).upper();x=m5.tail(100).reset_index(drop=True).copy()
    if len(x)<30:return _fail(eid,direction,["INSUFFICIENT_M5_CONTEXT"])
    a=_atr(x);last=_with_location(candle_metrics(x.iloc[-1]));prev=_with_location(candle_metrics(x.iloc[-2]));s=structure(x,min(80,len(x)));reg=context.get("regime","RANGE");highs,lows=_pivots(x)
    if eid=="E1":
        if not _trend_filter_ok(context,direction):return _fail(eid,direction,["MTF_TREND_FILTER_FAILED"])
        e9=ema(x,9).iloc[-1];e20=ema(x,20).iloc[-1];recent_high=num(x.high.iloc[-8:-2].max());pullback_touch=(last["low"]<=e9+.15*a or last["low"]<=e20+.15*a) if direction=="BUY" else (last["high"]>=e9-.15*a or last["high"]>=e20-.15*a);pull_vol=num(pd.to_numeric(x.volume,errors="coerce").iloc[-2]/max(pd.to_numeric(x.volume,errors="coerce").iloc[-6:-2].mean(),1e-12)) if "volume" in x else 1.0;reversal=_bullish_reversal(last,prev) if direction=="BUY" else _bearish_reversal(last,prev);context_ok=(direction=="BUY" and recent_high>=num(x.high.iloc[-1])) or (direction=="SELL" and recent_high<=num(x.high.iloc[-1]));ok=pullback_touch and reversal and pull_vol<1.0 and s["bias"]==direction and context_ok;return _result(eid,direction,e20,{"ema9":num(e9),"ema20":num(e20),"pullback_volume_ratio":pull_vol,"structure":s},90,"E1|pullback-reversal|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["IMPULSE_PULLBACK_CONTINUATION_FAILED"])
    if eid=="E2":
        if not _trend_filter_ok(context,direction):return _fail(eid,direction,["MTF_TREND_FILTER_FAILED"])
        e50=ema(x,50).iloc[-1];rsi=num(_rsi(x).iloc[-1],50);fib_ok=False;fib50=fib618=fib786=None
        if direction=="BUY" and highs and lows:
            hi_i,hi=highs[-1];prior_lows=[p for p in lows if p[0]<hi_i]
            if prior_lows:
                lo_i,lo=prior_lows[-1];rng=hi-lo;fib50=hi-rng*.50;fib618=hi-rng*.618;fib786=hi-rng*.786;fib_ok=fib618<=last["low"]<=fib50 or abs(last["close"]-e50)<=.35*a
        elif direction=="SELL" and highs and lows:
            lo_i,lo=lows[-1];prior_highs=[p for p in highs if p[0]<lo_i]
            if prior_highs:
                hi_i,hi=prior_highs[-1];rng=hi-lo;fib50=lo+rng*.50;fib618=lo+rng*.618;fib786=lo+rng*.786;fib_ok=fib50<=last["high"]<=fib618 or abs(last["close"]-e50)<=.35*a
        rsi_ok=(40<=rsi<=45) if direction=="BUY" else (55<=rsi<=60);reversal=_bullish_reversal(last,prev) if direction=="BUY" else _bearish_reversal(last,prev);ok=fib_ok and (rsi_ok or abs(last["close"]-e50)<=.35*a) and reversal and s["bias"]==direction;return _result(eid,direction,e50,{"ema50":num(e50),"rsi14":rsi,"fib50":fib50,"fib618":fib618,"fib786":fib786},88,"E2|deep-pullback|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["TREND_PULLBACK_CONTINUATION_FAILED"])
    if eid=="E3":
        if reg!="TRANSITION":return _fail(eid,direction,["TRANSITION_FILTER_FAILED"])
        rh,rl=_range_levels(x,20);close_break=last["close"]>rh if direction=="BUY" else last["close"]<rl;vr=_volume_ratio(x);ok=_e3_breakout_ok(close_break=close_break,volume_ratio=vr);anchor=rh if direction=="BUY" else rl;return _result(eid,direction,anchor,{"range_high":rh,"range_low":rl,"volume_ratio":vr,"range_width":rh-rl},86,"E3|range-break|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["RANGE_BREAK_EXPANSION_FAILED"])
    if eid=="E4":
        if reg!="TRANSITION":return _fail(eid,direction,["TRANSITION_FILTER_FAILED"])
        if context.get("h1_bias") in ("BUY","SELL") and context.get("h1_bias")!=direction:return _fail(eid,direction,["H1_DIRECTION_FILTER_FAILED"])
        rh,rl=_range_levels(x,20);level=rh if direction=="BUY" else rl;prior=x.iloc[-8:-1];broken=bool((prior.close>level).any()) if direction=="BUY" else bool((prior.close<level).any());touched=last["low"]<=level+.20*a and last["close"]>=level if direction=="BUY" else last["high"]>=level-.20*a and last["close"]<=level;rejection=_bullish_reversal(last,prev) if direction=="BUY" else _bearish_reversal(last,prev);ok=broken and touched and rejection;return _result(eid,direction,level,{"retest_level":level,"broken":broken,"retest_touched":touched,"atr":a},88,"E4|break-retest|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["BREAK_RETEST_CONTINUATION_FAILED"])
    if eid=="E5":
        if not _trend_filter_ok(context,direction):return _fail(eid,direction,["MTF_TREND_FILTER_FAILED"])
        body_atr=last["body"]/max(a,1e-12);vr=_volume_ratio(x);marubozu=last["body_ratio"]>=.80 and max(last["upper_wick"],last["lower_wick"])<=.15*last["range"];ok=_e5_momentum_ok(body_atr=body_atr,volume_ratio=vr,marubozu=marubozu) and ((direction=="BUY" and last["bull"]) or (direction=="SELL" and last["bear"]));return _result(eid,direction,last["high"] if direction=="BUY" else last["low"],{"body_atr":body_atr,"volume_ratio":vr,"marubozu":marubozu},84,"E5|momentum-expansion|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["MOMENTUM_EXPANSION_FAILED"])
    if eid=="E6":
        if reg!="RANGE" or (context.get("m15_context",{}).get("adx14",context.get("adx14",99)) or 99)>=20:return _fail(eid,direction,["RANGE_FILTER_FAILED"])
        upper,mid,lower=_bollinger(x,20,2.5);u=num(upper.iloc[-1]);m=num(mid.iloc[-1]);lo=num(lower.iloc[-1]);rsi=num(_rsi(x).iloc[-1],50);ok=(last["low"]<=lo and rsi<25 and _bullish_reversal(last,prev)) if direction=="BUY" else (last["high"]>=u and rsi>75 and _bearish_reversal(last,prev));return _result(eid,direction,m,{"bb_upper":u,"bb_mid":m,"bb_lower":lo,"rsi14":rsi},82,"E6|extreme-rejection|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["EXTREME_REJECTION_MEAN_RETURN_FAILED"])
    if eid=="E7":
        if reg not in ("RANGE","TRANSITION"):return _fail(eid,direction,["RANGE_TRANSITION_FILTER_FAILED"])
        if direction=="BUY":
            level=_equal_level(lows,a);sweep=level is not None and prev["low"]<level and prev["close"]>level and prev["lower_wick"]>=prev["body"]*.8;confirm=last["bull"] and last["close"]>prev["close"]
        else:
            level=_equal_level(highs,a);sweep=level is not None and prev["high"]>level and prev["close"]<level and prev["upper_wick"]>=prev["body"]*.8;confirm=last["bear"] and last["close"]<prev["close"]
        ok=level is not None and sweep and confirm;return _result(eid,direction,level,{"equal_level":level,"sweep":sweep,"confirmation":confirm},86,"E7|liquidity-sweep|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["SWEEP_REJECTION_REVERSAL_FAILED"])
    if eid=="E8":
        if reg!="RANGE":return _fail(eid,direction,["RANGE_FILTER_FAILED"])
        rh,rl=_range_levels(x,30);tol=.30*a;touches_low=sum(abs(num(v)-rl)<=tol for v in x.low.iloc[:-1]);touches_high=sum(abs(num(v)-rh)<=tol for v in x.high.iloc[:-1]);double_bottom=(len(lows)>=2 and abs(lows[-1][1]-lows[-2][1])<=tol and last["close"]>max(prev["high"],num(x.high.iloc[-4:-1].max())));double_top=(len(highs)>=2 and abs(highs[-1][1]-highs[-2][1])<=tol and last["close"]<min(prev["low"],num(x.low.iloc[-4:-1].min())));rejection=(direction=="BUY" and touches_low>=3 and (double_bottom or _bullish_reversal(last,prev))) or (direction=="SELL" and touches_high>=3 and (double_top or _bearish_reversal(last,prev)));return _result(eid,direction,rl if direction=="BUY" else rh,{"range_high":rh,"range_low":rl,"support_tests":touches_low,"resistance_tests":touches_high,"double_bottom":double_bottom,"double_top":double_top},80,"E8|range-rejection|%s|%s"%(direction,last["close"])) if rejection else _fail(eid,direction,["RANGE_REJECTION_FAILED"])
    return _fail(eid,direction,["UNKNOWN_ENGINE"])

def score_setup(result,regime,rr=None):
    if result.get("status")!="PASS":return {"score":0.0,"qualified":False,"components":{}}
    ev=result.get("evidence") or {};score=55.0;components={"setup_and_trigger":55.0};engine=result.get("engine")
    if ev.get("volume_ratio",0)>=1.5:score+=10;components["volume"]=10
    if ev.get("body_atr",0)>=2.5:score+=10;components["volatility"]=10
    regime_fit=(regime=="TREND" and engine in ("E1","E2","E5")) or (regime=="RANGE" and engine in ("E6","E7","E8")) or (regime=="TRANSITION" and engine in ("E3","E4","E7"))
    if regime_fit:score+=15;components["regime_fit"]=15
    if rr is not None and rr>=1.5:score+=10;components["rr"]=10
    score=min(100.0,score);return {"score":round(score,2),"qualified":score>=70,"components":components}

def sort_setup_candidates(candidates):
    return sorted(candidates,key=lambda r:(ENGINE_PRIORITY.get(str(r.get("engine")).upper(),99),-float(r.get("score_detail",{}).get("score",0) or 0),-float(r.get("quality",0) or 0)))

def evaluate_all_allowed(m5,context):
    engines=context.get("allowed_engines",[]);directions=_candidate_directions(context);out=[]
    for eid in engines:
        for direction in directions:
            result=evaluate_strategy(eid,m5,context,direction)
            if result.get("status")=="PASS":result["score_detail"]=score_setup(result,context.get("regime","RANGE"));out.append(result)
    return sort_setup_candidates(out)

def evaluate_all_allowed_with_trace(m5,context):
    engines=context.get("allowed_engines",[]);directions=_candidate_directions(context);trace=[];candidates=[]
    for eid in engines:
        for direction in directions:
            result=evaluate_strategy(eid,m5,context,direction);trace.append(result)
            if result.get("status")=="PASS":result["score_detail"]=score_setup(result,context.get("regime","RANGE"));candidates.append(result)
    return sort_setup_candidates(candidates),trace

def enrich_selected(result,symbol,regime,candle_time):
    anchor=result.get("setup_anchor");setup_id=build_setup_id(symbol,regime,result["engine"],result["direction"],anchor);trigger=build_trigger_id(result["engine"],result["direction"],candle_time,result.get("trigger_signature",""));return {**result,"setup_id":setup_id,"trigger_id":trigger,"regime":regime,"symbol":symbol}
