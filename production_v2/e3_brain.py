from __future__ import annotations
from statistics import mean
from typing import Any

QUESTION="What is price structure communicating?"
ARCHITECTURE="E3_SINGLE_PROFESSIONAL_BRAIN_V61_CAUSAL_CONTRACT"
UP,DOWN,NEUTRAL,MIXED="UP","DOWN","NEUTRAL","MIXED"
MIN_CANDLES=40; IR,ER=2,5; PROMINENCE_ATR=.10; EQ_TOLERANCE_ATR=.08; SWEEP_MIN_ATR=.10; RECLAIM_MIN_ATR=.05

def _num(v:Any):
    try:
        x=float(v); return x if x==x and abs(x)!=float("inf") else None
    except (TypeError,ValueError): return None

def _clean(bars):
    out=[];reasons=[]
    for i,b in enumerate(bars or []):
        if not isinstance(b,dict): reasons.append(f"bar_{i}_not_mapping");continue
        v=[_num(b.get(k)) for k in ("open","high","low","close")]
        if any(x is None for x in v): reasons.append(f"bar_{i}_ohlc_invalid");continue
        o,h,l,c=v
        if h<max(o,c) or l>min(o,c) or h<l: reasons.append(f"bar_{i}_ohlc_inconsistent");continue
        out.append({"open":o,"high":h,"low":l,"close":c})
    return out,reasons

def _tr(b,i):
    if i<=0:return b[i]["high"]-b[i]["low"] if b else 0
    x,p=b[i],b[i-1]["close"]
    return max(x["high"]-x["low"],abs(x["high"]-p),abs(x["low"]-p))

def _atr(b,p=14,end=None):
    if not b:return 0
    end=len(b)-1 if end is None else min(end,len(b)-1)
    return mean(_tr(b,i) for i in range(max(1,end-p+1),end+1)) if end>=1 else 0

def _pivots(b,side,radius):
    out=[]
    for i in range(radius,len(b)-radius):
        x=b[i][side];L=[b[j][side] for j in range(i-radius,i)];R=[b[j][side] for j in range(i+1,i+radius+1)];pr=PROMINENCE_ATR*max(_atr(b,14,i),1e-12)
        ok=(x>=max(L) and x>max(R) and min(x-max(L),x-max(R))>=pr) if side=="high" else (x<=min(L) and x<min(R) and min(min(L)-x,min(R)-x)>=pr)
        if ok:out.append((i,x,i+radius))
    return out

def _pivot_records(raw,current):
    out=[]
    for x in raw or []:
        if not isinstance(x,(tuple,list)) or len(x)!=3:continue
        try:i,p,ci=int(x[0]),float(x[1]),int(x[2])
        except (TypeError,ValueError):continue
        if ci<=current:out.append({"index":i,"price":round(p,8),"confirmation_index":ci,"status":"CONFIRMED"})
    return out

def _compress(points,atr,spacing=2):
    out=[];tol=max(atr*EQ_TOLERANCE_ATR,1e-12)
    for p in points:
        if not out or p["index"]-out[-1]["index"]>=spacing:out.append(p);continue
        if abs(p["price"]-out[-1]["price"])<=tol and p["confirmation_index"]>=out[-1]["confirmation_index"]:out[-1]=p
    return out

def _label(hs,ls,atr):
    tol=max(atr*EQ_TOLERANCE_ATR,1e-12);H=[];L=[];prev=None
    for p in hs:
        z="SWING_HIGH" if prev is None else "EQH" if abs(p["price"]-prev[1])<=tol else "HH" if p["price"]>prev[1] else "LH";H.append({**p,"label":z});prev=(p["index"],p["price"])
    prev=None
    for p in ls:
        z="SWING_LOW" if prev is None else "EQL" if abs(p["price"]-prev[1])<=tol else "HL" if p["price"]>prev[1] else "LL";L.append({**p,"label":z});prev=(p["index"],p["price"])
    return H,L

def _latest(xs,labels):
    for x in reversed(xs or []):
        if x.get("label") in labels:return x
    return None

