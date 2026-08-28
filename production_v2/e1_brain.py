"""E1 Professional Market-State Brain. Closed candles only; no trade decisions."""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

QUESTION="What is the market doing right now?"
MIN_BARS=60
PIVOT_WING=2
MARKET_STATES={"TREND_UP","TREND_DOWN","RANGE","COMPRESSION","EXPANSION","TRANSITION","UNCLEAR"}
EVIDENCE_HIERARCHY="DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> VOLATILITY -> STABILITY -> COUNTER_EVIDENCE -> STATE -> TRANSITION"
OWNERSHIP={"owns":["data_integrity","volatility_regime","market_structure_context","directional_pressure","multi_horizon_alignment","trend_persistence","market_regime","regime_transition","state_stability","counter_evidence","market_state_thesis","market_state_invalidation"],"does_not_own":["opportunity_setup","liquidity_auction","trade_location","entry_confirmation","trade_economics","risk_management","trade_execution"]}

def _num(x:Any)->float|None:
    try:x=float(x)
    except(TypeError,ValueError):return None
    return x if isfinite(x) else None

def _clamp(x:float)->float:return max(0.0,min(1.0,float(x)))

def _ema(v:list[float],p:int)->list[float]:
    if not v:return []
    a=2/(p+1);cur=v[0];out=[cur]
    for x in v[1:]:cur=a*x+(1-a)*cur;out.append(cur)
    return out

def _atr(b:list[dict[str,Any]],p:int,start:int|None=None,end:int|None=None)->float:
    s=b[start:end] if start is not None or end is not None else b;s=s[-p:];trs=[];pc=None
    for x in s:
        h,l,c=x["high"],x["low"],x["close"];trs.append(h-l if pc is None else max(h-l,abs(h-pc),abs(l-pc)));pc=c
    return mean(trs) if trs else 0.0

def _slope(v:list[float],atr:float,n:int)->float:return 0.0 if atr<=0 or len(v)<=n else (v[-1]-v[-1-n])/atr

def _eff(v:list[float],n:int)->float:
    s=v[-n:]
    if len(s)<2:return 0.0
    path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return abs(s[-1]-s[0])/max(path,1e-12)

# 1A Data Quality
def _1a(bars):
    valid=[];bad=0
    for r in bars or []:
        if not isinstance(r,dict):bad+=1;continue
        v={k:_num(r.get(k)) for k in ("open","high","low","close")}
        if any(x is None for x in v.values()):bad+=1;continue
        o,h,l,c=v["open"],v["high"],v["low"],v["close"]
        if h<l or h<max(o,c) or l>min(o,c):bad+=1;continue
        valid.append({**r,**v})
    return {"valid":valid,"valid_candles":len(valid),"invalid_candles":bad,"sufficient":len(valid)>=MIN_BARS,"quality":_clamp(len(valid)/max(len(valid)+bad,1))}

