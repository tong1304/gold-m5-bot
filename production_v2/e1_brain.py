"""E1 Professional Market-State Brain.

E1 answers only: what is the market doing right now?
It never creates a setup, entry, risk plan, or BUY/SELL decision.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 80
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> MULTI_HORIZON -> VOLATILITY -> TRANSITION -> STABILITY -> MARKET_STATE"
OWNERSHIP = {"owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "range_regime", "compression_regime", "expansion_regime", "regime_transition", "state_stability", "counter_evidence", "market_state_invalidation"], "does_not_own": ["opportunity_setup", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution", "BUY", "SELL"]}

def _clamp(x: float) -> float: return max(0.0, min(1.0, float(x)))
def _num(x: Any):
    try: v = float(x)
    except (TypeError, ValueError): return None
    return v if isfinite(v) else None

def _quality(bars):
    valid=[]; invalid=0
    for raw in bars or []:
        if not isinstance(raw, dict): invalid += 1; continue
        v={k:_num(raw.get(k)) for k in ("open","high","low","close")}
        if any(x is None for x in v.values()): invalid += 1; continue
        o,h,l,c=v.values()
        if h<l or h<max(o,c) or l>min(o,c): invalid += 1; continue
        valid.append({**raw, **v})
    return valid,invalid

def _atr(bars, n):
    if len(bars)<n: return 0.0
    out=[]; prev=None
    for b in bars[-n:]:
        h,l,c=b["high"],b["low"],b["close"]
        out.append(max(h-l,abs(h-prev),abs(l-prev)) if prev is not None else h-l); prev=c
    return mean(out) if out else 0.0

def _slope(values, atr, n):
    return (values[-1]-values[-1-n])/atr if atr>0 and len(values)>n else 0.0

def _eff(values,n):
    if len(values)<n: return 0.0
    s=values[-n:]; path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return _clamp(abs(s[-1]-s[0])/max(path,1e-12))

def _ema(values,n):
    if not values: return 0.0
    a=2/(n+1); x=values[0]
    for v in values[1:]: x=a*v+(1-a)*x
    return x

def _structure(bars,atr):
    highs=[]; lows=[]; w=PIVOT_WING
    for i in range(w,len(bars)-w):
        window=bars[i-w:i+w+1]; h=bars[i]["high"]; l=bars[i]["low"]
        if h>=max(x["high"] for x in window): highs.append((i,h))
        if l<=min(x["low"] for x in window): lows.append((i,l))
    highs,lows=highs[-12:],lows[-12:]
    hh=sum(highs[i][1]>highs[i-1][1] for i in range(1,len(highs))); lh=sum(highs[i][1]<highs[i-1][1] for i in range(1,len(highs)))
    hl=sum(lows[i][1]>lows[i-1][1] for i in range(1,len(lows))); ll=sum(lows[i][1]<lows[i-1][1] for i in range(1,len(lows)))
    bull=min(hh,hl); bear=min(lh,ll)
    if bull>=2 and bull>bear: state,direction,quality="BULLISH","UP",_clamp(.58+.07*bull+.02*max(0,hh+hl-lh-ll))
    elif bear>=2 and bear>bull: state,direction,quality="BEARISH","DOWN",_clamp(.58+.07*bear+.02*max(0,lh+ll-hh-hl))
    elif hh+hl>=3 and hh+hl>=lh+ll+1: state,direction,quality="BULLISH","UP",.52
    elif lh+ll>=3 and lh+ll>=hh+hl+1: state,direction,quality="BEARISH","DOWN",.52
    else: state,direction,quality="MIXED","NEUTRAL",.30
    last,prev=bars[-1]["close"],bars[-2]["close"]; ph=highs[-1][1] if highs else last; pl=lows[-1][1] if lows else last; buf=max(.15*atr,1e-12)
    up=last>ph+buf and prev>ph+buf; down=last<pl-buf and prev<pl-buf
    return {"state":state,"direction":direction,"quality":quality,"HH":hh,"HL":hl,"LH":lh,"LL":ll,"external_bos":"CONFIRMED_BOS" if up or down else "NO_BOS","bos_direction":"UP" if up else "DOWN" if down else "NONE","repricing_strength":1.0 if up or down else 0.0,"protected_high":ph,"protected_low":pl,"acceptance":"UP" if up else "DOWN" if down else "NONE","break_probe":"UP" if last>ph+buf and prev<=ph+buf else "DOWN" if last<pl-buf and prev>=pl-buf else "NONE","swing_count_highs":len(highs),"swing_count_lows":len(lows)}

def _pressure(closes,atr):
    vals=[_slope(closes,atr,n) for n in (5,10,20,40)]; ts=(.15,.20,.30,.40)
    states=["UP" if v>=t else "DOWN" if v<=-t else "FLAT" for v,t in zip(vals,ts)]; up,down=states.count("UP"),states.count("DOWN"); ls=states[1:]; lu,ld=ls.count("UP"),ls.count("DOWN")
    return {"states":states,"pressure":"UP" if up>down else "DOWN" if down>up else "BALANCED","consensus":max(up,down)/4,"long_direction":"UP" if lu>ld else "DOWN" if ld>lu else "NEUTRAL","long_consensus":max(lu,ld)/3,"values":vals}

def _persistence(closes,atr,p):
    vals=[_slope(closes,atr,n) for n in (5,10,20,40)]; ts=(.15,.20,.30,.40)
    hits=sum(v>=t if p=="UP" else v<=-t for v,t in zip(vals,ts)) if p in {"UP","DOWN"} else 0
    blocks=[]
    for i in range(0,18,6):
        d=closes[-24+i+5]-closes[-24+i]; blocks.append("UP" if d>0 else "DOWN" if d<0 else "FLAT")
    consistency=sum(x==p for x in blocks)/3 if p in {"UP","DOWN"} else 0.0
    score=hits/4
    return {"score":score,"consistency":consistency,"persistent":score>=.75 and consistency>=.667,"values":vals,"block_directions":blocks}

def _volatility(bars,closes,a14,a50):
    ratio=a14/max(a50,1e-12); short=mean([b["high"]-b["low"] for b in bars[-5:]])/max(mean([b["high"]-b["low"] for b in bars[-20:]]),1e-12); eff=_eff(closes,10)
    hist=[]
    for end in range(max(50,len(bars)-5),len(bars)+1): hist.append(_atr(bars[:end],14)/max(_atr(bars[:end],50),1e-12))
    state="EXPANDING" if ratio>=1.12 else "CONTRACTING" if ratio<=.82 else "NORMAL"
    exp_persist=sum(x>=1.08 for x in hist[-3:])>=2; comp_persist=sum(x<=.92 for x in hist[-3:])>=2
    directional=state=="EXPANDING" and exp_persist and eff>=.30 and abs(_slope(closes,a14,5))>=.25
    compression=state=="CONTRACTING" and comp_persist and short<=.90 and eff<=.55
    return {"state":state,"ratio":ratio,"short_range_ratio":short,"volatility_expansion":state=="EXPANDING","directional_expansion":directional,"compression":compression,"efficiency10":eff,"expansion_persistence":exp_persist}

def _range(bars,closes,atr,structure):
    x=bars[-21:-1]; y=bars[-41:-1]; hi,lo=max(b["high"] for b in x),min(b["low"] for b in x); hi40,lo40=max(b["high"] for b in y),min(b["low"] for b in y)
    e20,e40=_eff(closes,20),_eff(closes,40); contained=sum(lo40<=b["close"]<=hi40 for b in bars[-20:])/20; pos=_clamp((closes[-1]-lo)/(hi-lo if hi>lo else 1e-12)); score=_clamp(.20*(1-abs(pos-.5)*2)+.25*(1-e20)+.15*(1-e40)+.25*contained+.15*(structure["state"]=="MIXED"))
    return {"range_score":score,"range_confirmed":score>=.62 and e20<.45 and e40<.55 and contained>=.80,"position_20":pos,"range_high_20":hi,"range_low_20":lo,"range_high_40":hi40,"range_low_40":lo40,"efficiency_20":e20,"efficiency_40":e40,"contained40":contained}

def _transition(closes,atr,structure,pressure,persistence,volatility):
    s8=_slope(closes,atr,8); s30=_slope(closes,atr,30); sd="UP" if s8>.20 else "DOWN" if s8<-.20 else "FLAT"; cd="UP" if s30>.35 else "DOWN" if s30<-.35 else "FLAT"
    disagreement=structure["direction"] in {"UP","DOWN"} and pressure["pressure"] in {"UP","DOWN"} and structure["direction"]!=pressure["pressure"]; inflection=sd in {"UP","DOWN"} and cd in {"UP","DOWN"} and sd!=cd; repricing=structure["external_bos"]=="CONFIRMED_BOS"; persistent_counter=disagreement and (persistence["score"]>=.50 or pressure["long_consensus"]>=.667); confirmed=repricing and persistent_counter; present=confirmed or (disagreement and (inflection or persistent_counter)); watch=disagreement or inflection or volatility["directional_expansion"]; stage="CONFIRMED" if confirmed else "PRESENT" if present else "WATCH" if watch else "ABSENT"
    return {"state":stage,"stage":stage,"short_direction":sd,"context_direction":cd,"disagreement":disagreement,"inflection":inflection,"structural_repricing":repricing,"repricing_direction":structure["bos_direction"],"persistent_counter":persistent_counter,"lifecycle":stage}

def _reconcile(structure,pressure,persistence,volatility,range_info,transition,ema_relation,ema_gap):
    sd,pd=structure["direction"],pressure["pressure"]; counter=[]
    if sd in {"UP","DOWN"} and pd in {"UP","DOWN"} and sd!=pd: counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if ema_relation in {"UP","DOWN"} and pd in {"UP","DOWN"} and ema_relation!=pd: counter.append("EMA_CONTEXT_DISAGREES_WITH_PRESSURE")
    if persistence["score"]<.50 and pd in {"UP","DOWN"}: counter.append("PERSISTENCE_WEAK")
    if pressure["long_consensus"]<.667 and pd in {"UP","DOWN"}: counter.append("LONG_HORIZON_NOT_ALIGNED")
    if abs(ema_gap)<.25: counter.append("EMA_SEPARATION_WEAK")
    if range_info["range_confirmed"] and pd in {"UP","DOWN"}: counter.append("RANGE_COMPETES_WITH_DIRECTION")
    directional=pd in {"UP","DOWN"} and persistence["persistent"] and pressure["long_consensus"]>=.667; aligned=sd==pd and sd in {"UP","DOWN"}; strong=aligned and structure["quality"]>=.60
    opposite=structure["external_bos"]=="CONFIRMED_BOS" and structure["bos_direction"] in {"UP","DOWN"} and pd in {"UP","DOWN"} and structure["bos_direction"]!=pd
    if transition["stage"]=="CONFIRMED": state,direction="TRANSITION",transition["repricing_direction"]
    elif opposite: state,direction="TRANSITION",structure["bos_direction"]
    elif range_info["range_confirmed"] and transition["stage"]=="ABSENT": state,direction="RANGE","NEUTRAL"
    elif strong and directional: state,direction=("TREND_UP" if sd=="UP" else "TREND_DOWN"),sd
    elif directional and sd=="NEUTRAL": state,direction=("TREND_UP" if pd=="UP" else "TREND_DOWN"),pd
    elif volatility["compression"] and transition["stage"]=="ABSENT": state,direction="COMPRESSION",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    elif volatility["directional_expansion"] and transition["stage"]=="ABSENT": state,direction="EXPANSION",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    elif transition["stage"] in {"PRESENT","WATCH"}: state,direction="TRANSITION",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    elif aligned and pressure["consensus"]>=.50: state,direction=("TREND_UP" if sd=="UP" else "TREND_DOWN"),sd
    else: state,direction="UNCLEAR",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    support=(.25 if direction==pd else 0)+(.20*structure["quality"] if sd==direction and sd in {"UP","DOWN"} else .08 if sd=="MIXED" else 0)+.20*persistence["score"]+.15*pressure["long_consensus"]+.10*pressure["consensus"]+.10*persistence["consistency"]
    confidence=_clamp(support-min(.30,.06*len(counter)))
    if state=="RANGE": confidence=max(confidence,.55+.25*range_info["range_score"])
    if state=="TRANSITION": confidence=_clamp(confidence*(.92 if transition["stage"]=="CONFIRMED" else .82))
    if state=="UNCLEAR": confidence=min(confidence,.49)
    stability="STABLE" if confidence>=.75 and len(counter)<=1 else "CHALLENGED" if confidence>=.50 else "UNSTABLE"
    dominant=[]
    if structure["quality"]>=.60: dominant.append("STRUCTURE")
    if pressure["consensus"]>=.75: dominant.append("PRESSURE")
    if persistence["persistent"]: dominant.append("PERSISTENCE")
    if pressure["long_consensus"]>=.667: dominant.append("MULTI_HORIZON")
    if range_info["range_confirmed"]: dominant.append("RANGE")
    if volatility["compression"]: dominant.append("VOLATILITY_COMPRESSION")
    if volatility["directional_expansion"]: dominant.append("DIRECTIONAL_EXPANSION")
    if transition["stage"] in {"PRESENT","CONFIRMED"}: dominant.append("TRANSITION_EVIDENCE")
    return {"state":state,"direction":direction,"confidence":confidence,"dominant_evidence":dominant,"counter_evidence":counter,"conflicts":counter,"stability":stability,"evidence_agreement":_clamp(1-len(counter)/5),"directional_alignment":directional,"structural_alignment":aligned,"strong_structure":strong}

def _incomplete(base,n,invalid,reason):
    return {**base,"market_state":"UNCLEAR","direction":"NEUTRAL","directional_pressure":"NEUTRAL","directional_state":"UNRESOLVED","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","structure_direction":"NEUTRAL","structure_quality":0.0,"range_state":"UNKNOWN","compression":"UNKNOWN","expansion":"UNKNOWN","expansion_directional":"UNKNOWN","transition":"UNKNOWN","transition_stage":"UNKNOWN","transition_lifecycle":"UNKNOWN","confidence":0.0,"evidence_strength":0.0,"analysis_status":"INCOMPLETE","reasons":[reason],"reason_codes":[reason],"counter_evidence":[],"conflicts":[],"trade_authority_isolated":True,"trade_decision":None,"entry":None,"risk":None,"reasoning_trace":{"data_quality":{"valid_candles":n,"invalid_candles":invalid,"status":"INCOMPLETE"}}}

def analyze_e1(bars):
    base={"question":QUESTION,"reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN","ownership":OWNERSHIP,"evidence_hierarchy":EVIDENCE_HIERARCHY}
    valid,invalid=_quality(bars)
    if len(valid)<MIN_BARS: return _incomplete(base,len(valid),invalid,"DATA_QUALITY_INSUFFICIENT")
    closes=[b["close"] for b in valid]; a14,a50=_atr(valid,14),_atr(valid,50)
    if a14<=0 or a50<=0: return _incomplete(base,len(valid),invalid,"ATR_INVALID")
    e20,e50=_ema(closes,20),_ema(closes,50); ema_rel="UP" if e20>e50 else "DOWN" if e20<e50 else "FLAT"; gap=(e20-e50)/a14
    structure=_structure(valid,a14); pressure=_pressure(closes,a14); persistence=_persistence(closes,a14,pressure["pressure"]); volatility=_volatility(valid,closes,a14,a50); range_info=_range(valid,closes,a14,structure); transition=_transition(closes,a14,structure,pressure,persistence,volatility); r=_reconcile(structure,pressure,persistence,volatility,range_info,transition,ema_rel,gap)
    state,direction=r["state"],r["direction"]; directional_state="CONFIRMED" if state in {"TREND_UP","TREND_DOWN"} and r["confidence"]>=.70 else "DEVELOPING" if direction in {"UP","DOWN"} else "NEUTRAL"
    obs=[f"valid_candles={len(valid)}",f"invalid_candles={invalid}",f"ema20_vs_ema50={ema_rel}",f"ema_gap_atr={gap:.3f}",f"multi_horizon={','.join(pressure['states'])}",f"directional_consensus={pressure['consensus']:.3f}",f"long_horizon_direction={pressure['long_direction']}",f"long_horizon_consensus={pressure['long_consensus']:.3f}",f"persistence={persistence['score']:.3f}",f"persistence_consistency={persistence['consistency']:.3f}",f"structure={structure['state']}",f"structure_direction={structure['direction']}",f"structure_quality={structure['quality']:.3f}",f"external_bos={structure['external_bos']}",f"volatility_ratio={volatility['ratio']:.3f}",f"range_score={range_info['range_score']:.3f}",f"transition_stage={transition['stage']}"]
    reasons=["DATA_INTEGRITY_VALIDATED"]+["DOMINANT_EVIDENCE="+"+".join(r["dominant_evidence"])] if r["dominant_evidence"] else ["DATA_INTEGRITY_VALIDATED"]
    if r["counter_evidence"]: reasons.append("COUNTER_EVIDENCE_PRESENT")
    trace={"question":QUESTION,"data_quality":{"valid_candles":len(valid),"invalid_candles":invalid,"status":"VALIDATED"},"structure":structure,"pressure":pressure,"persistence":persistence,"volatility":volatility,"range":range_info,"transition":transition,"reconciliation":r,"authority_rule":"STRUCTURE_FIRST; EMA_CONTEXT_ONLY; E1_NEVER_TRADES"}
    return {**base,"market_state":state,"direction":direction,"directional_pressure":pressure["pressure"],"directional_state":directional_state,"trend_state":"UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE","volatility_state":volatility["state"],"structure_state":structure["state"],"structure_direction":structure["direction"],"structure_quality":structure["quality"],"structure_evidence":structure,"pressure":pressure["pressure"],"pressure_evidence":pressure,"persistence":persistence["score"],"persistence_consistency":persistence["consistency"],"persistence_evidence":persistence,"multi_horizon":pressure["states"],"directional_consensus":pressure["consensus"],"long_horizon_direction":pressure["long_direction"],"long_horizon_consensus":pressure["long_consensus"],"ema_relation":ema_rel,"ema_gap_atr":gap,"range_state":"CONFIRMED" if range_info["range_confirmed"] else "UNCONFIRMED","range_score":range_info["range_score"],"range_evidence":range_info,"compression":"ACTIVE" if volatility["compression"] else "INACTIVE","expansion":"ACTIVE" if volatility["volatility_expansion"] else "INACTIVE","expansion_directional":"ACTIVE" if volatility["directional_expansion"] else "INACTIVE","transition":transition["stage"],"transition_stage":transition["stage"],"transition_lifecycle":transition["lifecycle"],"transition_evidence":transition,"dominant_evidence":r["dominant_evidence"],"counter_evidence":r["counter_evidence"],"conflicts":r["conflicts"],"stability":r["stability"],"confidence":r["confidence"],"evidence_strength":r["confidence"],"evidence_agreement":r["evidence_agreement"],"evidence":obs,"observations":obs,"reasons":reasons,"reason_codes":reasons,"reasoning_trace":trace,"analysis_status":"COMPLETE","invalidations":["data_quality_failure","trend_alignment_break","opposite_external_bos","range_containment_break","compression_to_expansion","expansion_efficiency_collapse","transition_evidence_disappears"],"trade_authority_isolated":True,"trade_decision":None,"entry":None,"risk":None}