def _semantic(h,l):
    ev=sorted([x for x in h+l if x.get("label") in {"HH","HL","LH","LL"}],key=lambda x:(x["index"],0 if x["label"] in {"HH","LH"} else 1));s=NEUTRAL;lh=ll=None;t=[]
    for x in ev:
        if x["label"] in {"HH","LH"}:lh=x
        else:ll=x
        s=UP if lh and ll and lh["label"]=="HH" and ll["label"]=="HL" else DOWN if lh and ll and lh["label"]=="LH" and ll["label"]=="LL" else MIXED if lh and ll else NEUTRAL
        t.append({"index":x["index"],"label":x["label"],"state_after":s})
    return {"state":s,"basis":"ORDERED_CAUSAL_SWING_RELATIONSHIPS","counts_used_as_authority":False,"latest_directional_event":ev[-1] if ev else None,"latest_hh":_latest(h,{"HH"}),"latest_hl":_latest(l,{"HL"}),"latest_lh":_latest(h,{"LH"}),"latest_ll":_latest(l,{"LL"}),"bullish_pair":bool(lh and ll and lh["label"]=="HH" and ll["label"]=="HL"),"bearish_pair":bool(lh and ll and lh["label"]=="LH" and ll["label"]=="LL"),"structural_sequence":"→".join(x["label"] for x in ev[-12:]),"transitions":t[-12:],"semantic_rule":"ORDERED_SWINGS_ONLY;CONFIRMED_PIVOTS_ONLY;COUNTS_DESCRIPTIVE_ONLY;NEWER_CONFIRMED_LEG_HAS_AUTHORITY"}

def _protected(h,l,s):
    if s==UP:return {"protected_high":_latest(h,{"HH"}),"protected_low":_latest(l,{"HL"}),"logic":"latest_confirmed_HL_protects_bullish_structure"}
    if s==DOWN:return {"protected_high":_latest(h,{"LH"}),"protected_low":_latest(l,{"LL"}),"logic":"latest_confirmed_LH_protects_bearish_structure"}
    return {"protected_high":None,"protected_low":None,"logic":"NO_CLEAR_DIRECTIONAL_PROTECTED_PAIR"}

def _break(bars,h,l,atr,s,idx):
    hs=[x for x in h if x["confirmation_index"]<=idx-1];ls=[x for x in l if x["confirmation_index"]<=idx-1];cand=[];H=_latest(hs,{"HH","LH"});L=_latest(ls,{"HL","LL"})
    if H and bars[idx]["close"]>H["price"]:cand.append({"event":"BOS_UP","direction":UP,"level":H["price"],"structure_index":H["index"]})
    if L and bars[idx]["close"]<L["price"]:cand.append({"event":"BOS_DOWN","direction":DOWN,"level":L["price"],"structure_index":L["index"]})
    if not cand:return {"event":"NO_BREAK","direction":NEUTRAL,"confirmed":False,"closed_candle_confirmed":True,"scope":"EXTERNAL"}
    x=max(cand,key=lambda z:abs(bars[idx]["close"]-z["level"]));old=s.get("state",NEUTRAL);chg=(old==DOWN and x["direction"]==UP) or (old==UP and x["direction"]==DOWN)
    return {**x,"event":"CHOCH" if chg else x["event"],"confirmed":True,"closed_candle_confirmed":True,"break_candle_index":idx,"distance_atr":round(abs(bars[idx]["close"]-x["level"])/max(atr,1e-12),4),"scope":"EXTERNAL"}

def _failure(e,b,atr):
    if not e.get("confirmed"):return {"event":"NO_FAILURE","confirmed":False,"current":False}
    i,L,d=e["break_candle_index"],e["level"],e["direction"];f=i+1<len(b) and ((d==UP and b[i+1]["close"]<L) or (d==DOWN and b[i+1]["close"]>L))
    return {"event":"FAILED_BOS" if f else "NO_FAILURE","direction":DOWN if d==UP else UP,"confirmed":bool(f),"current":bool(f and i+1==len(b)-1),"closed_candle_confirmed":True,"level":L,"break_candle_index":i,"failure_candle_index":i+1 if f else None,"scope":"EXTERNAL","distance_atr":round(abs(b[i+1]["close"]-L)/max(atr,1e-12),4) if f else 0}

