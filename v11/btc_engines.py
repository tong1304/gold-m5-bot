from __future__ import annotations
import math
from typing import Any
import pandas as pd
from .common import atr14

BTC_ENGINE_NAMES={"B1":"RANGE_SWEEP_DISPLACEMENT","B2":"HTF_ZONE_M5_FVG_RETEST","B3":"VOLATILITY_EXPANSION_BREAKOUT_RETEST"}
BTC_POINT_BUFFER=125.0
BTC_B1_RANGE_LOOKBACK=20
BTC_B1_SWING_LOOKBACK=8
BTC_FVG_MIN_POINTS=100.0
BTC_B3_BODY_MULT=2.0
BTC_B3_VOLUME_MULT=1.5

def _num(v,default=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else default
    except Exception:return default

def _body(c):return abs(_num(c.get("close"))-_num(c.get("open")))
def _rng(c):return max(_num(c.get("high"))-_num(c.get("low")),1e-12)
def _bull(c):return _num(c.get("close"))>_num(c.get("open"))
def _bear(c):return _num(c.get("close"))<_num(c.get("open"))
def _avg_body(x,n=20):
    if x is None or x.empty:return 0.0
    z=x.tail(n);return sum(_body(r) for _,r in z.iterrows())/max(len(z),1)
def _volume_ratio(x,n=20):
    if x is None or x.empty or "volume" not in x.columns:return 0.0
    v=pd.to_numeric(x.volume,errors="coerce").fillna(0.0);base=_num(v.iloc[:-1].tail(n).mean(),0.0) if len(v)>1 else 0.0
    return _num(v.iloc[-1],0.0)/max(base,1e-12)
def _atr(x):
    if x is None or x.empty:return 1.0
    a=atr14(x).dropna()
    return _num(a.iloc[-1],1.0) if len(a) else _num((x.high-x.low).tail(14).mean(),1.0)
def _range_levels(x,n=20):
    z=x.iloc[-n-1:-1] if len(x)>n else x.iloc[:-1]
    return (_num(z.high.max()),_num(z.low.min())) if not z.empty else (0.0,0.0)
def _swing_high(x,end,n=8):
    z=x.iloc[max(0,end-n):end];return _num(z.high.max()) if not z.empty else None
def _swing_low(x,end,n=8):
    z=x.iloc[max(0,end-n):end];return _num(z.low.min()) if not z.empty else None

def _bull_reversal(x):
    if len(x)<2:return False
    a,b=x.iloc[-1],x.iloc[-2];body=_body(a);lower=min(_num(a.open),_num(a.close))-_num(a.low)
    engulf=_bull(a) and _bear(b) and _num(a.open)<=_num(b.close) and _num(a.close)>=_num(b.open)
    pin=_bull(a) and lower>=max(body*1.5,_rng(a)*.45) and (_num(a.close)-_num(a.low))/_rng(a)>=.65
    return engulf or pin

def _bear_reversal(x):
    if len(x)<2:return False
    a,b=x.iloc[-1],x.iloc[-2];body=_body(a);upper=_num(a.high)-max(_num(a.open),_num(a.close))
    engulf=_bear(a) and _bull(b) and _num(a.open)>=_num(b.close) and _num(a.close)<=_num(b.open)
    pin=_bear(a) and upper>=max(body*1.5,_rng(a)*.45) and (_num(a.close)-_num(a.low))/_rng(a)<=.35
    return engulf or pin

def _fvg(a,c,direction,min_points=BTC_FVG_MIN_POINTS):
    if direction=="BUY":bottom=_num(c.high);top=_num(a.low)
    else:bottom=_num(a.high);top=_num(c.low)
    width=top-bottom
    return {"bottom":bottom,"top":top,"width":width,"type":"BULLISH_FVG" if direction=="BUY" else "BEARISH_FVG"} if width>=min_points else None

def _recent_fvg(x,direction,start,end=None,min_points=BTC_FVG_MIN_POINTS):
    end=len(x) if end is None else min(end,len(x))
    for i in range(end-1,max(start+1,2),-1):
        f=_fvg(x.iloc[i],x.iloc[i-2],direction,min_points)
        if f:f["index"]=i;return f
    return None

def _ob(x,direction,start,end):
    for i in range(end-1,start-1,-1):
        c=x.iloc[i]
        if direction=="BUY" and _bear(c):return {"low":_num(c.low),"high":_num(c.open),"type":"BULLISH_OB","index":i}
        if direction=="SELL" and _bull(c):return {"low":_num(c.open),"high":_num(c.high),"type":"BEARISH_OB","index":i}
    return None

def _htf_zone(frame,direction,n=60):
    if frame is None or len(frame)<8:return None
    x=frame.tail(n).reset_index(drop=True);avg=_avg_body(x.iloc[:-1],20)
    for i in range(len(x)-2,0,-1):
        c=x.iloc[i];q=x.iloc[i+1]
        if direction=="BUY" and _bear(c) and _bull(q) and _body(q)>=avg*1.5:return {"low":_num(c.low),"high":_num(c.open),"type":"BULLISH_OB","index":i}
        if direction=="SELL" and _bull(c) and _bear(q) and _body(q)>=avg*1.5:return {"low":_num(c.open),"high":_num(c.high),"type":"BEARISH_OB","index":i}
    return None

def _zone_touched(frame,zone):
    if frame is None or frame.empty or not zone:return False
    z=frame.tail(6);return bool((pd.to_numeric(z.low,errors="coerce")<=zone["high"]).any() and (pd.to_numeric(z.high,errors="coerce")>=zone["low"]).any())

def _result(eid,direction,anchor,evidence,quality,trigger,entry_type="MARKET"):
    return {"status":"PASS","engine":eid,"strategy":BTC_ENGINE_NAMES[eid],"direction":direction,"setup_anchor":anchor,"evidence":evidence,"quality":float(max(0,min(100,quality))),"trigger_signature":trigger,"entry_type_hint":entry_type,"rejection_reasons":[]}
def _fail(eid,direction,reason,evidence=None):
    r={"status":"FAIL","engine":eid,"strategy":BTC_ENGINE_NAMES[eid],"direction":direction,"quality":0.0,"rejection_reasons":[reason]}
    if evidence:r["evidence"]=evidence
    return r

def _b1(x,direction):
    if len(x)<30:return _fail("B1",direction,"INSUFFICIENT_M5_CONTEXT")
    rh,rl=_range_levels(x,20);sweep_i=None;sweep=None
    # Sweep is detected before the current closed trigger candle.
    for i in range(max(1,len(x)-12),len(x)-1):
        c=x.iloc[i]
        if direction=="BUY" and _num(c.low)<rl and _num(c.close)>rl:sweep_i,sweep=i,c
        if direction=="SELL" and _num(c.high)>rh and _num(c.close)<rh:sweep_i,sweep=i,c
    if sweep is None:return _fail("B1",direction,"RANGE_SWEEP_FAILED",{"range_high":rh,"range_low":rl})
    disp_i=None;swing=None;avg=max(_avg_body(x.iloc[max(0,sweep_i-20):sweep_i]),1e-12)
    for i in range(sweep_i+1,len(x)):
        c=x.iloc[i];swing=_swing_high(x,i,8) if direction=="BUY" else _swing_low(x,i,8)
        if swing is None:continue
        broke=_num(c.close)>swing if direction=="BUY" else _num(c.close)<swing
        momentum=_body(c)>=max(avg*1.5,_atr(x.iloc[:i+1])*.8)
        if broke and momentum and (_bull(c) if direction=="BUY" else _bear(c)):disp_i=i;break
    if disp_i is None:return _fail("B1",direction,"DISPLACEMENT_CHOCH_FAILED",{"sweep_index":sweep_i})
    fvg=_recent_fvg(x,direction,sweep_i+1,disp_i+1,0.0)
    if fvg and fvg["width"]<BTC_FVG_MIN_POINTS:fvg=None
    ob=_ob(x,direction,sweep_i+1,disp_i);zone=fvg or ob
    if zone is None:return _fail("B1",direction,"FVG_OR_ORDER_BLOCK_FAILED")
    entry=zone["top"] if direction=="BUY" else zone["bottom"]
    sl=_num(sweep.low)-BTC_POINT_BUFFER if direction=="BUY" else _num(sweep.high)+BTC_POINT_BUFFER
    risk=entry-sl if direction=="BUY" else sl-entry
    if risk<=0:return _fail("B1",direction,"INVALID_B1_RISK")
    rr_tp=entry+risk*1.5 if direction=="BUY" else entry-risk*1.5;struct_tp=rh if direction=="BUY" else rl
    tp=max(struct_tp,rr_tp) if direction=="BUY" else min(struct_tp,rr_tp);rr=(tp-entry)/risk if direction=="BUY" else (entry-tp)/risk
    return _result("B1",direction,rl if direction=="BUY" else rh,{"range_high":rh,"range_low":rl,"sweep_index":sweep_i,"sweep_low":_num(sweep.low) if direction=="BUY" else None,"sweep_high":_num(sweep.high) if direction=="SELL" else None,"choch_index":disp_i,"choch_swing":swing,"fvg":fvg,"order_block":ob,"zone":zone,"entry_price":entry,"sl_price":sl,"tp_price":tp,"risk_reward":rr,"point_buffer":BTC_POINT_BUFFER},94,f"B1|range-sweep-displacement|{direction}|{entry}","BUY_LIMIT" if direction=="BUY" else "SELL_LIMIT")

def _b2(x,m15,h1,direction):
    if len(x)<35:return _fail("B2",direction,"INSUFFICIENT_M5_CONTEXT")
    z15=_htf_zone(m15,direction);z1=_htf_zone(h1,direction)
    if not(_zone_touched(m15,z15) or _zone_touched(h1,z1)):return _fail("B2",direction,"HTF_OB_DEMAND_SUPPLY_NOT_TOUCHED",{"m15_zone":z15,"h1_zone":z1})
    fvg=_recent_fvg(x,direction,max(0,len(x)-12),len(x),BTC_FVG_MIN_POINTS)
    if fvg is None:return _fail("B2",direction,"M5_FVG_100_POINTS_FAILED")
    c=x.iloc[-1]
    if direction=="BUY":
        choch=(_swing_high(x,len(x)-1,8) is not None and _num(c.close)>_swing_high(x,len(x)-1,8));retest=_num(c.low)<=fvg["top"];confirm=_bull_reversal(x);sw=_swing_low(x,len(x),20)
        if not(choch and retest and confirm):return _fail("B2",direction,"HTF_ZONE_M5_FVG_RETEST_FAILED",{"choch":choch,"retest":retest,"confirmation":confirm,"fvg":fvg})
        entry=_num(c.close);sl=sw-BTC_POINT_BUFFER;struct_tp=_num(m15.high.tail(20).max()) if m15 is not None and not m15.empty else entry+abs(entry-sl)*2;tp=max(struct_tp,entry+abs(entry-sl)*2);rr=(tp-entry)/abs(entry-sl)
    else:
        choch=(_swing_low(x,len(x)-1,8) is not None and _num(c.close)<_swing_low(x,len(x)-1,8));retest=_num(c.high)>=fvg["bottom"];confirm=_bear_reversal(x);sw=_swing_high(x,len(x),20)
        if not(choch and retest and confirm):return _fail("B2",direction,"HTF_ZONE_M5_FVG_RETEST_FAILED",{"choch":choch,"retest":retest,"confirmation":confirm,"fvg":fvg})
        entry=_num(c.close);sl=sw+BTC_POINT_BUFFER;struct_tp=_num(m15.low.tail(20).min()) if m15 is not None and not m15.empty else entry-abs(entry-sl)*2;tp=min(struct_tp,entry-abs(entry-sl)*2);rr=(entry-tp)/abs(entry-sl)
    return _result("B2",direction,sw,{"htf_zone_m15":z15,"htf_zone_h1":z1,"m5_swing_low":sw if direction=="BUY" else None,"m5_swing_high":sw if direction=="SELL" else None,"m15_target":struct_tp,"fvg":fvg,"entry_price":entry,"sl_price":sl,"tp_price":tp,"risk_reward":rr,"point_buffer":BTC_POINT_BUFFER},92,f"B2|htf-zone-fvg-retest|{direction}|{entry}")

def _b3(x,direction):
    if len(x)<30:return _fail("B3",direction,"INSUFFICIENT_M5_CONTEXT")
    rh,rl=_range_levels(x,20);avg_body=max(_avg_body(x.iloc[:-1],20),1e-12);bo_i=None;bo=None
    for i in range(max(20,len(x)-8),len(x)-1):
        c=x.iloc[i];prior=x.iloc[max(0,i-20):i];av=_num(pd.to_numeric(prior.get("volume",pd.Series(1.0,index=prior.index)),errors="coerce").mean(),1.0);v=_num(c.get("volume",0))
        ok=(_num(c.close)>rh if direction=="BUY" else _num(c.close)<rl) and _body(c)>avg_body*BTC_B3_BODY_MULT and v>av*BTC_B3_VOLUME_MULT
        if ok:bo_i,bo=i,c;break
    if bo is None:return _fail("B3",direction,"VOLATILITY_EXPANSION_BREAKOUT_FAILED",{"resistance":rh,"support":rl})
    c=x.iloc[-1]
    if direction=="BUY":
        retest=_num(c.low)<=rh;confirm=_bull(c);fvg=_recent_fvg(x,"BUY",bo_i+1,len(x),0.0)
        if not(retest and confirm):return _fail("B3",direction,"BREAKOUT_RETEST_CONFIRMATION_FAILED",{"retest":retest,"confirmation":confirm,"breakout_index":bo_i})
        entry=_num(c.close);sl=min(_num(bo.low),_num(fvg["bottom"]) if fvg else _num(bo.low))-BTC_POINT_BUFFER;risk=entry-sl;tp=entry+risk*1.5
    else:
        retest=_num(c.high)>=rl;confirm=_bear(c);fvg=_recent_fvg(x,"SELL",bo_i+1,len(x),0.0)
        if not(retest and confirm):return _fail("B3",direction,"BREAKOUT_RETEST_CONFIRMATION_FAILED",{"retest":retest,"confirmation":confirm,"breakout_index":bo_i})
        entry=_num(c.close);sl=max(_num(bo.high),_num(fvg["top"]) if fvg else _num(bo.high))+BTC_POINT_BUFFER;risk=sl-entry;tp=entry-risk*1.5
    if risk<=0:return _fail("B3",direction,"INVALID_B3_RISK")
    return _result("B3",direction,rh if direction=="BUY" else rl,{"resistance":rh,"support":rl,"breakout_index":bo_i,"breakout_high":_num(bo.high),"breakout_low":_num(bo.low),"fvg":fvg,"volume_ratio":_volume_ratio(x),"entry_price":entry,"sl_price":sl,"tp_price":tp,"risk_reward":1.5,"point_buffer":BTC_POINT_BUFFER},90,f"B3|volatility-breakout-retest|{direction}|{entry}")

def evaluate_btc_engines(m5,m15=None,h1=None):
    x=m5.tail(100).reset_index(drop=True).copy();candidates=[];trace=[]
    for direction in ("BUY","SELL"):
        for eid,fn,args in (("B1",_b1,(x,direction)),("B2",_b2,(x,m15,h1,direction)),("B3",_b3,(x,direction))):
            r=fn(*args)
            if r["status"]=="PASS":
                candidates.append(r);trace.append(f"BTC {eid}:{direction}:PASS trigger={r.get('trigger_signature','')}")
            else:trace.append(f"BTC {eid}:{direction}:FAIL reason={(r.get('rejection_reasons') or ['UNKNOWN'])[0]}")
    return candidates,trace
