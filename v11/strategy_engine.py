from __future__ import annotations
import pandas as pd
from .common import num, ema, atr14, structure, candle_metrics
from .setup_state import build_setup_id, build_trigger_id
ENGINE_NAMES={"E1":"TREND","E2":"TREND_PULLBACK","E3":"BREAKOUT","E4":"BREAKOUT_RETEST","E5":"MOMENTUM","E6":"MEAN_REVERSION","E7":"LIQUIDITY_REVERSAL","E8":"RANGE"}
def _atr(x):
    a=atr14(x).dropna();return num(a.iloc[-1]) if len(a) else num((x.high-x.low).tail(14).mean(),1e-12)
def _pivots(x):
    highs=[];lows=[]
    for i in range(2,len(x)-2):
        if num(x.high.iloc[i])>=max(num(v) for v in x.high.iloc[i-2:i+3]):highs.append((i,num(x.high.iloc[i])))
        if num(x.low.iloc[i])<=min(num(v) for v in x.low.iloc[i-2:i+3]):lows.append((i,num(x.low.iloc[i])))
    return highs,lows
def _vwap(x):
    typ=(x.high+x.low+x.close)/3;vol=pd.to_numeric(x.get("volume",pd.Series(1.0,index=x.index)),errors="coerce").fillna(1).clip(lower=1e-9)
    if "datetime" in x:
        ts=pd.to_datetime(x.datetime,utc=True,errors="coerce");d=ts.dt.date;return (typ*vol).groupby(d).cumsum()/vol.groupby(d).cumsum()
    return (typ*vol).cumsum()/vol.cumsum()
def _volume_ratio(x):
    v=pd.to_numeric(x.get("volume",pd.Series(1.0,index=x.index)),errors="coerce").fillna(1);return num(v.iloc[-1]/max(num(v.tail(20).mean(),1e-12),1e-12))
def _confirm(x,direction):
    last=candle_metrics(x.iloc[-1]);prev=candle_metrics(x.iloc[-2]);return (last["bull"] and last["body_ratio"]>=.55 and last["close"]>prev["high"]) if direction=="BUY" else (last["bear"] and last["body_ratio"]>=.55 and last["close"]<prev["low"])
