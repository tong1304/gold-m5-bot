from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Any

MARKET_STATES={"TREND_UP","TREND_DOWN","RANGE","COMPRESSION","EXPANSION","TRANSITION","UNCLEAR"}
PROFESSIONAL_QUESTION="What is the market doing right now?"
EVIDENCE_HIERARCHY="DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"


def _num(v:Any)->float|None:
    try: x=float(v)
    except (TypeError,ValueError): return None
    return x if isfinite(x) else None


def _clean_bars(bars):
    valid=[]; problems=[]
    for i,b in enumerate(bars or []):
        if not isinstance(b,dict): problems.append(f"bar_{i}_not_mapping"); continue
        vals={k:_num(b.get(k)) for k in ("open","high","low","close")}
        if any(v is None for v in vals.values()): problems.append(f"bar_{i}_ohlc_invalid"); continue
        o,h,l,c=vals["open"],vals["high"],vals["low"],vals["close"]
        if h<max(o,c) or l>min(o,c) or h<l: problems.append(f"bar_{i}_ohlc_inconsistent"); continue
        valid.append({**b,**vals})
    return valid,problems


def _ema_series(values,period):
    if not values:return []
    a=2.0/(period+1.0); x=values[0]; out=[x]
    for v in values[1:]: x=a*v+(1-a)*x; out.append(x)
    return out


def _true_ranges(bars):
    out=[]; prev=None
    for b in bars:
        h,l,c=float(b["high"]),float(b["low"]),float(b["close"])
        out.append(h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev))); prev=c
    return out


def _atr(bars,period=14):
    trs=_true_ranges(bars[-period:]); return mean(trs) if trs else 0.0


def _atr_ratio(bars): return _atr(bars,14)/max(_atr(bars,50),1e-12)


def _slope_atr(values,atr,lookback):
    if len(values)<=lookback or atr<=0:return 0.0
    return (values[-1]-values[-1-lookback])/atr


def _direction(v,t=0.15): return "UP" if v>t else "DOWN" if v<-t else "FLAT"


def _efficiency(closes,lookback):
    s=closes[-lookback:]
    if len(s)<2:return 0.0
    path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return abs(s[-1]-s[0])/max(path,1e-12)


def _signed_efficiency(closes,lookback):
    s=closes[-lookback:]
    if len(s)<2:return 0.0
    path=sum(abs(s[i]-s[i-1]) for i in range(1,len(s)))
    return (s[-1]-s[0])/max(path,1e-12)


def _pivots(bars,wing=2):
    highs=[]; lows=[]
    if len(bars)<2*wing+1:return highs,lows
    for i in range(wing,len(bars)-wing):
        w=bars[i-wing:i+wing+1]; h=float(bars[i]["high"]); l=float(bars[i]["low"])
        if h>=max(float(x["high"]) for x in w):highs.append(h)
        if l<=min(float(x["low"]) for x in w):lows.append(l)
    return highs,lows


def _structure(bars,closes,atr):
    ph,pl=_pivots(bars); ph,pl=ph[-6:],pl[-6:]
    hh=sum(ph[i]>ph[i-1] for i in range(1,len(ph))); lh=sum(ph[i]<ph[i-1] for i in range(1,len(ph)))
    hl=sum(pl[i]>pl[i-1] for i in range(1,len(pl))); ll=sum(pl[i]<pl[i-1] for i in range(1,len(pl)))
    bull=min(hh,hl); bear=min(lh,ll)
    if bull>=2 and bull>bear: state,q="BULLISH",min(1.0,.65+.08*bull)
    elif bear>=2 and bear>bull: state,q="BEARISH",min(1.0,.65+.08*bear)
    elif hh+hl>=2 and hh+hl>lh+ll: state,q="BULLISH",.55
    elif lh+ll>=2 and lh+ll>hh+hl: state,q="BEARISH",.55
    else:
        # When the tape is monotonic, classical pivots do not exist. A professional
        # analyst must not call that "mixed" simply because there are no swing points.
        s10=_signed_efficiency(closes,10); s20=_signed_efficiency(closes,20)
        if s10>0.65 and s20>0.55: state,q="BULLISH",.72
        elif s10<-0.65 and s20<-0.55: state,q="BEARISH",.72
        elif s20>0.35: state,q="BULLISH",.50
        elif s20<-0.35: state,q="BEARISH",.50
        else: state,q="MIXED",.30
    return state,q,{"pivot_highs":ph,"pivot_lows":pl,"higher_highs":hh,"lower_highs":lh,"higher_lows":hl,"lower_lows":ll}


