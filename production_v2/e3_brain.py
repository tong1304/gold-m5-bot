from __future__ import annotations
"""E3 — Professional Market Structure Brain.
Pure price-structure analysis. No E1/E2 decisions, gates or scores. E9 only trades."""
from statistics import mean
from typing import Any

QUESTION="What is price structure communicating?"
ARCHITECTURE="E3_SINGLE_PROFESSIONAL_BRAIN_V3"
UP,DOWN,NEUTRAL,MIXED="UP","DOWN","NEUTRAL","MIXED"
MIN_CANDLES=40
INTERNAL_RADIUS,EXTERNAL_RADIUS=2,5
PROMINENCE_ATR=.10
EQ_TOLERANCE_ATR=.10
BOS_CLOSE_ATR=.08
BOS_BODY_ATR=.20
BOS_CLOSE_LOCATION=.55
FAILURE_SWEEP_ATR=.05
FAILURE_RECLAIM_ATR=.05


def _num(v:Any):
    try:
        x=float(v); return x if x==x and abs(x)!=float("inf") else None
    except (TypeError,ValueError): return None


def _clean_bars(bars):
    out=[]; reasons=[]
    for i,b in enumerate(bars or []):
        if not isinstance(b,dict): reasons.append(f"bar_{i}_not_mapping"); continue
        o,h,l,c=[_num(b.get(k)) for k in ("open","high","low","close")]
        if any(v is None for v in (o,h,l,c)): reasons.append(f"bar_{i}_ohlc_invalid"); continue
        if h<max(o,c) or l>min(o,c) or h<l: reasons.append(f"bar_{i}_ohlc_inconsistent"); continue
        out.append({"open":o,"high":h,"low":l,"close":c})
    return out,reasons


def _tr(b,i):
    if i<=0 or i>=len(b): return 0.0
    x=b[i]; p=b[i-1]["close"]
    return max(x["high"]-x["low"],abs(x["high"]-p),abs(x["low"]-p))


def _atr(b,period=14):
    if len(b)<2:return 0.0
    return mean(_tr(b,i) for i in range(max(1,len(b)-period),len(b)))


def _atr_at(b,i,period=14):
    if i<=0:return 0.0
    return mean(_tr(b,j) for j in range(max(1,i-period+1),i+1))


def _pivot_points(b,side,radius):
    out=[]
    for i in range(radius,len(b)-radius):
        x=b[i][side]; left=[b[j][side] for j in range(i-radius,i)]; right=[b[j][side] for j in range(i+1,i+radius+1)]
        p=PROMINENCE_ATR*max(_atr_at(b,i),1e-12)
        if side=="high" and x>=max(left) and x>max(right) and min(x-max(left),x-max(right))>=p:out.append((i,x))
        if side=="low" and x<=min(left) and x<min(right) and min(min(left)-x,min(right)-x)>=p:out.append((i,x))
    return out


def _compress(points,atr,side=None,spacing=2):
    if side is None:
        v=[x[1] for x in points]; side="low" if len(v)>1 and all(v[i]<v[i-1] for i in range(1,len(v))) else "high"
    out=[]; tol=max(atr*EQ_TOLERANCE_ATR,1e-12)
    for p in points:
        if not out or p[0]-out[-1][0]>=spacing:out.append(p);continue
        old=out[-1]
        if abs(p[1]-old[1])<=tol:
            if side=="high" and p[1]>old[1]:out[-1]=p
            elif side=="low" and p[1]<old[1]:out[-1]=p
        elif side=="high" and p[1]>old[1]:out[-1]=p
        elif side=="low" and p[1]<old[1]:out[-1]=p
    return out


def _label(hp,lp,atr):
    tol=max(atr*EQ_TOLERANCE_ATR,1e-12); hs=[]; prev=None
    for i,p in hp:
        if prev is None:lab="SWING_HIGH"
        else:
            d=p-prev[1];lab="EQH" if abs(d)<=tol else ("HH" if d>0 else "LH")
        hs.append({"index":int(i),"price":round(float(p),8),"label":lab});prev=(i,p)
    ls=[];prev=None
    for i,p in lp:
        if prev is None:lab="SWING_LOW"
        else:
            d=p-prev[1];lab="EQL" if abs(d)<=tol else ("HL" if d>0 else "LL")
        ls.append({"index":int(i),"price":round(float(p),8),"label":lab});prev=(i,p)
    return hs,ls


