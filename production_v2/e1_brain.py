"""E1 Professional Market-State Brain.

E1 answers one question only: "What is the market doing right now?"
It is deliberately isolated from setup, entry, risk and execution authority.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "What is the market doing right now?"
MIN_BARS = 80
PIVOT_WING = 2
MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
EVIDENCE_HIERARCHY = "DATA_QUALITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> MULTI_HORIZON -> VOLATILITY -> RELATIONSHIP -> STABILITY -> TRANSITION -> MARKET_STATE"
OWNERSHIP = {"owns": ["data_integrity", "volatility_regime", "market_structure_context", "directional_pressure", "multi_horizon_alignment", "trend_persistence", "range_regime", "compression_regime", "expansion_regime", "market_regime", "regime_transition", "state_stability", "counter_evidence", "market_state_invalidation"], "does_not_own": ["opportunity_setup", "liquidity_auction", "trade_location", "entry_confirmation", "trade_economics", "risk_management", "trade_execution", "BUY", "SELL"]}

def _clamp(x: float) -> float: return max(0.0, min(1.0, float(x)))
def _num(x: Any) -> float | None:
    try: v = float(x)
    except (TypeError, ValueError): return None
    return v if isfinite(v) else None

def _ema(values: list[float], period: int) -> list[float]:
    if not values: return []
    a = 2.0 / (period + 1.0); cur = values[0]; out = [cur]
    for v in values[1:]: cur = a * v + (1-a) * cur; out.append(cur)
    return out

def _true_ranges(bars):
    out=[]; prev=None
    for b in bars:
        h,l,c=b["high"],b["low"],b["close"]
        out.append(max(h-l, abs(h-prev), abs(l-prev)) if prev is not None else max(h-l,0.0)); prev=c
    return out

def _atr(bars, period):
    if len(bars)<period: return 0.0
    return mean(_true_ranges(bars[-period:]))

def _slope(values, atr, lookback):
    if atr<=0 or len(values)<=lookback: return 0.0
    return (values[-1]-values[-1-lookback])/atr

def _efficiency(values, lookback):
    if len(values)<lookback: return 0.0
    s=values[-lookback:]; path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return _clamp(abs(s[-1]-s[0])/max(path,1e-12))

def _quality(bars):
    valid=[]; invalid=0
    for raw in bars or []:
        if not isinstance(raw,dict): invalid+=1; continue
        v={k:_num(raw.get(k)) for k in ("open","high","low","close")}
        if any(x is None for x in v.values()): invalid+=1; continue
        o,h,l,c=v.values()
        if h<l or h<max(o,c) or l>min(o,c): invalid+=1; continue
        valid.append({**raw,**v})
    return valid,invalid

def _pivots(bars, wing=PIVOT_WING):
    highs=[]; lows=[]
    for i in range(wing,len(bars)-wing):
        w=bars[i-wing:i+wing+1]; h,l=bars[i]["high"],bars[i]["low"]
        if h>=max(x["high"] for x in w): highs.append((i,h))
        if l<=min(x["low"] for x in w): lows.append((i,l))
    return highs,lows

def _structure(bars, atr):
    highs,lows=_pivots(bars); highs,lows=highs[-12:],lows[-12:]
    hh=sum(highs[i][1]>highs[i-1][1] for i in range(1,len(highs))); lh=sum(highs[i][1]<highs[i-1][1] for i in range(1,len(highs)))
    hl=sum(lows[i][1]>lows[i-1][1] for i in range(1,len(lows))); ll=sum(lows[i][1]<lows[i-1][1] for i in range(1,len(lows)))
    bull=min(hh,hl); bear=min(lh,ll); bulls=hh+hl; bears=lh+ll
    if bull>=2 and bull>bear: state,direction,quality="BULLISH","UP",_clamp(.58+.07*bull+.02*max(0,bulls-bears))
    elif bear>=2 and bear>bull: state,direction,quality="BEARISH","DOWN",_clamp(.58+.07*bear+.02*max(0,bears-bulls))
    elif bulls>=3 and bulls>=bears+1: state,direction,quality="BULLISH","UP",.52
    elif bears>=3 and bears>=bulls+1: state,direction,quality="BEARISH","DOWN",.52
    else: state,direction,quality="MIXED","NEUTRAL",.30
    last,prior=bars[-1]["close"],bars[-2]["close"]; ph=highs[-1][1] if highs else last; pl=lows[-1][1] if lows else last; buf=max(.15*atr,1e-12)
    up=last>ph+buf and prior>ph+buf; down=last<pl-buf and prior<pl-buf
    return {"state":state,"direction":direction,"quality":quality,"HH":hh,"HL":hl,"LH":lh,"LL":ll,"bull_score":bulls,"bear_score":bears,"external_bos":"CONFIRMED_BOS" if up or down else "NO_BOS","bos_direction":"UP" if up else "DOWN" if down else "NONE","repricing_strength":1.0 if up or down else 0.0,"protected_high":ph,"protected_low":pl,"acceptance":"UP" if up else "DOWN" if down else "NONE","break_probe":"UP" if last>ph+buf and prior<=ph+buf else "DOWN" if last<pl-buf and prior>=pl-buf else "NONE","swing_count_highs":len(highs),"swing_count_lows":len(lows)}

def _pressure(slopes):
    thresholds=(.15,.20,.30,.40); states=["UP" if s>=t else "DOWN" if s<=-t else "FLAT" for s,t in zip(slopes,thresholds)]; up,down=states.count("UP"),states.count("DOWN"); ls=states[1:]; lu,ld=ls.count("UP"),ls.count("DOWN")
    return {"states":states,"pressure":"UP" if up>down else "DOWN" if down>up else "BALANCED","consensus":max(up,down)/len(states),"long_direction":"UP" if lu>ld else "DOWN" if ld>lu else "NEUTRAL","long_consensus":max(lu,ld)/len(ls),"slope_5":slopes[0],"slope_10":slopes[1],"slope_20":slopes[2],"slope_40":slopes[3]}

def _persistence(closes,atr,pressure):
    windows=(5,10,20,40); values=[_slope(closes,atr,n) for n in windows]; thresholds=(.15,.20,.30,.40)
    hits=sum((v>=t if pressure=="UP" else v<=-t) for v,t in zip(values,thresholds)) if pressure in {"UP","DOWN"} else 0; score=hits/4
    recent=closes[-24:]; dirs=[]; consistency=0.0
    if len(recent)>=18:
        for i in range(0,18,6):
            d=recent[i+5]-recent[i]; dirs.append("UP" if d>0 else "DOWN" if d<0 else "FLAT")
        consistency=sum(x==pressure for x in dirs)/len(dirs) if pressure in {"UP","DOWN"} else 0.0
    return {"score":score,"consistency":consistency,"values":values,"persistent":score>=.75 and consistency>=.667,"block_directions":dirs}

def _range_analysis(bars,closes,atr,structure):
    b20,b40=bars[-21:-1],bars[-41:-1]; hi20,lo20=max(x["high"] for x in b20),min(x["low"] for x in b20); hi40,lo40=max(x["high"] for x in b40),min(x["low"] for x in b40); w20=max(hi20-lo20,1e-12); w40=max(hi40-lo40,1e-12)
    p20=_clamp((closes[-1]-lo20)/w20); p40=_clamp((closes[-1]-lo40)/w40); e20,e40=_efficiency(closes,20),_efficiency(closes,40); contained=sum(lo40<=x["close"]<=hi40 for x in bars[-20:])/20; balance=1-abs(p20-.5)*2; reject=1.0 if (p20<=.2 and closes[-1]>=closes[-2]) or (p20>=.8 and closes[-1]<=closes[-2]) else 0.0
    score=_clamp(.20*balance+.20*(1-e20)+.15*(1-e40)+.25*contained+.10*(structure["state"]=="MIXED")+.10*reject); confirmed=score>=.62 and e20<.45 and e40<.55 and w40/max(atr,1e-12)<=10 and contained>=.80
    return {"range_score":score,"range_confirmed":confirmed,"position_20":p20,"position_40":p40,"range_high_20":hi20,"range_low_20":lo20,"range_high_40":hi40,"range_low_40":lo40,"width20_atr":w20/max(atr,1e-12),"width40_atr":w40/max(atr,1e-12),"efficiency_20":e20,"efficiency_40":e40,"contained40":contained,"boundary_rejection":reject}

def _volatility(bars,atr14,atr50,closes):
    ratio=atr14/max(atr50,1e-12); ranges=[x["high"]-x["low"] for x in bars]; sr=mean(ranges[-5:])/max(mean(ranges[-20:]),1e-12); e10=_efficiency(closes,10); s5=abs(_slope(closes,atr14,5)); state="EXPANDING" if ratio>=1.12 else "CONTRACTING" if ratio<=.82 else "NORMAL"
    # Expansion is confirmed only when it persists for multiple bars; one-bar spikes are probes.
    recent_ratios=[]
    for end in range(max(50,len(bars)-5),len(bars)+1):
        sample=bars[:end]; a14=_atr(sample,14); a50=_atr(sample,50); recent_ratios.append(a14/max(a50,1e-12))
    exp_persist=sum(r>=1.08 for r in recent_ratios[-3:])>=2
    directional=state=="EXPANDING" and exp_persist and e10>=.30 and s5>=.25
    compression=state=="CONTRACTING" and sr<=.90 and e10<=.55 and sum(r<=.92 for r in recent_ratios[-3:])>=2
    return {"state":state,"ratio":ratio,"short_range_ratio":sr,"volatility_expansion":state=="EXPANDING","directional_expansion":directional,"compression":compression,"efficiency10":e10,"slope5_abs":s5,"expansion_persistence":exp_persist}

def _transition(closes,atr,structure,pressure,persistence,volatility):
    s8=_slope(closes,atr,8); s30=_slope(closes,atr,30); sd="UP" if s8>.20 else "DOWN" if s8<-.20 else "FLAT"; cd="UP" if s30>.35 else "DOWN" if s30<-.35 else "FLAT"
    disagreement=structure["direction"] in {"UP","DOWN"} and pressure["pressure"] in {"UP","DOWN"} and structure["direction"]!=pressure["pressure"]; inflection=sd in {"UP","DOWN"} and cd in {"UP","DOWN"} and sd!=cd; repricing=structure["external_bos"]=="CONFIRMED_BOS"; persistent_counter=disagreement and (persistence["score"]>=.50 or pressure["long_consensus"]>=.667); confirmed=repricing and persistent_counter; present=confirmed or disagreement and (inflection or persistent_counter); watch=disagreement or inflection or volatility["directional_expansion"]; stage="CONFIRMED" if confirmed else "PRESENT" if present else "WATCH" if watch else "ABSENT"
    return {"state":stage,"stage":stage,"short_direction":sd,"context_direction":cd,"disagreement":disagreement,"inflection":inflection,"structural_repricing":repricing,"repricing_direction":structure["bos_direction"],"persistent_counter":persistent_counter,"lifecycle":stage}

def _reconcile(*,structure,pressure,persistence,volatility,range_info,transition,ema_relation,ema_gap_atr):
    counter=[]; sd,pd=structure["direction"],pressure["pressure"]
    if sd in {"UP","DOWN"} and pd in {"UP","DOWN"} and sd!=pd: counter.append("STRUCTURE_DISAGREES_WITH_PRESSURE")
    if ema_relation in {"UP","DOWN"} and pd in {"UP","DOWN"} and ema_relation!=pd: counter.append("EMA_CONTEXT_DISAGREES_WITH_PRESSURE")
    if persistence["score"]<.50 and pd in {"UP","DOWN"}: counter.append("PERSISTENCE_WEAK")
    if pressure["long_consensus"]<.667 and pd in {"UP","DOWN"}: counter.append("LONG_HORIZON_NOT_ALIGNED")
    if abs(ema_gap_atr)<.25: counter.append("EMA_SEPARATION_WEAK")
    if range_info["range_confirmed"] and pd in {"UP","DOWN"}: counter.append("RANGE_COMPETES_WITH_DIRECTION")
    dominant=[]
    if sd in {"UP","DOWN"} and structure["quality"]>=.60: dominant.append("STRUCTURE")
    if pd in {"UP","DOWN"} and pressure["consensus"]>=.75: dominant.append("PRESSURE")
    if persistence["persistent"]: dominant.append("PERSISTENCE")
    if pressure["long_consensus"]>=.667: dominant.append("MULTI_HORIZON")
    if range_info["range_confirmed"]: dominant.append("RANGE")
    if volatility["compression"]: dominant.append("VOLATILITY_COMPRESSION")
    if volatility["directional_expansion"]: dominant.append("DIRECTIONAL_EXPANSION")
    if transition["stage"] in {"PRESENT","CONFIRMED"}: dominant.append("TRANSITION_EVIDENCE")
    directional=pd in {"UP","DOWN"} and persistence["persistent"] and pressure["long_consensus"]>=.667; align=sd==pd and sd in {"UP","DOWN"}; strong=align and structure["quality"]>=.60
    # Hard authority gates: opposite confirmed repricing and unresolved high-authority conflict cannot be overridden by context.
    opposite_bos=structure["external_bos"]=="CONFIRMED_BOS" and structure["bos_direction"] in {"UP","DOWN"} and pd in {"UP","DOWN"} and structure["bos_direction"]!=pd
    if transition["stage"]=="CONFIRMED": state,direction="TRANSITION",transition_dir=transition["repricing_direction"]
    elif opposite_bos: state,direction="TRANSITION",transition_dir=structure["bos_direction"]
    elif range_info["range_confirmed"] and transition["stage"]=="ABSENT": state,direction="RANGE","NEUTRAL"
    elif strong and directional: state,direction=("TREND_UP" if sd=="UP" else "TREND_DOWN"),sd
    elif directional and sd=="NEUTRAL": state,direction=("TREND_UP" if pd=="UP" else "TREND_DOWN"),pd
    elif volatility["compression"] and transition["stage"]=="ABSENT": state,direction="COMPRESSION",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    elif volatility["directional_expansion"] and transition["stage"]=="ABSENT": state,direction="EXPANSION",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    elif transition["stage"] in {"PRESENT","WATCH"}: state,direction="TRANSITION",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    elif sd in {"UP","DOWN"} and pd==sd and pressure["consensus"]>=.50: state,direction=("TREND_UP" if sd=="UP" else "TREND_DOWN"),sd
    else: state,direction="UNCLEAR",pd if pd in {"UP","DOWN"} else "NEUTRAL"
    support=0
    if direction in {"UP","DOWN"} and pd==direction: support+=.25
    if sd==direction and sd in {"UP","DOWN"}: support+=.20*structure["quality"]
    elif sd=="MIXED": support+=.08
    support+=.20*persistence["score"]+.15*pressure["long_consensus"]+.10*pressure["consensus"]+.10*persistence["consistency"]
    confidence=_clamp(support-min(.30,.06*len(counter)))
    if state=="RANGE": confidence=_clamp(max(confidence,.55+.25*range_info["range_score"]))
    elif state=="TRANSITION": confidence=_clamp(confidence*(.92 if transition["stage"]=="CONFIRMED" else .82))
    elif state=="UNCLEAR": confidence=min(confidence,.49)
    stability="STABLE" if confidence>=.75 and len(counter)<=1 else "CHALLENGED" if confidence>=.50 else "UNSTABLE"
    return {"state":state,"direction":direction,"confidence":confidence,"dominant_evidence":dominant,"counter_evidence":counter,"conflicts":counter,"stability":stability,"evidence_agreement":_clamp(1-min(len(counter),5)/5),"directional_alignment":directional,"structural_alignment":align,"strong_structure":strong}

def _incomplete(base,valid,invalid,reason):
    return {**base,"market_state":"UNCLEAR","direction":"NEUTRAL","directional_pressure":"NEUTRAL","directional_state":"UNRESOLVED","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","structure_direction":"NEUTRAL","structure_quality":0.0,"range_state":"UNKNOWN","compression":"UNKNOWN","expansion":"UNKNOWN","expansion_directional":"UNKNOWN","transition":"UNKNOWN","transition_stage":"UNKNOWN","transition_lifecycle":"UNKNOWN","confidence":0.0,"evidence_strength":0.0,"evidence":[f"valid_candles={valid}",f"invalid_candles={invalid}"],"observations":[],"conflicts":[],"counter_evidence":[],"dominant_evidence":[],"reasons":[reason],"reason_codes":[reason],"reasoning_trace":{"data_quality":{"valid_candles":valid,"invalid_candles":invalid,"status":"INCOMPLETE"},"reconciliation":{"state":"UNCLEAR","confidence":0.0}},"analysis_status":"INCOMPLETE","trade_authority_isolated":True,"trade_decision":None,"entry":None,"risk":None}

def analyze_e1(bars):
    base={"question":QUESTION,"reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY","architecture":"E1_SINGLE_PROFESSIONAL_BRAIN","ownership":OWNERSHIP,"evidence_hierarchy":EVIDENCE_HIERARCHY}
    valid,invalid=_quality(bars)
    if len(valid)<MIN_BARS: return _incomplete(base,len(valid),invalid,"DATA_QUALITY_INSUFFICIENT")
    closes=[b["close"] for b in valid]; atr14,atr50=_atr(valid,14),_atr(valid,50)
    if atr14<=0 or atr50<=0: return _incomplete(base,len(valid),invalid,"ATR_INVALID")
    ema20,ema50=_ema(closes,20),_ema(closes,50); ema_relation="UP" if ema20[-1]>ema50[-1] else "DOWN" if ema20[-1]<ema50[-1] else "FLAT"; ema_gap_atr=(ema20[-1]-ema50[-1])/atr14
    slopes=[_slope(closes,atr14,n) for n in (5,10,20,40)]; pressure=_pressure(slopes); persistence=_persistence(closes,atr14,pressure["pressure"]); structure=_structure(valid,atr14); range_info=_range_analysis(valid,closes,atr14,structure); volatility=_volatility(valid,atr14,atr50,closes); transition=_transition(closes,atr14,structure,pressure,persistence,volatility); r=_reconcile(structure=structure,pressure=pressure,persistence=persistence,volatility=volatility,range_info=range_info,transition=transition,ema_relation=ema_relation,ema_gap_atr=ema_gap_atr)
    state,direction=r["state"],r["direction"]; directional_state="CONFIRMED" if state in {"TREND_UP","TREND_DOWN"} and r["confidence"]>=.70 else "DEVELOPING" if direction in {"UP","DOWN"} else "NEUTRAL"
    obs=[f"valid_candles={len(valid)}",f"invalid_candles={invalid}",f"ema20_vs_ema50={ema_relation}",f"ema_gap_atr={ema_gap_atr:.3f}",f"multi_horizon={','.join(pressure['states'])}",f"directional_consensus={pressure['consensus']:.3f}",f"long_horizon_direction={pressure['long_direction']}",f"long_horizon_consensus={pressure['long_consensus']:.3f}",f"persistence={persistence['score']:.3f}",f"persistence_consistency={persistence['consistency']:.3f}",f"structure={structure['state']}",f"structure_direction={structure['direction']}",f"structure_quality={structure['quality']:.3f}",f"external_bos={structure['external_bos']}",f"volatility_ratio={volatility['ratio']:.3f}",f"range_score={range_info['range_score']:.3f}",f"transition_stage={transition['stage']}"]
    reasons=["DATA_INTEGRITY_VALIDATED"]
    if r["dominant_evidence"]: reasons.append("DOMINANT_EVIDENCE="+"+".join(r["dominant_evidence"]))
    if r["counter_evidence"]: reasons.append("COUNTER_EVIDENCE_PRESENT")
    if volatility["compression"]: reasons.append("VOLATILITY_COMPRESSION_DETECTED")
    if volatility["directional_expansion"]: reasons.append("DIRECTIONAL_EXPANSION_DETECTED")
    if transition["stage"]=="WATCH": reasons.append("TRANSITION_WATCH_ONLY")
    elif transition["stage"]=="PRESENT": reasons.append("REGIME_TRANSITION_PRESENT")
    elif transition["stage"]=="CONFIRMED": reasons.append("REGIME_TRANSITION_CONFIRMED")
    if ema_relation in {"UP","DOWN"}: reasons.append("EMA_AS_CONTEXT_NOT_AUTHORITY")
    if structure["external_bos"]=="CONFIRMED_BOS": reasons.append("EXTERNAL_REPRICING_CONFIRMED")
    trace={"question":QUESTION,"data_quality":{"valid_candles":len(valid),"invalid_candles":invalid,"status":"VALIDATED"},"volatility":volatility,"trend":{"structure":structure["state"],"structure_direction":structure["direction"],"structure_quality":structure["quality"],"pressure":pressure["pressure"],"persistence":persistence["score"],"persistence_consistency":persistence["consistency"],"multi_horizon":pressure["states"],"long_horizon_direction":pressure["long_direction"],"long_horizon_consensus":pressure["long_consensus"]},"range":range_info,"compression":{"active":volatility["compression"],"volatility_state":volatility["state"]},"expansion":{"volatility":volatility["volatility_expansion"],"directional":volatility["directional_expansion"]},"transition":transition,"reconciliation":r,"authority_rule":"STRUCTURE_FIRST; EMA_CONTEXT_ONLY; E1_NEVER_TRADES"}
    return {**base,"market_state":state,"direction":direction,"directional_pressure":pressure["pressure"],"directional_state":directional_state,"trend_state":"UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE","volatility_state":volatility["state"],"structure_state":structure["state"],"structure_direction":structure["direction"],"structure_quality":structure["quality"],"structure_evidence":structure,"pressure":pressure["pressure"],"pressure_evidence":pressure,"persistence":persistence["score"],"persistence_consistency":persistence["consistency"],"persistence_evidence":persistence,"multi_horizon":pressure["states"],"directional_consensus":pressure["consensus"],"long_horizon_direction":pressure["long_direction"],"long_horizon_consensus":pressure["long_consensus"],"ema_relation":ema_relation,"ema_gap_atr":ema_gap_atr,"range_state":"CONFIRMED" if range_info["range_confirmed"] else "UNCONFIRMED","range_score":range_info["range_score"],"range_evidence":range_info,"compression":"ACTIVE" if volatility["compression"] else "INACTIVE","expansion":"ACTIVE" if volatility["volatility_expansion"] else "INACTIVE","expansion_directional":"ACTIVE" if volatility["directional_expansion"] else "INACTIVE","transition":transition["stage"],"transition_stage":transition["stage"],"transition_lifecycle":transition["lifecycle"],"transition_evidence":transition,"dominant_evidence":r["dominant_evidence"],"counter_evidence":r["counter_evidence"],"conflicts":r["conflicts"],"stability":r["stability"],"confidence":r["confidence"],"evidence_strength":r["confidence"],"evidence_agreement":r["evidence_agreement"],"evidence":obs,"observations":obs,"reasons":reasons,"reason_codes":reasons,"reasoning_trace":trace,"analysis_status":"COMPLETE","invalidations":["market_state_invalid_if_data_quality_fails","trend_invalid_if_directional_pressure_persistence_and_horizon_alignment_break","trend_direction_must_be_reassessed_when_opposite_external_bos_confirms","range_invalid_if_boundary_containment_breaks","compression_invalid_if_volatility_expands","expansion_invalid_if_directional_efficiency_collapses","transition_invalid_if_structural_repricing_or_persistent_counter_flow_disappears"],"trade_authority_isolated":True,"trade_decision":None,"entry":None,"risk":None}