def _result(eid,direction,anchor,evidence,score,trigger_sig):return {"status":"PASS","engine":eid,"strategy":ENGINE_NAMES[eid],"direction":direction,"setup_anchor":anchor,"evidence":evidence,"quality":float(max(0,min(100,score))),"trigger_signature":trigger_sig}
def _fail(eid,direction,reasons):return {"status":"FAIL","engine":eid,"strategy":ENGINE_NAMES[eid],"direction":direction,"rejection_reasons":reasons,"quality":0.0}
def evaluate_strategy(engine_id,m5,context,direction):
    eid=str(engine_id).upper();direction=str(direction).upper();x=m5.tail(100).reset_index(drop=True).copy()
    if len(x)<30:return _fail(eid,direction,["INSUFFICIENT_M5_CONTEXT"])
    a=_atr(x);last=candle_metrics(x.iloc[-1]);prev=candle_metrics(x.iloc[-2]);s=structure(x,min(80,len(x)));reg=context.get("regime","RANGE")
    if eid=="E1":
        e20,e50,e200=ema(x,20).iloc[-1],ema(x,50).iloc[-1],ema(x,200).iloc[-1];adx=context.get("adx14") or 0;dip=context.get("di_plus") or 0;dim=context.get("di_minus") or 0
        ok=(direction=="BUY" and last["close"]>e20>e50>e200 and s["bias"]=="BUY" and adx>=25 and dip>dim) or (direction=="SELL" and last["close"]<e20<e50<e200 and s["bias"]=="SELL" and adx>=25 and dim>dip)
        return _result(eid,direction,last["close"],{"ema20":num(e20),"ema50":num(e50),"ema200":num(e200),"adx14":adx,"structure":s},82,"E1|structure|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["TREND_FILTER_FAILED"])
    highs,lows=_pivots(x)
    if eid=="E2":
        if not highs or not lows:return _fail(eid,direction,["NO_SWING_STRUCTURE"])
        e20=ema(x,20).iloc[-1];anchor=lows[-1][1] if direction=="BUY" else highs[-1][1];touched=(x.low.iloc[lows[-1][0]+1:].min()<=e20+.35*a) if direction=="BUY" else (x.high.iloc[highs[-1][0]+1:].max()>=e20-.35*a);impulse=abs(num(x.close.iloc[-1])-num(x.close.iloc[-min(6,len(x))]))>=a;ok=(context.get("direction") in (direction,"NEUTRAL")) and touched and impulse and _confirm(x,direction)
        return _result(eid,direction,anchor,{"ema20":num(e20),"atr":a,"impulse_atr":abs(last["close"]-num(x.close.iloc[-min(6,len(x))]))/max(a,1e-12)},86,"E2|continuation|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["IMPULSE_PULLBACK_CONTINUATION_FAILED"])
    if eid in ("E3","E4"):
        look=x.iloc[-21:-1] if len(x)>=22 else x.iloc[:-1];rh=num(look.high.max());rl=num(look.low.min())
        if eid=="E3":
            ok=(direction=="BUY" and last["close"]>rh and last["body_ratio"]>=.60 and _volume_ratio(x)>=1.2) or (direction=="SELL" and last["close"]<rl and last["body_ratio"]>=.60 and _volume_ratio(x)>=1.2);anchor=rh if direction=="BUY" else rl
            return _result(eid,direction,anchor,{"range_high":rh,"range_low":rl,"volume_ratio":_volume_ratio(x),"atr":a},84,"E3|break|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["RANGE_BREAK_EXPANSION_FAILED"])
        prior=x.iloc[-4:-1];touched=(num(prior.low.min())<=rh+.25*a and last["close"]>rh) if direction=="BUY" else (num(prior.high.max())>=rl-.25*a and last["close"]<rl);ok=touched and _confirm(x,direction);anchor=rh if direction=="BUY" else rl
        return _result(eid,direction,anchor,{"breakout_level":anchor,"retest_touched":touched,"atr":a},88,"E4|retest|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["BREAK_RETEST_CONTINUATION_FAILED"])
    if eid=="E5":
        av=atr14(x).dropna();atr_ratio=a/max(num(av.iloc[-6]),1e-12) if len(av)>=6 else 1;ok=last["body"]>=.70*a and last["body_ratio"]>=.65 and _volume_ratio(x)>=1.5 and atr_ratio>=1.05 and ((direction=="BUY" and last["bull"]) or (direction=="SELL" and last["bear"]))
        return _result(eid,direction,last["close"],{"body_atr":last["body"]/max(a,1e-12),"volume_ratio":_volume_ratio(x),"atr_expansion":atr_ratio},80,"E5|momentum|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["MOMENTUM_EXPANSION_FAILED"])
    vw=_vwap(x);v=num(vw.iloc[-1]);dist=abs(last["close"]-v)/max(a,1e-12)
    if eid=="E6":
        if reg=="TREND":return _fail(eid,direction,["MEAN_REVERSION_BLOCKED_IN_TREND"])
        rejection=(last["lower_wick"]>=last["body"]*.8 and last["close"]>last["open"]) if direction=="BUY" else (last["upper_wick"]>=last["body"]*.8 and last["close"]<last["open"]);ok=dist>=1.5 and rejection and ((direction=="BUY" and last["close"]<v) or (direction=="SELL" and last["close"]>v))
        return _result(eid,direction,v,{"vwap":v,"distance_atr":dist},78,"E6|rejection|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["EXTREME_REJECTION_MEAN_RETURN_FAILED"])
    if eid=="E7":
        level=lows[-1][1] if direction=="BUY" and lows else highs[-1][1] if direction=="SELL" and highs else None
        if level is None:return _fail(eid,direction,["NO_LIQUIDITY_LEVEL"])
        sweep=prev["low"]<level and prev["close"]>level if direction=="BUY" else prev["high"]>level and prev["close"]<level;rejection=prev["lower_wick"]>=max(prev["body"],.15*a) if direction=="BUY" else prev["upper_wick"]>=max(prev["body"],.15*a);ok=sweep and rejection and _confirm(x,direction)
        return _result(eid,direction,level,{"sweep_level":level,"atr":a},90,"E7|sweep-reversal|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["SWEEP_REJECTION_REVERSAL_FAILED"])
    if eid=="E8":
        rh=num(x.high.iloc[-21:-1].max());rl=num(x.low.iloc[-21:-1].min());anchor=rl if direction=="BUY" else rh;rejection=(last["low"]<=rl+.20*a and last["bull"] and last["lower_wick"]>=last["body"]*.5) if direction=="BUY" else (last["high"]>=rh-.20*a and last["bear"] and last["upper_wick"]>=last["body"]*.5);ok=reg=="RANGE" and rejection
        return _result(eid,direction,anchor,{"range_high":rh,"range_low":rl,"vwap":v},76,"E8|range-rejection|%s|%s"%(direction,last["close"])) if ok else _fail(eid,direction,["RANGE_REJECTION_FAILED"])
    return _fail(eid,direction,["UNKNOWN_ENGINE"])

def score_setup(result,regime,rr=None):
    if result.get("status")!="PASS":return {"score":0.0,"qualified":False,"components":{}}
    ev=result.get("evidence") or {};score=55.0;components={"setup_and_trigger":55.0};engine=result.get("engine")
    if ev.get("volume_ratio",0)>=1.2:score+=10;components["volume"]=10
    if ev.get("atr_expansion",0)>=1.05:score+=10;components["volatility"]=10
    regime_fit=(regime=="TREND" and engine in ("E1","E2","E3","E4","E5")) or (regime=="RANGE" and engine in ("E6","E7","E8")) or (regime=="TRANSITION" and engine in ("E3","E4","E7"))
    if regime_fit:score+=15;components["regime_fit"]=15
    if rr is not None and rr>=2:score+=10;components["rr"]=10
    score=min(100.0,score);return {"score":round(score,2),"qualified":score>=70,"components":components}

def evaluate_all_allowed(m5,context):
    engines=context.get("allowed_engines",[]);directions=[context.get("direction")] if context.get("direction") in ("BUY","SELL") else ["BUY","SELL"];out=[]
    for eid in engines:
        for direction in directions:
            result=evaluate_strategy(eid,m5,context,direction)
            if result.get("status")=="PASS":result["score_detail"]=score_setup(result,context.get("regime","RANGE"));out.append(result)
    out.sort(key=lambda r:(r.get("score_detail",{}).get("score",0),r.get("quality",0)),reverse=True);return out

def enrich_selected(result,symbol,regime,candle_time):
    anchor=result.get("setup_anchor");setup_id=build_setup_id(symbol,regime,result["engine"],result["direction"],anchor);trigger=build_trigger_id(result["engine"],result["direction"],candle_time,result.get("trigger_signature",""));return {**result,"setup_id":setup_id,"trigger_id":trigger,"regime":regime,"symbol":symbol}