def _latest(xs,labels):return next((x for x in reversed(xs) if x["label"] in labels),None)


def _classify(h,l):
    hh=_latest(h,{"HH","LH"});ll=_latest(l,{"HL","LL"})
    if hh and ll and hh["label"]=="HH" and ll["label"]=="HL":return UP
    if hh and ll and hh["label"]=="LH" and ll["label"]=="LL":return DOWN
    return MIXED if hh or ll else NEUTRAL


def _count_state(h,l,n=8):
    r=h[-n:]+l[-n:]; bull=sum(x["label"] in {"HH","HL"} for x in r);bear=sum(x["label"] in {"LH","LL"} for x in r)
    if not bull and not bear:return NEUTRAL
    if bull>=bear+2:return UP
    if bear>=bull+2:return DOWN
    return MIXED


def _counts(h,l,n=8):
    c={k:0 for k in ("HH","HL","LH","LL","EQH","EQL")}
    for x in h[-n:]+l[-n:]:
        if x["label"] in c:c[x["label"]]+=1
    return c


def _sequence(h,l,n=12):return sorted(h+l,key=lambda x:x["index"])[-n:]


def _protected(s,h,l):
    if s==UP:return {"protected_low":_latest(l,{"HL"}),"protected_high":_latest(h,{"HH","EQH"})}
    if s==DOWN:return {"protected_low":_latest(l,{"LL","EQL"}),"protected_high":_latest(h,{"LH","EQH"})}
    return {"protected_low":_latest(l,{"HL","LL"}),"protected_high":_latest(h,{"HH","LH"})}


def _quality(bar,level,d,atr):
    if atr<=0 or level is None:return {"confirmed":False}
    rng=max(bar["high"]-bar["low"],1e-12);body=abs(bar["close"]-bar["open"])/atr;loc=(bar["close"]-bar["low"])/rng
    dist=((bar["close"]-level) if d==UP else (level-bar["close"])) / atr
    close_ok=dist>=BOS_CLOSE_ATR;loc_ok=loc>=BOS_CLOSE_LOCATION if d==UP else loc<=1-BOS_CLOSE_LOCATION
    return {"confirmed":bool(close_ok and (body>=BOS_BODY_ATR or loc_ok)),"distance_atr":round(max(0,dist),4),"body_atr":round(body,4),"close_location":round(loc,4),"displacement_ok":body>=BOS_BODY_ATR,"close_beyond_level":close_ok}


def _event(bar,s,d,atr,event,scope="EXTERNAL",idx=0):
    q=_quality(bar,s["price"] if s else None,d,atr)
    if not q["confirmed"]:return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}
    return {"event":event,"direction":d,"confirmed":True,"scope":scope,"level":s["price"],"swing_index":s["index"],"swing_label":s["label"],"break_candle_index":idx,"break_distance_atr":q["distance_atr"],"break_body_atr":q["body_atr"],"close_location":q["close_location"],"displacement_ok":q["displacement_ok"],"close_beyond_level":q["close_beyond_level"]}


def _bos(bars,highs,lows,atr,prior_structure,scope="EXTERNAL"):
    if not bars or atr<=0:return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}
    s=_latest(highs,{"HH","LH","EQH"}) if prior_structure==DOWN else _latest(highs,{"HH","EQH"}) if prior_structure==UP else None
    if not s:return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}
    return _event(bars[-1],s,UP,atr,"CONFIRMED_CHOCH" if prior_structure==DOWN else "CONFIRMED_BOS",scope,len(bars)-1)


def _sweep_failure(bars,highs,lows,atr=None,prior_structure="UP"):
    if not bars:return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}
    if atr is None or atr<=0:atr=max(bars[-1]["high"]-bars[-1]["low"],1e-12)
    b=bars[-1];p=_protected(prior_structure,highs,lows);s=p.get("protected_high")
    if s:
        sweep=(b["high"]-s["price"])/atr;reclaim=(s["price"]-b["close"])/atr
        if sweep>=FAILURE_SWEEP_ATR and reclaim>=FAILURE_RECLAIM_ATR:return {"event":"FAILED_BREAK","direction":DOWN,"confirmed":True,"level":s["price"],"swing_index":s["index"],"swing_label":s["label"],"failure_candle_index":len(bars)-1,"scope":"EXTERNAL","sweep_distance_atr":round(sweep,4),"reclaim_distance_atr":round(reclaim,4)}
    s=p.get("protected_low")
    if s:
        sweep=(s["price"]-b["low"])/atr;reclaim=(b["close"]-s["price"])/atr
        if sweep>=FAILURE_SWEEP_ATR and reclaim>=FAILURE_RECLAIM_ATR:return {"event":"FAILED_BREAK","direction":UP,"confirmed":True,"level":s["price"],"swing_index":s["index"],"swing_label":s["label"],"failure_candle_index":len(bars)-1,"scope":"EXTERNAL","sweep_distance_atr":round(sweep,4),"reclaim_distance_atr":round(reclaim,4)}
    return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}