def _volatility(bars):
    ratio=_atr_ratio(bars); ranges=[float(b["high"])-float(b["low"]) for b in bars]
    recent=mean(ranges[-6:]); baseline=mean(ranges[-26:-6]) if len(ranges)>=26 else median(ranges[:-6] or ranges)
    rr=recent/max(baseline,1e-12); compression=ratio<.78 and rr<.82; expansion=ratio>1.18 or rr>=1.35
    return ("EXPANDING" if expansion else "CONTRACTING" if compression else "NORMAL"),compression,expansion,rr,{"atr_short_long_ratio":ratio,"recent_vs_baseline_range":rr}


def _confidence(state,sq,persistence,eff,consensus,ema_ok,conflicts,data_quality):
    base={"TREND_UP":.62,"TREND_DOWN":.62,"RANGE":.58,"COMPRESSION":.60,"EXPANSION":.54,"TRANSITION":.58,"UNCLEAR":.25}.get(state,.25)
    quality=.24*sq+.24*persistence+.20*min(1,eff/.70)+.12*(consensus/3)+.08*float(ema_ok)+.12*data_quality
    return round(max(0,min(.99,base+.34*quality-min(.32,.08*conflicts))),3)


def _incomplete(reason,conflicts=None):
    conflicts=conflicts or []
    return {"question":PROFESSIONAL_QUESTION,"market_state":"UNCLEAR","directional_pressure":"NEUTRAL","trend_state":"NONE","volatility_state":"UNKNOWN","structure_state":"UNCLEAR","compression":"UNKNOWN","expansion":"UNKNOWN","transition":"UNKNOWN","confidence":0.0,"evidence":[reason],"conflicts":conflicts,"reasoning_trace":[f"QUESTION -> {PROFESSIONAL_QUESTION}",f"DATA_QUALITY -> {reason}"],"professional_reasoning":{"question":PROFESSIONAL_QUESTION,"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":"UNCLEAR","market_state":"UNCLEAR","direction":"NEUTRAL","directional_pressure":"NEUTRAL","confidence":0.0,"trend_persistence":0.0,"next_question":"IS_MARKET_TOO_BALANCED_TO_CLASSIFY?","evidence_hierarchy":EVIDENCE_HIERARCHY,"independent_evidence":{},"directional_consensus":{"ema":"FLAT","short":"FLAT","medium":"FLAT","long":"FLAT","confirmed":False},"conflict_detected":bool(conflicts),"conflict_count":len(conflicts)},"analysis_status":"INCOMPLETE","reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY"}