def _sweep(b,h,l,atr):
    if not b or atr<=0:return {"event":"NO_SWEEP_RECLAIM","direction":NEUTRAL,"confirmed":False,"lifecycle":"NONE","current":False}
    i=len(b)-1;found=[]
    for p,d,side in [(_latest(h,{"HH","LH","EQH"}),DOWN,"high"),(_latest(l,{"HL","LL","EQL"}),UP,"low")]:
        if not p or p["confirmation_index"]>i-1:continue
        sw=(b[i]["high"]-p["price"])/atr if side=="high" else (p["price"]-b[i]["low"])/atr;rc=(p["price"]-b[i]["close"])/atr if side=="high" else (b[i]["close"]-p["price"])/atr
        if sw>=SWEEP_MIN_ATR:
            st="RECLAIM" if rc>=RECLAIM_MIN_ATR else "SWEEP";found.append((max(0,rc),{"event":"SWEEP_RECLAIM" if st=="RECLAIM" else "SWEEP","direction":d,"confirmed":True,"closed_candle_confirmed":True,"current":True,"level":p["price"],"swing_index":p["index"],"sweep_candle_index":i,"sweep_distance_atr":round(sw,4),"reclaim_distance_atr":round(max(0,rc),4),"scope":"EXTERNAL","liquidity_type":"EQUAL_HIGH" if p["label"]=="EQH" else "EQUAL_LOW" if p["label"]=="EQL" else "STRUCTURAL_SWING","lifecycle":st}))
    return max(found,key=lambda x:x[0])[1] if found else {"event":"NO_SWEEP_RECLAIM","direction":NEUTRAL,"confirmed":False,"lifecycle":"NONE","current":False}

def analyze_e3(bars):
    clean,reasons=_clean(bars)
    if len(clean)<MIN_CANDLES:return {"engine":"E3","architecture":ARCHITECTURE,"question":QUESTION,"status":"INSUFFICIENT_DATA","decision_authority":"E9_ONLY","trade_decision":None,"data_quality":{"valid_bars":len(clean),"rejected":reasons}}
    i=len(clean)-1;atr=_atr(clean);H,L=_label(_compress(_pivot_records(_pivots(clean,"high",ER),i),atr),_compress(_pivot_records(_pivots(clean,"low",ER),i),atr),atr);IH,IL=_label(_compress(_pivot_records(_pivots(clean,"high",IR),i),atr),_compress(_pivot_records(_pivots(clean,"low",IR),i),atr),atr)
    ext=_semantic(H,L);inte=_semantic(IH,IL);bos=_break(clean,H,L,atr,ext,i);fail=_failure(bos,clean,atr);liq=_sweep(clean,H,L,atr);state=ext["state"]
    narrative={UP:"Bullish external structure is currently dominant; internal structure is context, not authority.",DOWN:"Bearish external structure is currently dominant; internal structure is context, not authority.",MIXED:"External structure is mixed; directional commitment is not structurally clean.",NEUTRAL:"No sufficiently clear directional external structure is confirmed."}[state]
    return {"engine":"E3","architecture":ARCHITECTURE,"question":QUESTION,"status":"OK","decision_authority":"E9_ONLY","trade_decision":None,"as_of_closed_candle":i,"causal":{"lookahead_allowed":False,"future_data_used":False,"confirmation_cutoff":i},"data_quality":{"valid_bars":len(clean),"rejected":reasons,"atr":round(atr,8)},"external_structure":ext,"internal_structure":inte,"protected_structure":_protected(H,L,state),"bos_choch":bos,"failed_break":fail,"liquidity":liq,"structure_lifecycle":{"current_structure":state,"bos_stage":"CONFIRMED" if bos.get("confirmed") else "NONE","failure_stage":"FAILED" if fail.get("confirmed") else "NONE","liquidity_stage":liq.get("lifecycle","NONE"),"last_confirmed_pivot_index":max([x["confirmation_index"] for x in H+L],default=None),"as_of_closed_candle":i},"narrative":narrative,"contract":{"return_type":"dict","tuple_normalized":True,"decision_owner":"E9"}}