# Shared measurements: no classification authority here.
def _measure(b):
    c=[x["close"] for x in b];a14=_atr(b,14);a50=_atr(b,50);e20=_ema(c,20);e50=_ema(c,50)
    er="UP" if e20[-1]>e50[-1] else "DOWN" if e20[-1]<e50[-1] else "FLAT"
    gap=(e20[-1]-e50[-1])/max(a14,1e-12);hs=(5,10,20,40);th=(.15,.20,.30,.40);sl=[_slope(c,a14,n) for n in hs]
    st=["UP" if x>=t else "DOWN" if x<=-t else "FLAT" for x,t in zip(sl,th)];up=st.count("UP");dn=st.count("DOWN");lu=st[1:].count("UP");ld=st[1:].count("DOWN")
    pressure="UP" if up==4 or lu>ld else "DOWN" if dn==4 or ld>lu else "BALANCED"
    con=max(up,dn)/4;lc=max(lu,ld)/3
    if pressure=="UP":pers=sum((sl[0]>=.20,sl[1]>=.25,sl[2]>=.35,sl[3]>=.45))/4;lp=sum((sl[1]>=.25,sl[2]>=.35,sl[3]>=.45))/3
    elif pressure=="DOWN":pers=sum((sl[0]<=-.20,sl[1]<=-.25,sl[2]<=-.35,sl[3]<=-.45))/4;lp=sum((sl[1]<=-.25,sl[2]<=-.35,sl[3]<=-.45))/3
    else:pers=lp=0.0
    prior=_atr(b,50,-64,-14) if len(b)>=64 else a50;vr=a14/max(prior,1e-12)
    ctx=_slope(c,a14,30);recent=_slope(c,a14,8);flip=abs(ctx)>=.45 and abs(recent)>=.65 and (ctx>0)!=(recent>0)
    prev=_slope(c[:-1],a14,5);pp="UP" if prev>.20 else "DOWN" if prev<-.20 else "NEUTRAL";last="UP" if b[-1]["close"]>b[-1]["open"] else "DOWN" if b[-1]["close"]<b[-1]["open"] else "FLAT"
    return dict(closes=c,atr14=a14,atr50=a50,ema20=e20,ema50=e50,ema_relation=er,ema_gap=gap,ema20_slope=_slope(e20,a14,5),ema50_slope=_slope(e50,a14,5),horizons=hs,slopes=sl,horizon_states=st,up=up,down=dn,long_up=lu,long_down=ld,pressure=pressure,consensus=con,long_consensus=lc,persistence=pers,long_persistence=lp,eff10=_eff(c,10),eff20=_eff(c,20),eff40=_eff(c,40),prior_atr=prior,volatility_ratio=vr,context_slope=ctx,recent_slope=recent,context_flip=flip,prior_pressure=pp,single_counter_candle=pp in {"UP","DOWN"} and last in {"UP","DOWN"} and pp!=last)

# 1C Trend / Structure
def _1c(b,m):
    hi=[];lo=[]
    for i in range(PIVOT_WING,len(b)-PIVOT_WING):
        w=b[i-PIVOT_WING:i+PIVOT_WING+1]
        if b[i]["high"]>=max(x["high"] for x in w):hi.append((i,b[i]["high"]))
        if b[i]["low"]<=min(x["low"] for x in w):lo.append((i,b[i]["low"]))
    hi,lo=hi[-8:],lo[-8:];hh=sum(hi[i][1]>hi[i-1][1] for i in range(1,len(hi)));lh=sum(hi[i][1]<hi[i-1][1] for i in range(1,len(hi)));hl=sum(lo[i][1]>lo[i-1][1] for i in range(1,len(lo)));ll=sum(lo[i][1]<lo[i-1][1] for i in range(1,len(lo)))
    bs,ds=min(hh,hl),min(lh,ll)
    if bs>=2 and bs>ds:state,q="BULLISH",min(1,.62+.07*bs)
    elif ds>=2 and ds>bs:state,q="BEARISH",min(1,.62+.07*ds)
    elif hh+hl>=2 and hh+hl>lh+ll:state,q="BULLISH",.52
    elif lh+ll>=2 and lh+ll>hh+hl:state,q="BEARISH",.52
    else:state,q="MIXED",.30
    last=b[-1]["close"];rh=max((x[1] for x in hi),default=last);rl=min((x[1] for x in lo),default=last);buf=max(.1*m["atr14"],1e-12);bu=last>rh+buf;bd=last<rl-buf
    return {"state":state,"direction":"UP" if state=="BULLISH" else "DOWN" if state=="BEARISH" else "NEUTRAL","quality":q,"counts":{"HH":hh,"HL":hl,"LH":lh,"LL":ll},"external_bos":"CONFIRMED_BOS" if bu or bd else "NO_BOS","bos_direction":"UP" if bu else "DOWN" if bd else "NONE","recent_swing_high":rh,"recent_swing_low":rl}

# 1B Volatility
def _1b(m):
    r=m["volatility_ratio"];s="EXPANDING" if r>1.10 else "CONTRACTING" if r<.78 else "NORMAL"
    return {"state":s,"ratio":r,"atr14":m["atr14"],"prior_atr":m["prior_atr"]}

# 1D Range
def _1d(m,t):
    score=.35*(m["pressure"]=="BALANCED")+.30*(1-_clamp(((m["eff20"]+m["eff40"])/2)/.45))+.20*(1-_clamp(t["quality"]/.70))+.15*(1-_clamp(abs(m["ema_gap"])/1.20))
    ok=score>=.62 and m["eff20"]<.40 and m["eff40"]<.45 and abs(m["ema_gap"])<1
    return {"state":"RANGE" if ok else "NOT_RANGE","score":_clamp(score)}

