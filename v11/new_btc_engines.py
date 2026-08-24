from __future__ import annotations

import math
import pandas as pd

from .common import atr14, ema

BTC_NEW_ENGINE_NAMES={
    "B1":"RANGE_SWEEP_DISPLACEMENT",
    "B2":"HTF_OB_M5_FVG_RETEST",
    "B3":"VOLATILITY_EXPANSION_BREAKOUT_RETEST",
}
BTC_NEW_ENGINE_MIN_RR={"B1":2.0,"B2":3.0,"B3":1.5}


def _n(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def _body(c):return abs(_n(c.close)-_n(c.open))
def _rng(c):return max(_n(c.high)-_n(c.low),1e-12)
def _bull(c):return _n(c.close)>_n(c.open)
def _bear(c):return _n(c.close)<_n(c.open)

def _atr(x):
    a=atr14(x).dropna() if x is not None and not x.empty else pd.Series(dtype=float)
    return _n(a.iloc[-1],1.0) if len(a) else max(_n((x.high-x.low).tail(14).mean(),1.0),1e-12)

def _pivots(x,span=2):
    hs=[];ls=[]
    for i in range(span,len(x)-span):
        if _n(x.high.iloc[i])>=_n(x.high.iloc[i-span:i+span+1].max()):hs.append((i,_n(x.high.iloc[i])))
        if _n(x.low.iloc[i])<=_n(x.low.iloc[i-span:i+span+1].min()):ls.append((i,_n(x.low.iloc[i])))
    return hs,ls

def _fvg(x,i,direction):
    if i<2:return None
    a,c=x.iloc[i-2],x.iloc[i]
    if direction=="BUY" and _n(c.low)>_n(a.high):
        return {"bottom":_n(a.high),"top":_n(c.low),"ce":(_n(a.high)+_n(c.low))/2,"index":i,"type":"BULLISH_FVG"}
    if direction=="SELL" and _n(c.high)<_n(a.low):
        return {"bottom":_n(c.high),"top":_n(a.low),"ce":(_n(a.low)+_n(c.high))/2,"index":i,"type":"BEARISH_FVG"}
    return None

def _latest_fvg(x,direction,start=2,end=None):
    end=len(x) if end is None else min(end,len(x))
    for i in range(end-1,max(2,start)-1,-1):
        f=_fvg(x,i,direction)
        if f:return f
    return None

def _fail(eid,direction,reason,e=None):
    return {"status":"FAIL","engine":eid,"strategy":BTC_NEW_ENGINE_NAMES[eid],"direction":direction,"quality":0.0,"rejection_reasons":[reason],"evidence":e or {}}

def _pass(eid,direction,e,quality,entry_type):
    return {"status":"PASS","engine":eid,"strategy":BTC_NEW_ENGINE_NAMES[eid],"direction":direction,"setup_anchor":e.get("setup_anchor"),"evidence":e,"quality":float(quality),"trigger_signature":f"{eid}|{direction}|{e.get('entry_price')}","entry_type_hint":entry_type,"rejection_reasons":[]}

def _rr(entry,sl,tp,direction):
    risk=abs(entry-sl);reward=(tp-entry) if direction=="BUY" else (entry-tp)
    return reward/max(risk,1e-12)


def _b1(x,direction):
    if len(x)<50:return _fail("B1",direction,"INSUFFICIENT_M5_RANGE_CONTEXT")
    look=48;z=x.iloc[-look-1:-1];rh,rl=_n(z.high.max()),_n(z.low.min());a=_atr(x)
    sweep=None
    for i in range(len(x)-2,max(2,len(x)-18),-1):
        c=x.iloc[i]
        if direction=="BUY" and _n(c.low)<rl and _n(c.close)>rl:sweep=(i,c);break
        if direction=="SELL" and _n(c.high)>rh and _n(c.close)<rh:sweep=(i,c);break
    if not sweep:return _fail("B1",direction,"RANGE_SWEEP_FAILED",{"range_high":rh,"range_low":rl})
    si,sc=sweep;hs,ls=_pivots(x.iloc[:si].reset_index(drop=True),2);internal=hs[-1][1] if direction=="BUY" and hs else ls[-1][1] if direction=="SELL" and ls else None
    if internal is None:return _fail("B1",direction,"MSS_SWING_NOT_FOUND")
    ci=next((i for i in range(si+1,len(x)-1) if (_n(x.iloc[i].close)>internal and _bull(x.iloc[i])) if direction=="BUY" else (_n(x.iloc[i].close)<internal and _bear(x.iloc[i]))),None)
    if ci is None:return _fail("B1",direction,"MSS_DISPLACEMENT_FAILED")
    avg=_n(pd.Series([_body(x.iloc[i]) for i in range(max(0,ci-20),ci)]).mean(),1.0)
    if _body(x.iloc[ci])<max(avg*1.5,.8*a):return _fail("B1",direction,"DISPLACEMENT_TOO_WEAK")
    fvg=_latest_fvg(x,direction,si+1,ci+1)
    if not fvg:return _fail("B1",direction,"NO_FVG_NO_TRADE")
    entry=fvg["ce"];sl=_n(sc.low)-.15*a if direction=="BUY" else _n(sc.high)+.15*a;tp=rh if direction=="BUY" else rl;rr=_rr(entry,sl,tp,direction)
    if rr<2.0:return _fail("B1",direction,"RR_BELOW_2",{"risk_reward":rr})
    return _pass("B1",direction,{"range_high":rh,"range_low":rl,"sweep_index":si,"sweep_low":_n(sc.low) if direction=="BUY" else None,"sweep_high":_n(sc.high) if direction=="SELL" else None,"mss_level":internal,"mss_index":ci,"fvg":fvg,"entry_price":entry,"sl_price":sl,"tp_price":tp,"risk_reward":rr,"setup_anchor":rl if direction=="BUY" else rh},94,"LIMIT")


def _htf_ob(frame,direction):
    if frame is None or len(frame)<20:return None
    x=frame.tail(100).reset_index(drop=True);avg=max(_n(pd.Series([_body(x.iloc[i]) for i in range(max(0,len(x)-21),len(x)-1)]).mean(),1.0),1e-12)
    for i in range(len(x)-3,1,-1):
        c=x.iloc[i];n=x.iloc[i+1]
        if direction=="BUY" and _bear(c) and _bull(n) and _body(n)>=avg*1.5:return {"low":_n(c.low),"high":_n(c.open),"index":i,"type":"BULLISH_OB"}
        if direction=="SELL" and _bull(c) and _bear(n) and _body(n)>=avg*1.5:return {"low":_n(c.open),"high":_n(c.high),"index":i,"type":"BEARISH_OB"}
    return None

def _touched(frame,zone):
    if frame is None or frame.empty or not zone:return False
    z=frame.tail(8);return bool((_n(z.low.min())<=zone["high"]) and (_n(z.high.max())>=zone["low"]))

def _b2(x,m15,h1,direction):
    if len(x)<40:return _fail("B2",direction,"INSUFFICIENT_M5_CONTEXT")
    ob1,ob4=_htf_ob(h1,direction),_htf_ob(m15,direction)
    zone=ob1 or ob4
    if not zone:return _fail("B2",direction,"HTF_OB_NOT_FOUND")
    htf= h1 if ob1 else m15
    if not _touched(x,zone):return _fail("B2",direction,"HTF_OB_NOT_TOUCHED")
    if bool(zone.get("index") is not None and zone.get("index")>=len(htf)-2):return _fail("B2",direction,"HTF_OB_NOT_CONFIRMED")
    # The latest M5 sweep/CHoCH must occur after price entered the HTF OB.
    hs,ls=_pivots(x,2);fvg=_latest_fvg(x,direction,max(2,len(x)-18),len(x))
    if not fvg:return _fail("B2",direction,"M5_FVG_REQUIRED")
    if direction=="BUY":
        sweep=next((i for i in range(len(x)-2,max(2,len(x)-18),-1) if _n(x.iloc[i].low)<_n(x.low.iloc[max(0,i-8):i].min()) and _n(x.iloc[i].close)>_n(x.low.iloc[max(0,i-8):i].min())),None)
        level=hs[-1][1] if hs else None;choch=level is not None and _n(x.close.iloc[-1])>level;entry=fvg["ce"];sl=_n(x.low.iloc[max(0,fvg["index"]-2):fvg["index"]+1].min())-.15*_atr(x);tp=_n(h1.high.tail(60).max()) if h1 is not None and not h1.empty else entry+4*_atr(x)
    else:
        sweep=next((i for i in range(len(x)-2,max(2,len(x)-18),-1) if _n(x.iloc[i].high)>_n(x.high.iloc[max(0,i-8):i].max()) and _n(x.iloc[i].close)<_n(x.high.iloc[max(0,i-8):i].max())),None)
        level=ls[-1][1] if ls else None;choch=level is not None and _n(x.close.iloc[-1])<level;entry=fvg["ce"];sl=_n(x.high.iloc[max(0,fvg["index"]-2):fvg["index"]+1].max())+.15*_atr(x);tp=_n(h1.low.tail(60).min()) if h1 is not None and not h1.empty else entry-4*_atr(x)
    if sweep is None or not choch:return _fail("B2",direction,"M5_SWEEP_CHOCH_FAILED",{"sweep":sweep,"choch":choch})
    if direction=="BUY" and _n(x.low.iloc[-1])>fvg["top"]:return _fail("B2",direction,"M5_FVG_NOT_RETESTED")
    if direction=="SELL" and _n(x.high.iloc[-1])<fvg["bottom"]:return _fail("B2",direction,"M5_FVG_NOT_RETESTED")
    rr=_rr(entry,sl,tp,direction)
    if rr<3.0:return _fail("B2",direction,"RR_BELOW_3",{"risk_reward":rr})
    return _pass("B2",direction,{"htf_ob":zone,"htf_timeframe":"1H" if ob1 else "4H","m5_sweep_index":sweep,"m5_choch_level":level,"fvg":fvg,"entry_price":entry,"sl_price":sl,"tp_price":tp,"risk_reward":rr,"setup_anchor":zone["low"]},93,"LIMIT")


def _bb(x,n=20):
    c=pd.to_numeric(x.close,errors="coerce");mid=c.rolling(n).mean();sd=c.rolling(n).std(ddof=0);return mid,mid+2*sd,mid-2*sd

def _b3(x,direction):
    if len(x)<50:return _fail("B3",direction,"INSUFFICIENT_M5_CONTEXT")
    mid,upper,lower=_bb(x);a=_atr(x);width=(upper-lower)/mid.replace(0,pd.NA);sq=width.iloc[-10:-2]
    if len(sq)==0 or _n(sq.min(),99) > _n(width.iloc[-30:-10].quantile(.35),0):return _fail("B3",direction,"BB_SQUEEZE_NOT_CONFIRMED")
    e20=ema(x,20);e50=ema(x,50);avg_vol=_n(pd.to_numeric(x.volume.iloc[-21:-1],errors="coerce").mean(),0) if "volume" in x else 0;v=_n(x.volume.iloc[-1],0) if "volume" in x else 0
    c=x.iloc[-1]
    if direction=="BUY":
        resistance=_n(x.high.iloc[-25:-1].max());breakout=_bull(c) and _n(c.close)>_n(upper.iloc[-1]) and _n(c.close)>resistance;align=_n(e20.iloc[-1])>=_n(e50.iloc[-1]);
    else:
        resistance=_n(x.low.iloc[-25:-1].min());breakout=_bear(c) and _n(c.close)<_n(lower.iloc[-1]) and _n(c.close)<resistance;align=_n(e20.iloc[-1])<=_n(e50.iloc[-1])
    if not align:return _fail("B3",direction,"EMA_ALIGNMENT_FAILED")
    if not breakout or (avg_vol>0 and v<avg_vol*1.5):return _fail("B3",direction,"EXPANSION_VOLUME_BREAKOUT_FAILED",{"volume_ratio":v/max(avg_vol,1e-12) if avg_vol else None})
    # Retest must be represented by the latest closed candle after a prior breakout.
    prior=x.iloc[-2]; level=resistance
    if direction=="BUY":retest=_n(prior.low)<=level or _n(prior.low)<=_n(mid.iloc[-2]);trigger=_bull(c) and _n(c.close)>level;sl=_n(prior.low)-.1*a
    else:retest=_n(prior.high)>=level or _n(prior.high)>=_n(mid.iloc[-2]);trigger=_bear(c) and _n(c.close)<level;sl=_n(prior.high)+.1*a
    if not retest:return _fail("B3",direction,"RETEST_NOT_CONFIRMED")
    if not trigger:return _fail("B3",direction,"TRIGGER_CANDLE_FAILED")
    entry=_n(c.close);tp=entry+1.5*abs(entry-sl) if direction=="BUY" else entry-1.5*abs(entry-sl);rr=_rr(entry,sl,tp,direction)
    return _pass("B3",direction,{"bb_mid":_n(mid.iloc[-1]),"bb_upper":_n(upper.iloc[-1]),"bb_lower":_n(lower.iloc[-1]),"ema20":_n(e20.iloc[-1]),"ema50":_n(e50.iloc[-1]),"breakout_level":level,"volume_ratio":v/max(avg_vol,1e-12) if avg_vol else None,"entry_price":entry,"sl_price":sl,"tp_price":tp,"risk_reward":rr,"setup_anchor":level},90,"MARKET")


BTC_NEW_REGISTRY={"B1":_b1,"B2":_b2,"B3":_b3}

def evaluate_new_btc_engines(m5,m15=None,h1=None):
    x=m5.tail(140).reset_index(drop=True).copy();out=[];trace=[]
    for eid,fn in (("B1",lambda d:_b1(x,d)),("B2",lambda d:_b2(x,m15,h1,d)),("B3",lambda d:_b3(x,d))):
        for direction in ("BUY","SELL"):
            try:item=fn(direction)
            except Exception as exc:item=_fail(eid,direction,f"ENGINE_ERROR:{type(exc).__name__}:{exc}")
            trace.append(item)
            if item["status"]=="PASS":
                item["score_detail"]={"score":item["quality"],"qualified":True,"components":{"btc_new_engine_quality":item["quality"]}}
                out.append(item)
    out.sort(key=lambda z:(int(str(z["engine"])[1:]),-z.get("quality",0)))
    return out,trace