def analyze_e1(bars):
    """Independent professional market-state analyst. Raw OHLC only; no peer/sub-engine input."""
    valid,data_problems=_clean_bars(bars)
    if len(valid)<60:return _incomplete("valid_candles_below_minimum",data_problems[:6])
    highs=[float(b["high"]) for b in valid]; lows=[float(b["low"]) for b in valid]; closes=[float(b["close"]) for b in valid]
    atr=_atr(valid)
    if atr<=0:return _incomplete("atr_invalid",["atr_invalid"])
    e20s,e50s=_ema_series(closes,20),_ema_series(closes,50); e20,e50=e20s[-1],e50s[-1]
    ema_rel="UP" if e20>e50 else "DOWN" if e20<e50 else "FLAT"; e20slope=_slope_atr(e20s,atr,5); e50slope=_slope_atr(e50s,atr,5); gap=(e20-e50)/atr
    structure,sq,sd=_structure(valid,closes,atr); structure_dir="UP" if structure=="BULLISH" else "DOWN" if structure=="BEARISH" else "FLAT"
    vol,compression,expansion,rr,vd=_volatility(valid)
    short_slope,medium_slope,long_slope=_slope_atr(closes,atr,5),_slope_atr(closes,atr,10),_slope_atr(closes,atr,20)
    short_dir,medium_dir,long_dir=_direction(short_slope,.15),_direction(medium_slope,.20),_direction(long_slope,.30); dirs=[short_dir,medium_dir,long_dir]; up,down=dirs.count("UP"),dirs.count("DOWN")
    if up>=2 and up>down:pressure="UP"
    elif down>=2 and down>up:pressure="DOWN"
    elif structure_dir in {"UP","DOWN"}:pressure=structure_dir
    else:pressure="NEUTRAL"
    persistence=0.0; pw={}
    if pressure in {"UP","DOWN"}:
        aligned=0
        for name,lb,t in (("short",5,.20),("medium",10,.30),("long",20,.45)):
            v=_slope_atr(closes,atr,lb); pw[name]=round(v,4); aligned+=int(v>=t if pressure=="UP" else v<=-t)
        persistence=aligned/3
    eff10,eff20=_efficiency(closes,10),_efficiency(closes,20); se10,se20=_signed_efficiency(closes,10),_signed_efficiency(closes,20)
    ema_ok=pressure in {"UP","DOWN"} and ema_rel==pressure and ((pressure=="UP" and e20slope>=-.05 and e50slope>=-.10) or (pressure=="DOWN" and e20slope<=.05 and e50slope<=.10))
    ema_conflict=pressure in {"UP","DOWN"} and ema_rel in {"UP","DOWN"} and ema_rel!=pressure
    structural_conflict=pressure in {"UP","DOWN"} and structure_dir in {"UP","DOWN"} and structure_dir!=pressure
    horizon_conflict=short_dir in {"UP","DOWN"} and long_dir in {"UP","DOWN"} and short_dir!=long_dir
    prior_high,prior_low=max(highs[-21:-1]),min(lows[-21:-1]); sweep_high=highs[-1]>prior_high and closes[-1]<prior_high; sweep_low=lows[-1]<prior_low and closes[-1]>prior_low
    conflicts=[]
    if data_problems:conflicts.append("DATA_QUALITY_ANOMALIES")
    if structural_conflict:conflicts.append("directional_structure_conflict")
    if ema_conflict:conflicts.append("EMA_VS_PRICE_PRESSURE")
    if horizon_conflict:conflicts.append("SHORT_VS_LONG_HORIZON")
    if sweep_high or sweep_low:conflicts.append("LIQUIDITY_SWEEP_OR_FAILED_BREAK")
    if pressure=="NEUTRAL":conflicts.append("DIRECTIONAL_PRESSURE_BALANCED")
    transition_active=structural_conflict or (horizon_conflict and persistence<1.0) or ((sweep_high or sweep_low) and persistence<2/3)
    strong_structure=structure_dir==pressure and sq>=.50
    consensus_confirmed=pressure in {"UP","DOWN"} and up+down==3 and ((up==3 and pressure=="UP") or (down==3 and pressure=="DOWN")) and ema_rel==pressure
    trend_confirmed=pressure in {"UP","DOWN"} and strong_structure and persistence>=2/3 and eff20>=.25 and abs(gap)>=.12 and ema_ok and not transition_active
    if compression and eff20<.45: state,final_pressure,why="COMPRESSION","NEUTRAL","volatility_compression_dominates_direction"
    elif transition_active: state,final_pressure,why="TRANSITION",pressure,"material_structure_horizon_or_liquidity_change"
    elif trend_confirmed: state,final_pressure,why=("TREND_UP" if pressure=="UP" else "TREND_DOWN"),pressure,"structure_price_pressure_persistence_ema_aligned"
    elif expansion: state,final_pressure,why="EXPANSION",pressure,"volatility_expanding_without_full_trend_confirmation"
    elif pressure=="NEUTRAL" and eff20<.35: state,final_pressure,why="RANGE","NEUTRAL","directional_efficiency_is_low"
    elif pressure in {"UP","DOWN"} and strong_structure and persistence>=1/3 and not ema_conflict: state,final_pressure,why=("TREND_UP" if pressure=="UP" else "TREND_DOWN"),pressure,"directional_state_present_with_moderate_confirmation"
    else: state,final_pressure,why="UNCLEAR",pressure,"evidence_not_coherent_enough_for_named_regime"
    transition="PRESENT" if state=="TRANSITION" else "ABSENT"; trend_state="UP" if state=="TREND_UP" else "DOWN" if state=="TREND_DOWN" else "NONE"; data_quality=max(0,1-min(1,len(data_problems)/max(1,len(valid))))
    confidence=_confidence(state,sq,persistence,eff20,max(up,down),ema_ok,len(conflicts),data_quality)
    direction_word="bullish" if final_pressure=="UP" else "bearish" if final_pressure=="DOWN" else "neutral"
    thesis=(f"Market is {state}: structure, multi-horizon price behaviour and persistence support {direction_word}; EMA is confirmation, not the primary cause." if state in {"TREND_UP","TREND_DOWN"} else f"Market is transitioning with {direction_word} pressure; conflicting or changing evidence prevents a clean trend label." if state=="TRANSITION" else "Market is rotational/ranging; directional efficiency is too low for a persistent directional state." if state=="RANGE" else "Market is compressed; volatility contraction dominates and directional commitment is insufficient." if state=="COMPRESSION" else f"Market is expanding with {direction_word} pressure, but trend confirmation is incomplete." if state=="EXPANSION" else "Market evidence is mixed; E1 withholds a stronger regime label rather than forcing a trend.")
    independent={"structure":structure,"structure_quality":round(sq,3),"ema_relationship":ema_rel,"ema_gap_atr":round(gap,4),"ema20_slope_atr":round(e20slope,4),"ema50_slope_atr":round(e50slope,4),"price_short_slope_atr":round(short_slope,4),"price_medium_slope_atr":round(medium_slope,4),"price_long_slope_atr":round(long_slope,4),"price_efficiency_10":round(eff10,4),"price_efficiency_20":round(eff20,4),"signed_efficiency_10":round(se10,4),"signed_efficiency_20":round(se20,4),"volatility":vol,"atr_short_long_ratio":round(vd["atr_short_long_ratio"],4),"recent_vs_baseline_range":round(rr,4),"persistence":round(persistence,4),"liquidity_sweep_high":sweep_high,"liquidity_sweep_low":sweep_low}
    consensus={"ema":ema_rel,"short":short_dir,"medium":medium_dir,"long":long_dir,"pressure":final_pressure,"confirmed":consensus_confirmed}
    evidence=[f"ema20_vs_ema50={ema_rel}",f"ema_gap_atr={gap:.3f}",f"ema20_slope_atr={e20slope:.3f}",f"ema50_slope_atr={e50slope:.3f}",f"price_slope_atr={short_slope:.3f}",f"price_medium_slope_atr={medium_slope:.3f}",f"price_long_slope_atr={long_slope:.3f}",f"structure={structure}",f"structure_quality={sq:.3f}",f"directional_pressure={final_pressure}",f"price_consensus={max(up,down)}/3",f"trend_persistence={persistence:.3f}",f"price_efficiency_10={eff10:.3f}",f"price_efficiency_20={eff20:.3f}",f"signed_efficiency_10={se10:.3f}",f"signed_efficiency_20={se20:.3f}",f"recent_vs_baseline_range={rr:.3f}",f"atr_short_long_ratio={vd['atr_short_long_ratio']:.3f}",f"ema_confirmed={ema_ok}",f"ema_conflict={ema_conflict}",f"structure_conflict={structural_conflict}",f"horizon_conflict={horizon_conflict}",f"sweep_high={sweep_high}",f"sweep_low={sweep_low}"]
    trace=[f"QUESTION -> {PROFESSIONAL_QUESTION}",f"DATA_QUALITY -> valid_candles={len(valid)} problems={len(data_problems)}",f"VOLATILITY -> {vol} compression={compression} expansion={expansion}",f"STRUCTURE -> {structure} quality={sq:.2f}",f"PRESSURE -> {final_pressure} short={short_dir} medium={medium_dir} long={long_dir}",f"PERSISTENCE -> {persistence:.2f} windows={pw}",f"STATE -> {state} because={why}",f"TRANSITION -> {transition} conflicts={','.join(conflicts) if conflicts else 'NONE'}",f"THESIS -> {thesis}"]
    return {"question":PROFESSIONAL_QUESTION,"market_state":state,"directional_pressure":final_pressure,"trend_state":trend_state,"volatility_state":vol,"structure_state":structure,"structure_quality":round(sq,3),"compression":"PRESENT" if compression else "ABSENT","expansion":"PRESENT" if expansion else "ABSENT","transition":transition,"confidence":confidence,"evidence":evidence,"conflicts":conflicts,"reasoning_trace":trace,"professional_reasoning":{"question":PROFESSIONAL_QUESTION,"task":"DESCRIBE_MARKET_STATE_ONLY","primary_state":state,"market_state":state,"direction":final_pressure,"directional_pressure":final_pressure,"confidence":confidence,"trend_persistence":persistence,"next_question":"IS_THIS_STATE_STABLE_OR_TRANSITIONING?" if state in {"TREND_UP","TREND_DOWN","TRANSITION"} else "IS_DIRECTIONAL_PRESSURE_STRONG_ENOUGH_TO_MATTER?" if final_pressure in {"UP","DOWN"} else "IS_MARKET_TOO_BALANCED_TO_CLASSIFY?","evidence_hierarchy":EVIDENCE_HIERARCHY,"independent_evidence":independent,"directional_consensus":consensus,"structure_detail":sd,"volatility_detail":vd,"persistence_windows":pw,"ema":{"relationship":ema_rel,"gap_atr":round(gap,4),"confirmed":ema_ok,"conflict":ema_conflict},"conflict_detected":bool(conflicts),"conflict_count":len(conflicts),"trend_confirmed":trend_confirmed,"classification_reason":why,"data_quality":round(data_quality,3),"thesis":thesis},"analysis_status":"COMPLETE","reasoning_role":"MARKET_STATE_ANALYST","trade_decision_authority":False,"decision_authority":"E9_ONLY"}