# 1E Compression
def _1e(m,v):
    rs=_clamp((.90-m["volatility_ratio"])/.20);ef=_clamp((.55-max(m["eff20"],m["eff40"]))/.55);ok=v["state"]=="CONTRACTING" and m["volatility_ratio"]<.82
    return {"state":"CONFIRMED" if ok else "ABSENT","score":_clamp(.70*rs+.30*ef)}

# 1F Expansion
def _1f(m,v):
    imp=_clamp(abs(m["slopes"][0])/.80);ef=_clamp(m["eff10"]/.45);ok=v["state"]=="EXPANDING" and m["eff10"]>=.25 and abs(m["slopes"][0])>=.25
    return {"state":"CONFIRMED" if ok else "ABSENT","score":_clamp(.55*_clamp((m["volatility_ratio"]-1.05)/.35)+.25*imp+.20*ef)}

# 1G Transition: deliberately stricter than trend classification.
def _1g(m,t):
    p=m["pressure"];sd=t["direction"];br=t["external_bos"]=="CONFIRMED_BOS";against=br and p in {"UP","DOWN"} and t["bos_direction"]!=p
    repricing=p in {"UP","DOWN"} and sd in {"UP","DOWN"} and sd!=p and t["quality"]>=.62 and br and t["bos_direction"]==p and m["persistence"]>=.75 and m["long_persistence"]>=.667
    ok=repricing and m["context_flip"]
    ev=[]
    if m["context_flip"]:ev.append("CONTEXT_FLIP")
    if br:ev.append("STRUCTURE_BREAK")
    if against:ev.append("STRUCTURE_BREAK_AGAINST_PRESSURE")
    if ok:ev.append("STRUCTURAL_REPRICING_CONFIRMED")
    return {"state":"CONFIRMED" if ok else "ABSENT","confirmed":ok,"structural_repricing":repricing,"context_flip":m["context_flip"],"bos_against_pressure":against,"evidence":ev}

