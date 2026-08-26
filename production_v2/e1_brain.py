from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any

MARKET_STATES = {"TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "EXPANSION", "TRANSITION", "UNCLEAR"}
PROFESSIONAL_QUESTION = "What is the market doing right now?"
CORE_QUESTION = "What state is the market currently in, what is changing, and what type of opportunity environment does that create?"
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"


def _num(value: Any) -> float | None:
    try: value = float(value)
    except (TypeError, ValueError): return None
    return value if isfinite(value) else None


def _clean_bars(bars: list[dict[str, Any]] | None):
    valid, problems = [], []
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict): problems.append(f"bar_{i}_not_mapping"); continue
        values = {k: _num(bar.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()): problems.append(f"bar_{i}_ohlc_invalid"); continue
        o,h,l,c = values["open"],values["high"],values["low"],values["close"]
        if h < max(o,c) or l > min(o,c) or h < l: problems.append(f"bar_{i}_ohlc_inconsistent"); continue
        valid.append({**bar, **values})
    return valid, problems


def _ema(values, period):
    if not values: return 0.0
    a = 2.0/(period+1.0); value = values[0]
    for item in values[1:]: value = a*item+(1-a)*value
    return value


def _true_ranges(bars):
    out=[]; previous=None
    for b in bars:
        h,l,c=float(b["high"]),float(b["low"]),float(b["close"])
        out.append(h-l if previous is None else max(h-l,abs(h-previous),abs(l-previous))); previous=c
    return out


def _atr(bars, period=14):
    trs=_true_ranges(bars[-period:]); return mean(trs) if trs else 0.0


def _atr_ratio(bars, short=14, long=50): return _atr(bars,short)/max(_atr(bars,long),1e-12)


def _pivots(bars, wing=2):
    highs,lows=[],[]
    for i in range(wing,max(wing,len(bars)-wing)):
        w=bars[i-wing:i+wing+1]; h=float(bars[i]["high"]); l=float(bars[i]["low"])
        if h>=max(float(x["high"]) for x in w): highs.append(h)
        if l<=min(float(x["low"]) for x in w): lows.append(l)
    return highs,lows


def _efficiency(closes, lookback):
    s=closes[-lookback:]
    if len(s)<2:return 0.0
    path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return abs(s[-1]-s[0])/max(path,1e-12)


def _slope_atr(closes, atr, lookback):
    if len(closes)<=lookback or atr<=0:return 0.0
    return (closes[-1]-closes[-1-lookback])/atr


def _structure(bars):
    highs,lows=_pivots(bars); rh,rl=highs[-5:],lows[-5:]
    hh=sum(rh[i]>rh[i-1] for i in range(1,len(rh))); lh=sum(rh[i]<rh[i-1] for i in range(1,len(rh)))
    hl=sum(rl[i]>rl[i-1] for i in range(1,len(rl))); ll=sum(rl[i]<rl[i-1] for i in range(1,len(rl)))
    bp,bear=min(hh,hl),min(lh,ll)
    if bp>=2 and bp>bear: state,q="BULLISH",min(1.0,.62+.10*bp)
    elif bear>=2 and bear>bp: state,q="BEARISH",min(1.0,.62+.10*bear)
    elif hh+hl>=2 and hh+hl>lh+ll: state,q="BULLISH",.54
    elif lh+ll>=2 and lh+ll>hh+hl: state,q="BEARISH",.54
    else: state,q="MIXED",.30
    return state,q,{"pivot_highs":rh,"pivot_lows":rl,"higher_highs":hh,"lower_highs":lh,"higher_lows":hl,"lower_lows":ll}


def _persistence(closes,atr,direction):
    if direction not in {"UP","DOWN"}: return 0.0,{"aligned_windows":0,"windows":{}}
    values={}; aligned=0
    for lb,threshold in ((5,.15),(10,.25),(20,.40)):
        v=_slope_atr(closes,atr,lb); values[str(lb)]=round(v,4)
        aligned += int(v>=threshold if direction=="UP" else v<=-threshold)
    return aligned/3.0,{"aligned_windows":aligned,"windows":values}


def _volatility(bars):
    ranges=[float(b["high"])-float(b["low"]) for b in bars]; ratio=_atr_ratio(bars)
    recent=mean(ranges[-6:]); baseline=mean(ranges[-26:-6]) if len(ranges)>=26 else median(ranges[:-6] or ranges)
    rr=recent/max(baseline,1e-12); compression=ratio<.78 and rr<.82; expansion=ratio>1.18 or rr>=1.35
    return ("EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"),compression,expansion,{"atr_short_long_ratio":round(ratio,4),"recent_vs_baseline_range":round(rr,4)}


def _range_analysis(bars,atr,efficiency):
    closes=[float(b["close"]) for b in bars]; sample=closes[-20:]
    if len(sample)<5 or atr<=0:return 0.0,{"channel_width_atr":0.0,"boundary_rejections":0,"efficiency":efficiency}
    width=(max(sample)-min(sample))/atr
    hi=sum(float(b["high"])>=max(sample)-.35*atr and float(b["close"])<max(sample)-.10*atr for b in bars[-20:])
    lo=sum(float(b["low"])<=min(sample)+.35*atr and float(b["close"])>min(sample)+.10*atr for b in bars[-20:])
    containment=max(0,min(1,1-max(0,width-5)/5)); chop=max(0,min(1,(.55-efficiency)/.55)); rejection=min(1,(hi+lo)/4)
    return .45*containment+.35*chop+.20*rejection,{"channel_width_atr":round(width,4),"boundary_rejections":hi+lo,"efficiency":round(efficiency,4)}


def _tf_context(bars,label):
    valid,problems=_clean_bars(bars)
    if len(valid)<60:return {"available":False,"state":"UNAVAILABLE","direction":"NONE","confidence":0.0,"problems":problems or [f"{label}_insufficient_data"]}
    closes=[float(b["close"]) for b in valid]; atr=_atr(valid); e20,e50=_ema(closes,20),_ema(closes,50); slope=_slope_atr(closes,atr,10); structure,sq,_=_structure(valid)
    ema_dir="UP" if e20>e50 else "DOWN" if e20<e50 else "FLAT"; slope_dir="UP" if slope>.15 else "DOWN" if slope<-.15 else "FLAT"; struct_dir="UP" if structure=="BULLISH" else "DOWN" if structure=="BEARISH" else "NONE"
    dirs=[d for d in (ema_dir,slope_dir,struct_dir) if d in {"UP","DOWN"}]; direction="UP" if dirs.count("UP")>=2 else "DOWN" if dirs.count("DOWN")>=2 else "NONE"
    return {"available":True,"state":"DIRECTIONAL" if direction!="NONE" else "BALANCED","direction":direction,"confidence":round((max(dirs.count("UP"),dirs.count("DOWN"))/3)*.6+sq*.4,4),"structure":structure,"ema_direction":ema_dir,"slope_atr":round(slope,4)}


def analyze_e1(bars, *, m15_bars=None, h1_bars=None):
    valid,data_problems=_clean_bars(bars)
    if len(valid)<60:
        return {"question":PROFESSIONAL_QUESTION,"market_state":"UNCLEAR","directional_pressure":"BALANCED","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","compression":"UNKNOWN","expansion":"UNKNOWN","transition":"UNKNOWN","confidence":0.0,"evidence":["valid_candles_below_minimum",*data_problems[:6]],"conflicts":[],"reasoning_trace":["QUESTION -> DATA_QUALITY -> insufficient valid M5 candles -> classification withheld"],"professional_reasoning":{"question":PROFESSIONAL_QUESTION,"core_question":CORE_QUESTION,"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":"UNCLEAR","evidence_hierarchy":EVIDENCE_HIERARCHY,"evidence_dimensions":["trend","range","compression","expansion","transition"],"trend_persistence":{"aligned_windows":0,"windows":{}},"conflict_detected":bool(data_problems),"confidence_meaning":"MARKET_STATE_CLASSIFICATION_ONLY","opportunity_environment":"INSUFFICIENT_DATA","uncertainties":["insufficient_m5_data"]},"analysis_status":"INCOMPLETE","reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY"}
    highs=[float(b["high"]) for b in valid]; lows=[float(b["low"]) for b in valid]; closes=[float(b["close"]) for b in valid]; atr=_atr(valid); e20,e50=_ema(closes,20),_ema(closes,50); gap=abs(e20-e50)/max(atr,1e-12)
    ema_dir="UP" if e20>e50 else "DOWN" if e20<e50 else "FLAT"; short=_slope_atr(closes,atr,5); medium=_slope_atr(closes,atr,10); long=_slope_atr(closes,atr,20); slope_dir="UP" if medium>.15 else "DOWN" if medium<-.15 else "FLAT"
    structure,sq,sd=_structure(valid); struct_dir="UP" if structure=="BULLISH" else "DOWN" if structure=="BEARISH" else "NONE"; vol,compression,expansion,vd=_volatility(valid); eff10=_efficiency(closes,10); eff20=_efficiency(closes,20)
    up=int(ema_dir=="UP")+int(slope_dir=="UP")+int(struct_dir=="UP"); down=int(ema_dir=="DOWN")+int(slope_dir=="DOWN")+int(struct_dir=="DOWN"); pressure="UP" if up>=2 and up>down else "DOWN" if down>=2 and down>up else "BALANCED"; persistence,pd=_persistence(closes,atr,pressure); rq,rd=_range_analysis(valid,atr,eff20)
    ema_struct=(ema_dir=="UP" and structure=="BEARISH") or (ema_dir=="DOWN" and structure=="BULLISH"); pressure_struct=(pressure=="UP" and structure=="BEARISH") or (pressure=="DOWN" and structure=="BULLISH"); short_long=(long>.45 and short<-.20) or (long<-.45 and short>.20); ema_slope=(ema_dir=="UP" and medium<-.15) or (ema_dir=="DOWN" and medium>.15); failed=(highs[-1]>max(highs[-21:-1]) and closes[-1]<max(highs[-21:-1])) or (lows[-1]<min(lows[-21:-1]) and closes[-1]>min(lows[-21:-1]))
    tq=.30*persistence+.25*sq+.20*min(1,gap/.80)+.15*min(1,abs(medium)/.80)+.10*min(1,eff20/.65)
    if ema_struct:tq-=.20
    if pressure_struct:tq-=.15
    if short_long or ema_slope:tq-=.10
    tq=max(0,min(1,tq)); strong=pressure in {"UP","DOWN"} and persistence>=2/3 and sq>=.60 and tq>=.65 and not pressure_struct
    transition=pressure_struct or short_long or ema_slope or failed or (persistence<1/3 and abs(medium)>=.45) or (gap<.18 and abs(medium)>=.70)
    if transition and not strong: state="TRANSITION"
    elif compression and not strong: state="COMPRESSION"
    elif strong and pressure=="UP": state="TREND_UP"
    elif strong and pressure=="DOWN": state="TREND_DOWN"
    elif rq>=.55 and pressure=="BALANCED" and not expansion: state="RANGE"
    elif expansion: state="EXPANSION"
    else: state="UNCLEAR"
    trend_state="UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE"
    m15=_tf_context(m15_bars,"M15"); h1=_tf_context(h1_bars,"H1"); mtf_available=bool(m15.get("available") and h1.get("available")); mtf_dirs=[x.get("direction") for x in (m15,h1) if x.get("available") and x.get("direction") in {"UP","DOWN"}]; mtf_conflict=bool(mtf_dirs and trend_state in {"UP","DOWN"} and any(d!=trend_state for d in mtf_dirs))
    conflicts=[]
    if data_problems:conflicts.append("data_quality_anomalies_present")
    if ema_struct:conflicts.append("ema_structure_disagreement")
    if pressure_struct:conflicts.append(f"pressure_structure_disagreement:{pressure}:{structure}")
    if short_long:conflicts.append("short_long_slope_disagreement")
    if ema_slope:conflicts.append("ema_slope_disagreement")
    if failed:conflicts.append("failed_break_or_liquidity_event")
    if mtf_conflict:conflicts.append("mtf_context_conflict")
    confidence=.25*sq+.25*persistence+.20*min(1,abs(medium)/.80)+.15*min(1,gap/.80)+.15*{"TREND_UP":.95,"TREND_DOWN":.95,"RANGE":.80,"COMPRESSION":.82,"EXPANSION":.68,"TRANSITION":.55,"UNCLEAR":.35}[state]-.10*min(1,len(conflicts)/3)-(.05 if mtf_conflict else 0); confidence=max(0,min(1,confidence))
    env={"TREND_UP":"DIRECTIONAL_ENVIRONMENT_WITHOUT_ENTRY_AUTHORIZATION","TREND_DOWN":"DIRECTIONAL_ENVIRONMENT_WITHOUT_ENTRY_AUTHORIZATION","RANGE":"BALANCED_TWO_SIDED_ENVIRONMENT","COMPRESSION":"CONTRACTING_ENVIRONMENT_AWAITING_EXPANSION","EXPANSION":"VOLATILITY_EXPANSION_ENVIRONMENT_DIRECTION_NOT_YET_PRIMARY","TRANSITION":"CHANGING_OR_UNRESOLVED","UNCLEAR":"CHANGING_OR_UNRESOLVED"}[state]
    uncertainties=[]
    if ema_struct:uncertainties.append("ema_structure_disagreement")
    if short_long or ema_slope:uncertainties.append("multi_horizon_slope_disagreement")
    if mtf_conflict:uncertainties.append("mtf_context_conflict")
    if state=="TRANSITION":uncertainties.append("state_is_changing_not_stable")
    if state=="UNCLEAR":uncertainties.append("evidence_not_strong_enough_for_primary_state")
    if not mtf_available:uncertainties.append("mtf_context_unavailable")
    evidence=[f"ema20_vs_ema50={ema_dir}",f"ema_gap_atr={gap:.3f}",f"price_slope_short_atr={short:.3f}",f"price_slope_medium_atr={medium:.3f}",f"price_slope_long_atr={long:.3f}",f"structure={structure}",f"structure_quality={sq:.3f}",f"directional_pressure={pressure}",f"directional_consensus={max(up,down)}/3",f"trend_persistence={persistence:.3f}",f"price_efficiency_10={eff10:.3f}",f"price_efficiency_20={eff20:.3f}",f"range_quality={rq:.3f}",f"recent_vs_baseline_range={vd['recent_vs_baseline_range']:.3f}",f"atr_short_long_ratio={vd['atr_short_long_ratio']:.3f}",f"compression={compression}",f"expansion={expansion}",f"transition={transition}",f"mtf_available={mtf_available}"]
    trace=[f"QUESTION: {PROFESSIONAL_QUESTION}",f"CORE_QUESTION: {CORE_QUESTION}",f"1 DATA_QUALITY: valid_m5={len(valid)}; anomalies={len(data_problems)}.",f"2 VOLATILITY: {vol}; compression={compression}; expansion={expansion}.",f"3 STRUCTURE: {structure}; quality={sq:.2f}; HH={sd['higher_highs']}; HL={sd['higher_lows']}; LH={sd['lower_highs']}; LL={sd['lower_lows']}.",f"4 PRESSURE: {pressure}; EMA={ema_dir}; slope={slope_dir}; votes={up}/{down}.",f"5 PERSISTENCE: {persistence:.2f}; windows={pd['windows']}.",f"6 STATE: trend_quality={tq:.2f}; range_quality={rq:.2f}; primary={state}.",f"7 TRANSITION: {'PRESENT' if transition else 'ABSENT'}; conflicts={conflicts or ['none']}.",f"MTF_CONTEXT: M15={m15.get('direction','NONE')}; H1={h1.get('direction','NONE')}; conflict={mtf_conflict}; M5 remains primary.",f"CONFIDENCE: {confidence:.2f}; classification confidence only.","BOUNDARY: E1 stops at market-state analysis; no setup, entry, risk, target, sizing, or execution decision."]
    return {"question":PROFESSIONAL_QUESTION,"market_state":state,"directional_pressure":pressure,"trend_state":trend_state,"volatility_state":vol,"structure_state":structure,"compression":"PRESENT" if compression else "ABSENT","expansion":"PRESENT" if expansion else "ABSENT","transition":"PRESENT" if transition else "ABSENT","confidence":round(confidence,4),"evidence":evidence,"conflicts":conflicts,"reasoning_trace":trace,"professional_reasoning":{"question":PROFESSIONAL_QUESTION,"core_question":CORE_QUESTION,"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":state,"directional_pressure":pressure,"trend_state":trend_state,"volatility_state":vol,"structure_state":structure,"evidence_dimensions":["trend","range","compression","expansion","transition"],"trend_quality":round(tq,4),"range_quality":round(rq,4),"trend_persistence":pd,"conflict_matrix":{"ema_vs_structure":ema_struct,"pressure_vs_structure":pressure_struct,"short_vs_long_slope":short_long,"ema_vs_slope":ema_slope,"mtf":mtf_conflict},"conflict_detected":bool(conflicts),"confidence_meaning":"MARKET_STATE_CLASSIFICATION_ONLY","opportunity_environment":env,"uncertainties":list(dict.fromkeys(uncertainties)),"mtf_context":{"available":mtf_available,"m5_primary":True,"override_m5":False,"conflict":mtf_conflict,"M15":m15,"H1":h1},"independent_evidence":{"ema_relationship":ema_dir,"ema_gap_atr":round(gap,4),"price_slope_short_atr":round(short,4),"price_slope_medium_atr":round(medium,4),"price_slope_long_atr":round(long,4),"structure":structure,"structure_quality":round(sq,4),"range_quality":round(rq,4),"price_efficiency_10":round(eff10,4),"price_efficiency_20":round(eff20,4),"atr_short_long_ratio":vd["atr_short_long_ratio"],"recent_vs_baseline_range":vd["recent_vs_baseline_range"]},"next_question":"WHAT_IS_CHANGING_NEXT_AND_IS_THE_CURRENT_STATE_STABLE?"},"analysis_status":"COMPLETE","reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY"}
