"""E1 Professional Market-State Brain.

E1 answers one question only: What is the market doing right now?
It uses closed-candle OHLC evidence and never makes a trade decision.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 60
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP","TREND_DOWN","RANGE","COMPRESSION","EXPANSION","TRANSITION","UNCLEAR"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> VOLATILITY -> RELATIONSHIP -> STABILITY -> STATE -> TRANSITION"
OWNERSHIP = {"owns":["data_integrity","volatility_regime","market_structure_context","directional_pressure","multi_horizon_alignment","trend_persistence","market_regime","regime_transition","state_stability","counter_evidence","market_state_invalidation"],"does_not_own":["opportunity_setup","liquidity_auction","trade_location","entry_confirmation","trade_economics","risk_management","trade_execution"]}

def _clamp(x: float) -> float: return max(0.0,min(1.0,float(x)))
def _num(x: Any):
    try: x=float(x)
    except (TypeError,ValueError): return None
    return x if isfinite(x) else None

def _ema(v:list[float],p:int)->list[float]:
    if not v:return []
    a=2/(p+1); cur=v[0]; out=[cur]
    for x in v[1:]: cur=a*x+(1-a)*cur; out.append(cur)
    return out

def _atr(b:list[dict[str,Any]],p:int)->float:
    s=b[-p:]; prev=None; tr=[]
    for x in s:
        h,l,c=x["high"],x["low"],x["close"]
        tr.append(max(h-l,abs(h-prev),abs(l-prev)) if prev is not None else h-l); prev=c
    return mean(tr) if tr else 0.0

def _slope(v:list[float],atr:float,n:int)->float:
    return 0.0 if atr<=0 or len(v)<=n else (v[-1]-v[-1-n])/atr

def _eff(v:list[float],n:int)->float:
    s=v[-n:]
    if len(s)<2:return 0.0
    path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return abs(s[-1]-s[0])/max(path,1e-12)

def _hierarchical_state(*,pressure:str,structure_direction:str,structure_quality:float,consensus:float,persistence:float,ema_relation:str,long_consensus:float,long_persistence:float,context_flip:bool,structure_break:bool,single_counter_candle:bool=False)->dict[str,Any]:
    counter=[]
    if structure_direction in {"UP","DOWN"} and pressure in {"UP","DOWN"} and structure_direction!=pressure: counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if ema_relation in {"UP","DOWN"} and pressure in {"UP","DOWN"} and ema_relation!=pressure: counter.append("EMA_CONTEXT_DISAGREES_WITH_PRESSURE")
    if single_counter_candle: counter.append("SINGLE_COUNTER_CANDLE")
    strong=consensus>=.75 and persistence>=.75 and long_consensus>=.667 and long_persistence>=.667
    confirmed_transition=bool(structure_break and strong and structure_direction in {"UP","DOWN"} and pressure in {"UP","DOWN"} and structure_direction!=pressure)
    aligned=(structure_direction in {"UP","DOWN"} and pressure==structure_direction and long_consensus>=.667 and long_persistence>=.667 and structure_quality>=.52)
    developing=(structure_direction in {"UP","DOWN"} and pressure==structure_direction and consensus>=.50 and persistence>=.50 and structure_quality>=.52)
    if confirmed_transition:
        state="TRANSITION"; direction=pressure; maturity="TRANSITION"
    elif aligned:
        state="TREND_UP" if structure_direction=="UP" else "TREND_DOWN"; direction=structure_direction; maturity="ESTABLISHED"
    elif developing:
        state="TREND_UP" if structure_direction=="UP" else "TREND_DOWN"; direction=structure_direction; maturity="DEVELOPING"
    else:
        state="UNCLEAR"; direction=pressure if pressure in {"UP","DOWN"} else structure_direction if structure_direction in {"UP","DOWN"} else "NEUTRAL"; maturity="UNRESOLVED"
    stage="CONFIRMED" if confirmed_transition else "DEVELOPING" if strong and (context_flip or structure_break) else "WATCH" if (context_flip or counter) else "ABSENT"
    if confirmed_transition: reason="persistent counter-pressure produced confirmed external structural repricing"
    elif aligned: reason="structure, pressure and long-horizon persistence agree"
    elif developing: reason="structure and pressure agree but confirmation is incomplete"
    elif structure_direction in {"UP","DOWN"} and pressure in {"UP","DOWN"} and structure_direction!=pressure: reason="counter-trend pressure is present but structural regime remains intact"
    else: reason="evidence does not establish a dominant trend regime"
    return {"state":state,"direction":direction,"maturity":maturity,"transition":confirmed_transition,"transition_stage":stage,"reason":reason,"counter_evidence":counter,"directional_state":"CONFIRMED" if maturity=="ESTABLISHED" else "DEVELOPING" if direction in {"UP","DOWN"} else "NEUTRAL"}

def _quality(bars):
    valid=[]; bad=0
    for raw in bars or []:
        if not isinstance(raw,dict): bad+=1; continue
        vals={k:_num(raw.get(k)) for k in ("open","high","low","close")}
        if any(x is None for x in vals.values()): bad+=1; continue
        o,h,l,c=vals["open"],vals["high"],vals["low"],vals["close"]
        if h<l or h<max(o,c) or l>min(o,c): bad+=1; continue
        valid.append({**raw,"open":o,"high":h,"low":l,"close":c})
    return valid,bad

def _structure(b,atr):
    hs=[];ls=[]
    for i in range(PIVOT_WING,len(b)-PIVOT_WING):
        w=b[i-PIVOT_WING:i+PIVOT_WING+1]
        if b[i]["high"]>=max(x["high"] for x in w):hs.append((i,b[i]["high"]))
        if b[i]["low"]<=min(x["low"] for x in w):ls.append((i,b[i]["low"]))
    hs,ls=hs[-8:],ls[-8:]
    hh=sum(hs[i][1]>hs[i-1][1] for i in range(1,len(hs))); lh=sum(hs[i][1]<hs[i-1][1] for i in range(1,len(hs)))
    hl=sum(ls[i][1]>ls[i-1][1] for i in range(1,len(ls))); ll=sum(ls[i][1]<ls[i-1][1] for i in range(1,len(ls)))
    bull=min(hh,hl); bear=min(lh,ll)
    if bull>=2 and bull>bear: state,quality="BULLISH",min(1,.62+.07*bull)
    elif bear>=2 and bear>bull: state,quality="BEARISH",min(1,.62+.07*bear)
    elif hh+hl>lh+ll and hh+hl>=2: state,quality="BULLISH",.52
    elif lh+ll>hh+hl and lh+ll>=2: state,quality="BEARISH",.52
    else: state,quality="MIXED",.30
    direction="UP" if state=="BULLISH" else "DOWN" if state=="BEARISH" else "NEUTRAL"
    last=b[-1]["close"]; sh=hs[-1][1] if hs else last; sl=ls[-1][1] if ls else last; buf=max(.15*atr,1e-12)
    # Structural acceptance requires two closed candles beyond a confirmed swing.
    pc=b[-2]["close"]
    accepted_up=last>sh+buf and pc>sh+buf; accepted_down=last<sl-buf and pc<sl-buf
    probe_up=last>sh+buf and pc<=sh+buf; probe_down=last<sl-buf and pc>=sl-buf
    bos="UP" if accepted_up else "DOWN" if accepted_down else "NONE"
    return {"state":state,"direction":direction,"quality":quality,"HH":hh,"HL":hl,"LH":lh,"LL":ll,"external_bos":"CONFIRMED_BOS" if bos!="NONE" else "NO_BOS","bos_direction":bos,"protected_high":sh,"protected_low":sl,"acceptance":"UP" if accepted_up else "DOWN" if accepted_down else "NONE","break_probe":"UP" if probe_up else "DOWN" if probe_down else "NONE"}

def analyze_e1(bars:list[dict[str,Any]]|None)->dict[str,Any]:
    valid,bad=_quality(bars)
    base={"question":QUESTION,"reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN"}
    if len(valid)<MIN_BARS:return {**base,"market_state":"UNCLEAR","directional_pressure":"NEUTRAL","directional_state":"UNRESOLVED","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","structure_quality":0.0,"range_state":"UNKNOWN","compression":"UNKNOWN","expansion":"UNKNOWN","transition":"UNKNOWN","transition_stage":"UNKNOWN","confidence":0.0,"evidence":[f"valid_candles={len(valid)}",f"invalid_candles={bad}"],"observations":[],"conflicts":[],"reasons":["DATA_QUALITY_INSUFFICIENT"],"analysis_status":"INCOMPLETE"}
    closes=[x["close"] for x in valid]; atr14=_atr(valid,14); atr50=_atr(valid,50)
    if atr14<=0 or atr50<=0:return {**base,"market_state":"UNCLEAR","confidence":0.0,"reasons":["ATR_INVALID"],"analysis_status":"INCOMPLETE"}
    ema20=_ema(closes,20); ema50=_ema(closes,50); ema_rel="UP" if ema20[-1]>ema50[-1] else "DOWN" if ema20[-1]<ema50[-1] else "FLAT"
    slopes=[_slope(closes,atr14,n) for n in (5,10,20,40)]; thresholds=(.15,.20,.30,.40)
    states=["UP" if s>=t else "DOWN" if s<=-t else "FLAT" for s,t in zip(slopes,thresholds)]
    up,down=states.count("UP"),states.count("DOWN"); pressure="UP" if up>down else "DOWN" if down>up else "BALANCED"; consensus=max(up,down)/4
    longs=states[1:]; long_up,long_down=longs.count("UP"),longs.count("DOWN"); long_cons=max(long_up,long_down)/3
    persistence=(sum((slopes[i]>=x for i,x in enumerate((.20,.25,.35,.45))) if pressure=="UP" else sum((slopes[i]<=x for i,x in enumerate((-.20,-.25,-.35,-.45))) if pressure=="DOWN" else 0))/4
    lpersistence=(sum((slopes[i]>=x for i,x in zip((1,2,3),(.25,.35,.45))) if pressure=="UP" else sum((slopes[i]<=x for i,x in zip((1,2,3),(-.25,-.35,-.45))) if pressure=="DOWN" else 0))/3
    prior=_atr(valid[:-14],50) if len(valid)>64 else atr50; vr=atr14/max(prior,1e-12)
    vol="EXPANDING" if vr>1.10 else "CONTRACTING" if vr<.78 else "NORMAL"
    context=_slope(closes,atr14,30); recent=_slope(closes,atr14,8); flip=abs(context)>=.45 and abs(recent)>=.65 and (context>0)!=(recent>0)
    st=_structure(valid,atr14)
    transition_break=st["external_bos"]=="CONFIRMED_BOS" and st["bos_direction"]==pressure and st["direction"]!=pressure
    single=(len(valid)>=2 and ((valid[-2]["close"]-valid[-2]["open"]) * (valid[-1]["close"]-valid[-1]["open"])<0))
    h=_hierarchical_state(pressure=pressure,structure_direction=st["direction"],structure_quality=st["quality"],consensus=consensus,persistence=persistence,ema_relation=ema_rel,long_consensus=long_cons,long_persistence=lpersistence,context_flip=flip,structure_break=transition_break,single_counter_candle=single)
    eff20=_eff(closes,20); eff40=_eff(closes,40); eff10=_eff(closes,10)
    range_score=_clamp(.35*(1 if pressure=="BALANCED" else 0)+.30*(1-_clamp((eff20+eff40)/.9))+.20*(1-_clamp(st["quality"]/.7))+.15*(1-_clamp(abs(ema20[-1]-ema50[-1])/max(atr14,1e-12)/1.2)))
    range_ok=range_score>=.62 and eff20<.40 and eff40<.45 and st["state"]=="MIXED"
    compression=vol=="CONTRACTING" and vr<.82 and max(eff20,eff40)<.55 and (pressure=="BALANCED" or consensus<.75)
    expansion=vol=="EXPANDING" and eff10>=.25 and abs(slopes[0])>=.25 and consensus>=.50
    state=h["state"]
    if state=="UNCLEAR":
        if expansion: state="EXPANSION"
        elif compression: state="COMPRESSION"
        elif range_ok: state="RANGE"
    direction=h["direction"]
    conflicts=[]
    if st["direction"] in {"UP","DOWN"} and pressure in {"UP","DOWN"} and st["direction"]!=pressure: conflicts.append("STRUCTURE_VS_PRESSURE")
    if ema_rel in {"UP","DOWN"} and pressure in {"UP","DOWN"} and ema_rel!=pressure: conflicts.append("EMA_VS_PRESSURE")
    if up and down: conflicts.append("MULTI_HORIZON_DISAGREEMENT")
    counter=h["counter_evidence"] or ["NO_MATERIAL_COUNTER_EVIDENCE"]
    agreement=.5*(1 if st["direction"]==pressure and pressure!="BALANCED" else 0)+.5*long_cons
    confidence=_clamp(.40*st["quality"]+.25*lpersistence+.20*long_cons+.15*agreement-.12*len(conflicts))
    if state=="UNCLEAR": confidence=min(confidence,.60)
    invalidation=("external bearish BOS + acceptance + persistent down pressure" if direction=="UP" else "external bullish BOS + acceptance + persistent up pressure" if direction=="DOWN" else "persistent directional pressure + structural repricing")
    supporting=[]
    if st["direction"]==direction and direction in {"UP","DOWN"}: supporting.append("STRUCTURE_ALIGNS")
    if long_cons>=.667: supporting.append("LONG_HORIZON_ALIGNMENT")
    if lpersistence>=.667: supporting.append("LONG_HORIZON_PERSISTENCE")
    trace=[f"QUESTION -> {QUESTION}",f"1A DATA_QUALITY -> valid={len(valid)} invalid={bad}",f"1B VOLATILITY -> {vol} ratio={vr:.3f}",f"1C TREND -> structure={st['state']} pressure={pressure} persistence={persistence:.3f} multi_horizon={','.join(states)}",f"1D RANGE -> {'CONFIRMED' if range_ok else 'ABSENT'} score={range_score:.3f}",f"1E COMPRESSION -> {'CONFIRMED' if compression else 'ABSENT'}",f"1F EXPANSION -> {'CONFIRMED' if expansion else 'ABSENT'}",f"1G TRANSITION -> {h['transition_stage']} confirmed={h['transition']}",f"RECONCILIATION -> state={state} direction={direction}",f"RECONCILIATION -> conflicts={conflicts} counter={counter}",f"CONFIDENCE -> {confidence:.3f} market-state confidence only",f"INVALIDATION -> {invalidation}"]
    thesis_status="CONFIRMED" if h["maturity"]=="ESTABLISHED" else "DEVELOPING" if direction in {"UP","DOWN"} else "UNRESOLVED"
    return {**base,"market_state":state,"directional_pressure":pressure,"directional_pressure_label":"BULLISH" if pressure=="UP" else "BEARISH" if pressure=="DOWN" else "NEUTRAL","directional_state":h["directional_state"],"trend_state":"UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE","volatility_state":vol,"structure_state":st["state"],"structure_quality":round(st["quality"],3),"range_state":"RANGE" if range_ok else "NOT_RANGE","compression":"CONFIRMED" if compression else "ABSENT","expansion":"CONFIRMED" if expansion else "ABSENT","transition":"PRESENT" if h["transition"] else "ABSENT","transition_stage":h["transition_stage"],"confidence":round(confidence,3),"evidence":[f"valid_candles={len(valid)}",f"invalid_candles={bad}",f"ema20_vs_ema50={ema_rel}",f"multi_horizon={','.join(states)}",f"directional_consensus={consensus:.3f}",f"long_horizon_consensus={long_cons:.3f}",f"persistence={persistence:.3f}",f"long_horizon_persistence={lpersistence:.3f}",f"external_bos={st['external_bos']}",f"volatility_ratio={vr:.3f}"],"observations":[],"conflicts":conflicts,"reasons":(["REGIME_TRANSITION_CONFIRMED"] if h["transition"] else ["TRANSITION_WATCH_ONLY"] if h["transition_stage"] in {"WATCH","DEVELOPING"} else ["MARKET_STATE_CLASSIFIED"]),"reasoning_trace":trace,"professional_reasoning":{"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":state,"market_state":state,"direction":direction,"directional_pressure":pressure,"directional_state":h["directional_state"],"trend_maturity":h["maturity"],"trend_confirmed":state in {"TREND_UP","TREND_DOWN"} and h["maturity"]=="ESTABLISHED","transition_confirmed":h["transition"],"transition_stage":h["transition_stage"],"transition_direction":pressure,"transition_evidence":["EXTERNAL_STRUCTURAL_REPRICING"] if h["transition"] else [],"conflict_detected":bool(conflicts),"conflict_count":len(conflicts),"classification_reason":h["reason"],"single_counter_candle":single,"primary_thesis":{"direction":direction,"status":thesis_status,"supporting_evidence":supporting,"counter_evidence":counter,"relationship":"WITH_TREND" if st["direction"]==pressure and pressure in {"UP","DOWN"} else "COUNTER_TREND_PRESSURE" if st["direction"] in {"UP","DOWN"} and pressure in {"UP","DOWN"} else "MIXED_OR_NEUTRAL"},"counter_evidence":counter,"dominant_evidence":supporting or [f"STATE={state}"],"invalidation":{"primary":invalidation},"confidence_model":{"evidence_strength":round(st["quality"],3),"evidence_agreement":round(agreement,3),"counter_evidence":round(_clamp(len(counter)/5),3),"stability":round(_clamp(.6*long_cons+.4*(1-len(conflicts)/5)),3)},"evidence_hierarchy":EVIDENCE_HIERARCHY,"ownership_boundaries":OWNERSHIP},"analysis_status":"COMPLETE"}