# Evidence Reconciliation: the only state authority.
def _reconcile(m,t,v,r,c,e,tr):
    p=m["pressure"];sd=t["direction"];struct=sd in {"UP","DOWN"} and t["quality"]>=.52;counter=[]
    if p in {"UP","DOWN"} and struct and sd!=p:counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if p in {"UP","DOWN"} and m["ema_relation"] in {"UP","DOWN"} and m["ema_relation"]!=p:counter.append("EMA_DISAGREES_WITH_PRESSURE")
    if m["consensus"]<.75 or m["long_consensus"]<.667:counter.append("MULTI_HORIZON_NOT_FULLY_CONFIRMED")
    if m["context_flip"]:counter.append("RECENT_CONTEXT_FLIP")
    if m["single_counter_candle"]:counter.append("SINGLE_COUNTER_CANDLE")
    if not counter:counter=["NO_MATERIAL_COUNTER_EVIDENCE"]
    ad=sd if struct and (m["long_persistence"]>=.667 or m["long_consensus"]>=.667) else p if p in {"UP","DOWN"} else "NEUTRAL"
    aligned=ad in {"UP","DOWN"} and struct and ad==sd and m["long_consensus"]>=.667 and m["long_persistence"]>=.667
    developing=ad in {"UP","DOWN"} and struct and ad==sd
    if tr["confirmed"]:state,mat,why="TRANSITION","TRANSITION","confirmed structural repricing against prior context"
    elif c["state"]=="CONFIRMED" and not aligned and not e["state"]=="CONFIRMED":state,mat,why="COMPRESSION","CONTRACTING","volatility contraction is dominant evidence"
    elif e["state"]=="CONFIRMED":state,mat,why="EXPANSION","EXPANDING","volatility expansion with displacement is dominant"
    elif r["state"]=="RANGE" and not aligned:state,mat,why="RANGE","RANGE","balanced pressure, weak efficiency and weak structural dominance"
    elif aligned:state,mat,why=("TREND_UP" if ad=="UP" else "TREND_DOWN"),"ESTABLISHED","structure is authoritative and persistence confirms it"
    elif developing:state,mat,why=("TREND_UP" if ad=="UP" else "TREND_DOWN"),"DEVELOPING","structure establishes context while pressure develops"
    else:state,mat,why="UNCLEAR","UNRESOLVED","evidence does not establish a dominant regime"
    ds="CONFLICTED" if tr["confirmed"] else "CONFIRMED" if mat=="ESTABLISHED" else "DEVELOPING" if ad in {"UP","DOWN"} else "NEUTRAL"
    support=_clamp((m["consensus"]+m["persistence"]+(1 if ad==sd and ad!="NEUTRAL" else 0)+m["long_consensus"]+m["long_persistence"])/5);cs=_clamp(len([x for x in counter if x!="NO_MATERIAL_COUNTER_EVIDENCE"])/5);st=_clamp((m["long_consensus"]+m["long_persistence"]+(1 if struct else 0))/3-.15*cs);ss="STABLE" if st>=.70 and not tr["confirmed"] else "UNSTABLE" if st<.45 or tr["confirmed"] else "WATCH"
    fit={"TREND_UP":1 if ad=="UP" else 0,"TREND_DOWN":1 if ad=="DOWN" else 0,"RANGE":r["score"],"COMPRESSION":c["score"],"EXPANSION":e["score"],"TRANSITION":.85 if tr["confirmed"] else 0,"UNCLEAR":.40}[state]
    conf=_clamp(.25*support+.20*(t["quality"] if state in {"TREND_UP","TREND_DOWN","TRANSITION"} else .5*t["quality"])+.15*st+.15*fit+.10*m["long_persistence"]+.10*max(m["eff20"],m["eff40"])+.05*(1-cs)-.15*cs)
    if state=="UNCLEAR":conf=min(conf,.65)
    if tr["confirmed"]:conf=min(conf,.80)
    conflicts=[]
    if m["ema_relation"] in {"UP","DOWN"} and p in {"UP","DOWN"} and m["ema_relation"]!=p:conflicts.append("EMA_VS_PRICE_PRESSURE")
    if sd in {"UP","DOWN"} and p in {"UP","DOWN"} and sd!=p:conflicts.append("STRUCTURE_VS_PRICE_PRESSURE")
    if m["up"] and m["down"]:conflicts.append("SHORT_VS_LONG_HORIZON")
    if m["context_flip"]:conflicts.append("RECENT_IMPULSE_VS_PRIOR_CONTEXT")
    if tr["bos_against_pressure"]:conflicts.append("STRUCTURE_BREAK_VS_PRESSURE")
    for x in counter:
        if x!="NO_MATERIAL_COUNTER_EVIDENCE" and x not in conflicts:conflicts.append(x)
    return {"state":state,"direction":ad,"maturity":mat,"directional_state":ds,"reason":why,"counter":counter,"conflicts":conflicts,"support":round(support,3),"counter_score":round(cs,3),"stability":round(st,3),"stability_status":ss,"confidence":round(conf,3)}

def _incomplete(reason,evidence,conflicts):
    return {"question":QUESTION,"reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN","market_state":"UNCLEAR","directional_pressure":"NEUTRAL","directional_pressure_label":"NEUTRAL","directional_state":"UNRESOLVED","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","structure_quality":0.0,"range_state":"UNKNOWN","compression":"UNKNOWN","expansion":"UNKNOWN","transition":"UNKNOWN","regime_stress":"UNKNOWN","confidence":0.0,"evidence":evidence,"observations":evidence,"conflicts":conflicts,"reasons":[reason],"reasoning_trace":[f"QUESTION -> {QUESTION}","1A DATA_QUALITY -> insufficient","STATE -> UNCLEAR"],"professional_reasoning":{"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":"UNCLEAR","direction":"NEUTRAL","directional_pressure":"NEUTRAL","transition_confirmed":False,"conflict_detected":bool(conflicts),"counter_evidence":[reason],"confidence_model":{"support":0,"counter_evidence":1,"structure":0,"persistence":0,"stability":0}},"analysis_status":"INCOMPLETE"}