def _failure(bars,h,l,s,atr):return _sweep_failure(bars,h,l,atr,s)


def _choch(bars,h,l,s,atr):
    if s not in {UP,DOWN}:return {"event":"NO_CHOCH","direction":NEUTRAL,"confirmed":False}
    p=_protected(s,h,l);sw=p.get("protected_low") if s==UP else p.get("protected_high");d=DOWN if s==UP else UP
    if not sw:return {"event":"NO_CHOCH","direction":NEUTRAL,"confirmed":False}
    return _event(bars[-1],sw,d,atr,"CONFIRMED_CHOCH","EXTERNAL",len(bars)-1)


def _slope(b,n=20):
    if len(b)<5:return NEUTRAL,0.0
    c=[x["close"] for x in b[-n:]];z=(c[-1]-c[0])/(max(_atr(b),1e-12)*max(1,len(c)-1));return (UP if z>.035 else DOWN if z<-.035 else NEUTRAL),round(min(1,abs(z)*8),4)


def analyze_e3(bars):
    clean,data=_clean_bars(bars);base={"architecture":ARCHITECTURE,"reasoning_role":"MARKET_STRUCTURE_ANALYST","question":QUESTION,"decision":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"sub_engines_active":False,"sub_engines_status":"PAUSED","specialists_active":False,"specialists_status":"PAUSED","upstream_direction_used":False,"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False}
    if len(clean)<MIN_CANDLES:
        r=["E3_INSUFFICIENT_DATA",*data[:4]];return {**base,"analysis_status":"INSUFFICIENT_DATA","finding":"STRUCTURE_INSUFFICIENT_DATA","structure":"UNKNOWN","structure_state":"INSUFFICIENT_DATA","direction":NEUTRAL,"directional_bias":NEUTRAL,"structural_bias":NEUTRAL,"swing_map":{"highs":[],"lows":[]},"internal_structure":{},"external_structure":{},"BOS":"NONE","BOS_type":"NONE","structural_failure":"NONE","failure_type":"NONE","strength":0.0,"structure_strength":0.0,"confidence":0.0,"evidence":[],"observations":[],"conflicts":[],"reason_codes":r,"reasons":r,"reasoning_trace":{"closed_candles":len(clean)}}
    atr=_atr(clean)
    ih,il=_label(_compress(_pivot_points(clean,"high",INTERNAL_RADIUS),atr,"high"),_compress(_pivot_points(clean,"low",INTERNAL_RADIUS),atr,"low"),atr)
    eh,el=_label(_compress(_pivot_points(clean,"high",EXTERNAL_RADIUS),atr,"high"),_compress(_pivot_points(clean,"low",EXTERNAL_RADIUS),atr,"low"),atr)
    istate,estate=_classify(ih,il),_classify(eh,el);icount,ecount=_count_state(ih,il),_count_state(eh,el);ic,ec=_counts(ih,il),_counts(eh,el)
    bos=_bos(clean,eh,el,atr,estate);choch=_choch(clean,eh,el,estate,atr);failure=_failure(clean,eh,el,estate,atr);slope,slope_q=_slope(clean)
    conflicts=[]
    if estate in {UP,DOWN} and istate in {UP,DOWN} and estate!=istate:conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if ecount!=NEUTRAL and ecount!=estate:conflicts.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if icount!=NEUTRAL and icount!=istate:conflicts.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if estate==MIXED or istate==MIXED:conflicts.append("STRUCTURE_CONFLICT")
    if not bos.get("confirmed"):conflicts.append("NO_CONFIRMED_EXTERNAL_BOS")
    if failure.get("confirmed"):conflicts.append("FAILED_BREAK_DETECTED")
    if choch.get("confirmed"):conflicts.append("CHANGE_OF_CHARACTER_DETECTED")
    if estate in {UP,DOWN} and slope in {UP,DOWN} and slope!=estate:conflicts.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    conflicts=list(dict.fromkeys(conflicts))
    if failure.get("confirmed"):direction,state,finding=failure["direction"],"STRUCTURE_FAILURE","FAILED_BREAK"
    elif choch.get("confirmed"):direction,state=choch["direction"],"CHANGE_OF_CHARACTER";finding="BULLISH_CHOCH" if direction==UP else "BEARISH_CHOCH"
    elif bos.get("confirmed"):direction,state=bos["direction"],"BREAKOUT_CONFIRMED";finding="BULLISH_BOS" if direction==UP else "BEARISH_BOS"
    elif estate in {UP,DOWN}:direction,state=estate,"DIRECTIONAL_CONTEXT_UNCONFIRMED";finding="BULLISH_EXTERNAL_STRUCTURE" if estate==UP else "BEARISH_EXTERNAL_STRUCTURE"
    else:direction,state=NEUTRAL,"DIRECTIONAL_CONTEXT_UNCONFIRMED" if slope in {UP,DOWN} else "RANGE_OR_UNCLEAR";finding="STRUCTURE_NEUTRAL" if estate==NEUTRAL else "MIXED_STRUCTURE"
    strength=.25+(.20 if estate in {UP,DOWN} else 0)+(.20 if estate==istate and estate in {UP,DOWN} else 0)+(.10 if ecount==estate and estate in {UP,DOWN} else 0)+(.05 if icount==istate and istate in {UP,DOWN} else 0)+(.12 if bos.get("confirmed") else 0)+(.08 if choch.get("confirmed") else 0)-(.15 if failure.get("confirmed") else 0)-(.10 if estate==MIXED or istate==MIXED else 0);strength=round(max(0,min(1,strength)),4)
    observations=[f"closed_candles={len(clean)}",f"atr14={atr:.8f}",f"external_structure={estate}",f"internal_structure={istate}",f"external_count_state={ecount}",f"internal_count_state={icount}",f"external_counts={ec}",f"internal_counts={ic}",f"external_sequence={'→'.join(x['label'] for x in _sequence(eh,el))}",f"internal_sequence={'→'.join(x['label'] for x in _sequence(ih,il))}",f"slope_context={slope}",f"slope_quality={slope_q:.4f}"]
    trace={"closed_candles":len(clean),"atr14":round(atr,8),"external_state":estate,"internal_state":istate,"external_count_state":ecount,"internal_count_state":icount,"external_counts":ec,"internal_counts":ic,"slope_context":slope,"slope_quality":slope_q,"slope_is_structural_authority":False,"external_bos":bos,"external_choch":choch,"structural_failure":failure}
    evidence={"external":{"state":estate,"count_state":ecount,"counts":ec,"protected_levels":_protected(estate,eh,el)},"internal":{"state":istate,"count_state":icount,"counts":ic},"BOS":bos,"CHOCH":choch,"failure":failure}
    reasons=list(dict.fromkeys([*conflicts,"CONFIRMED_EXTERNAL_BOS" if bos.get("confirmed") else "NO_CONFIRMED_EXTERNAL_BOS","CONFIRMED_EXTERNAL_CHOCH" if choch.get("confirmed") else "NO_CONFIRMED_STRUCTURAL_REVERSAL"]))
    return {**base,"analysis_status":"COMPLETE","finding":finding,"structure":estate,"structure_state":state,"direction":direction,"directional_bias":direction,"structural_bias":estate,"external_structure":{"state":estate,"count_state":ecount,"counts":ec,"swings":{"highs":eh,"lows":el}},"internal_structure":{"state":istate,"count_state":icount,"counts":ic,"swings":{"highs":ih,"lows":il}},"swing_map":{"highs":eh,"lows":el},"BOS":bos.get("event","NO_BOS"),"BOS_type":bos.get("event","NO_BOS"),"bos":bos,"CHOCH":choch.get("event","NO_CHOCH"),"choch":choch,"structural_failure":failure.get("event","NO_FAILURE"),"failure_type":failure.get("event","NO_FAILURE"),"failure":failure,"strength":strength,"structure_strength":strength,"confidence":strength,"evidence":evidence,"observations":observations,"conflicts":conflicts,"reason_codes":reasons,"reasons":reasons,"reasoning_trace":trace}