def analyze_e1(bars:list[dict[str,Any]]|None)->dict[str,Any]:
    """1A -> 1B/1C/1D/1E/1F/1G -> Evidence Reconciliation."""
    d=_1a(bars)
    if not d["sufficient"]:return _incomplete("insufficient reliable closed candles; classification withheld",[f"valid_candles={d['valid_candles']}",f"invalid_candles={d['invalid_candles']}",f"minimum_required={MIN_BARS}"],["DATA_QUALITY_ANOMALIES"] if d["invalid_candles"] else [])
    b=d["valid"];m=_measure(b)
    if m["atr14"]<=0 or m["atr50"]<=0:return _incomplete("ATR invalid; classification withheld",["ATR_INVALID"],["ATR_INVALID"])
    v=_1b(m);t=_1c(b,m);r=_1d(m,t);c=_1e(m,v);e=_1f(m,v);tr=_1g(m,t);q=_reconcile(m,t,v,r,c,e,tr)
    state,dr,mat=q["state"],q["direction"],q["maturity"];label="BULLISH" if dr=="UP" else "BEARISH" if dr=="DOWN" else "NEUTRAL";sa=1 if t["direction"]==dr and dr!="NEUTRAL" else .5 if t["state"]=="MIXED" else 0;ea=1 if dr in {"UP","DOWN"} and m["ema_relation"]==dr else 0;ps=m["consensus"]*(.65+.35*m["persistence"]);ts=.30*m["consensus"]+.25*m["persistence"]+.25*sa+.10*ea+.10*m["long_consensus"]
    inv=("PRICE_ACCEPTS_BELOW_THE_PROTECTED_BULLISH_STRUCTURE_OR_PRESSURE_REMAINS_PERSISTENTLY_DOWN" if dr=="UP" else "PRICE_ACCEPTS_ABOVE_THE_PROTECTED_BEARISH_STRUCTURE_OR_PRESSURE_REMAINS_PERSISTENTLY_UP" if dr=="DOWN" else "A_DOMINANT_REGIME_IS_ESTABLISHED_BY_INDEPENDENT_EVIDENCE")
    ic=( ["STRUCTURE_TURNS_BEARISH","MULTI_HORIZON_PRESSURE_TURNS_DOWN_AND_PERSISTS","EMA_CONTEXT_FLIPS_DOWN_WITH_CONFIRMING_STRUCTURE"] if dr=="UP" else ["STRUCTURE_TURNS_BULLISH","MULTI_HORIZON_PRESSURE_TURNS_UP_AND_PERSISTS","EMA_CONTEXT_FLIPS_UP_WITH_CONFIRMING_STRUCTURE"] if dr=="DOWN" else ["PERSISTENT_MULTI_HORIZON_DIRECTIONAL_PRESSURE","CONFIRMED_STRUCTURE_BREAK_WITH_ACCEPTANCE"] )
    thesis={"direction":dr,"label":label,"status":"CONFIRMED" if state in {"TREND_UP","TREND_DOWN"} and mat=="ESTABLISHED" else "DEVELOPING" if dr!="NEUTRAL" else "UNRESOLVED","supporting_evidence":["STRUCTURE_ALIGNS"] if sa==1 else [],"counter_evidence":q["counter"],"support_score":q["support"],"counter_score":q["counter_score"]}
    evidence=[f"valid_candles={d['valid_candles']}",f"invalid_candles={d['invalid_candles']}",f"ema20_vs_ema50={m['ema_relation']}",f"ema_gap_atr={m['ema_gap']:.3f}",*(f"price_slope_{n}_atr={s:.3f}" for n,s in zip(m['horizons'],m['slopes'])),f"multi_horizon={','.join(m['horizon_states'])}",f"directional_consensus={m['consensus']:.3f}",f"long_horizon_consensus={m['long_consensus']:.3f}",f"persistence={m['persistence']:.3f}",f"long_horizon_persistence={m['long_persistence']:.3f}",f"structure_state={t['state']}",f"structure_quality={t['quality']:.3f}",f"external_bos={t['external_bos']}",f"volatility_ratio={m['volatility_ratio']:.3f}",f"stability={q['stability_status']}:{q['stability']:.3f}",f"counter_evidence={q['counter']}",f"transition_evidence={tr['evidence']}"]
    ind={"1A_data_quality":{"valid_candles":d["valid_candles"],"invalid_candles":d["invalid_candles"],"quality":round(d["quality"],3)},"1B_volatility":v,"1C_trend":t,"1D_range":r,"1E_compression":c,"1F_expansion":e,"1G_transition":tr,"data_quality":{"valid_candles":d["valid_candles"],"invalid_candles":d["invalid_candles"]},"structure":{**t,"alignment":sa},"pressure":{"direction":dr,"score":round(ps,3),"state":q["directional_state"]},"persistence":{"score":round(m["persistence"],3),"long_horizon_score":round(m["long_persistence"],3),"efficiency20":round(m["eff20"],3),"efficiency40":round(m["eff40"],3)},"ema_context":{"relation":m["ema_relation"],"gap_atr":round(m["ema_gap"],3),"ema20_slope_atr":round(m["ema20_slope"],3),"ema50_slope_atr":round(m["ema50_slope"],3),"alignment":ea},"volatility":{"atr14":round(m["atr14"],6),"prior_atr":round(m["prior_atr"],6),"ratio":round(m["volatility_ratio"],3)},"stability":{"score":q["stability"],"status":q["stability_status"]},"counter_evidence":q["counter"],"invalidation":{"primary":inv,"conditions":ic}}
    trace=[f"QUESTION -> {QUESTION}",f"1A DATA_QUALITY -> VALID {d['valid_candles']}/{d['valid_candles']+d['invalid_candles']}",f"1B VOLATILITY -> {v['state']} ratio={m['volatility_ratio']:.2f}",f"1C TREND -> structure={t['state']} quality={t['quality']:.2f} pressure={m['pressure']} persistence={m['persistence']:.2f}",f"1D RANGE -> {r['state']} score={r['score']:.2f}",f"1E COMPRESSION -> {c['state']} score={c['score']:.2f}",f"1F EXPANSION -> {e['state']} score={e['score']:.2f}",f"1G TRANSITION -> {'PRESENT' if tr['confirmed'] else 'ABSENT'} evidence={tr['evidence']}",f"RECONCILIATION -> dominant={state} direction={dr} support={q['support']:.2f} counter={q['counter_score']:.2f}",f"CONFLICTS -> {q['conflicts']}",f"STABILITY -> {q['stability_status']} score={q['stability']:.2f}",f"CONFIDENCE -> {q['confidence']:.3f} (market-state confidence, not trade probability)",f"STATE -> {state} because={q['reason']}",f"INVALIDATION -> {inv}"]
    return {"question":QUESTION,"reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN","market_state":state,"directional_pressure":dr if dr!="NEUTRAL" else label,"directional_pressure_label":label,"directional_state":q["directional_state"],"trend_state":"UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE","volatility_state":v["state"],"structure_state":t["state"],"structure_quality":round(t["quality"],3),"range_state":r["state"],"compression":c["state"],"expansion":e["state"],"transition":"PRESENT" if tr["confirmed"] else "ABSENT","regime_stress":"PRESENT" if state=="UNCLEAR" and dr!="NEUTRAL" else "ABSENT","confidence":q["confidence"],"evidence":evidence,"observations":evidence,"conflicts":q["conflicts"],"reasons":q["conflicts"]+["REGIME_TRANSITION_CONFIRMED" if tr["confirmed"] else "REGIME_CONFIRMATION_INSUFFICIENT" if state=="UNCLEAR" else "DIRECTIONAL_STATE_DEVELOPING" if q["directional_state"]=="DEVELOPING" else "MARKET_STATE_CLASSIFIED"],"reasoning_trace":trace,"professional_reasoning":{"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":state,"market_state":state,"direction":dr,"directional_pressure":label,"directional_state":q["directional_state"],"trend_maturity":mat,"trend_confirmed":state in {"TREND_UP","TREND_DOWN"},"regime_stress":state=="UNCLEAR" and dr!="NEUTRAL","transition_confirmed":tr["confirmed"],"conflict_detected":bool(q["conflicts"]),"conflict_count":len(q["conflicts"]),"classification_reason":q["reason"],"single_counter_candle":m["single_counter_candle"],"pressure_score":round(ps,3),"structure_alignment":round(sa,3),"trend_score":round(ts,3),"primary_thesis":thesis,"counter_evidence":q["counter"],"invalidation":{"primary":inv,"conditions":ic},"confidence_model":{"support":q["support"],"counter_evidence":q["counter_score"],"structure":round(sa,3),"persistence":round(m["persistence"],3),"stability":q["stability"]},"state_stability":{"status":q["stability_status"],"score":q["stability"]},"independent_evidence":ind,"evidence_hierarchy":EVIDENCE_HIERARCHY,"ownership_boundaries":OWNERSHIP},"analysis_status":"COMPLETE"}
