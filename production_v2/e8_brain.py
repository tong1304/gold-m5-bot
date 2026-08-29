from __future__ import annotations

from statistics import mean, median
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V16"
VERSION = "16.0"

MIN_BARS = 30
ATR_PERIOD = 14
MIN_RR = 1.50
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 3.50
RISK_ATR_BUFFER = 0.20
FALLBACK_STOP_ATR = 1.20
STRUCTURE_LOOKBACK = 20
MAE_LOOKBACK = 12
MIN_SPACE_ATR = 0.75
MIN_TARGET_CLEARANCE_ATR = 0.10
MAX_TARGET_EXTENSION_ATR = 3.50
TARGET_QUALITY_MIN = 70.0
SECONDARY_TARGET_QUALITY = 62.0
MIN_SURVIVAL_MARGIN_ATR = 0.15
MAX_EXECUTION_COST_ATR = 0.15
MIN_ECONOMIC_EDGE = 0.10
SPACE_CONFLICT_ATR = 0.75
TP1_FRACTION = 0.50
MIN_PROBABILITY = 0.50
MIN_PROBABILITY_QUALITY = 60.0


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _evidence(e: EngineResult | None) -> dict[str, Any]:
    return dict(e.output or {}) if e else {}


def _first_num(m: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        try:
            x = float(m[key])
            if x == x and x > 0:
                return x
        except (KeyError, TypeError, ValueError):
            pass
    return None


def _direction(e6: dict[str, Any]) -> str:
    for raw in (e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction")):
        x = _text(raw)
        if x in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}: return "BUY"
        if x in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}: return "SELL"
    parts = _text(e6.get("finding")).split()
    if parts and parts[0] in {"BUY", "BULLISH", "UP", "LONG"}: return "BUY"
    if parts and parts[0] in {"SELL", "BEARISH", "DOWN", "SHORT"}: return "SELL"
    return "NEUTRAL"


def _setup(e6: dict[str, Any]) -> str:
    for key in ("setup", "setup_family", "setup_type", "thesis_setup"):
        if e6.get(key) not in (None, ""): return str(e6[key])
    parts = str(e6.get("finding") or "").split()
    return parts[1] if len(parts) >= 2 and _text(parts[0]) in {"BUY", "SELL"} else "UNKNOWN"


def _confirmation(e7: dict[str, Any]) -> tuple[str, list[str]]:
    trace=[]
    for key in ("confirmation", "confirmation_state", "trigger_state", "proof_state"):
        if e7.get(key) not in (None, ""): trace.append(_text(e7[key]))
    proof=e7.get("proof_gates")
    if isinstance(proof,dict):
        for key in ("confirmation","closed_candle_confirmation","follow_through"):
            v=proof.get(key)
            if v is True or v in {"PASS","CONFIRMED","PROVEN","VALID","VALIDATED"}: trace.append("CONFIRMED")
            elif v is False or v in {"FAIL","PENDING","UNAVAILABLE","NOT_PROVEN"}: trace.append("NOT_CONFIRMED")
    reasons=[_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    if any(x in {"PROOF_GATES_INCOMPLETE","VALID_CLOSED_CANDLE_TRIGGER_MISSING","TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION","LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for x in reasons): return "NOT_CONFIRMED",trace+reasons
    if any(x in {"CONFIRMATION_PROVEN","CAUSAL_FOLLOW_THROUGH_PROVEN"} for x in reasons): return "CONFIRMED",trace+reasons
    for key in ("confirmed","confirmation_proven","closed_candle_confirmed"):
        if key in e7: trace.append("CONFIRMED" if bool(e7[key]) else "NOT_CONFIRMED")
    return ("CONFIRMED" if any(x in {"CONFIRMED","PROVEN","VALIDATED"} for x in trace) else "NOT_CONFIRMED"),trace+reasons


def _atr(bars,period=ATR_PERIOD):
    trs=[]
    for i in range(max(1,len(bars)-period),len(bars)):
        h=_num(bars[i].get("high")); l=_num(bars[i].get("low")); pc=_num(bars[i-1].get("close"))
        if h>0 and l>=0 and pc>0: trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return mean(trs) if trs else 0.0


def _atr_series(bars,period=ATR_PERIOD):
    trs=[]
    for i in range(1,len(bars)):
        h=_num(bars[i].get("high")); l=_num(bars[i].get("low")); pc=_num(bars[i-1].get("close"))
        if h>0 and l>=0 and pc>0: trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return [mean(trs[max(0,i-period+1):i+1]) for i in range(len(trs))]


def _levels(e3,e4,e5,bars):
    prior=bars[-(STRUCTURE_LOOKBACK+1):-1]; highs=[_num(x.get("high")) for x in prior if _num(x.get("high"))>0]; lows=[_num(x.get("low")) for x in prior if _num(x.get("low"))>0]
    return {"protected_high":_first_num(e3,("protected_high","external_protected_high","internal_protected_high")),"protected_low":_first_num(e3,("protected_low","external_protected_low","internal_protected_low")),"next_resistance":_first_num(e5,("next_resistance","nearest_resistance","resistance")),"next_support":_first_num(e5,("next_support","nearest_support","support")),"liquidity_event_level":_first_num(e4,("event_level","liquidity_level","nearest_liquidity","opposing_liquidity_level")),"structure_high_20":max(highs) if highs else None,"structure_low_20":min(lows) if lows else None}


def _target_candidates(levels,direction,entry,atr,e4):
    raw=([("RESISTANCE",levels.get("next_resistance"),92.0,1),("PROTECTED_HIGH",levels.get("protected_high"),90.0,2),("LIQUIDITY_EVENT",levels.get("liquidity_event_level"),80.0,3),("STRUCTURE_HIGH_20",levels.get("structure_high_20"),70.0,4)] if direction=="BUY" else [("SUPPORT",levels.get("next_support"),92.0,1),("PROTECTED_LOW",levels.get("protected_low"),90.0,2),("LIQUIDITY_EVENT",levels.get("liquidity_event_level"),80.0,3),("STRUCTURE_LOW_20",levels.get("structure_low_20"),70.0,4)] if direction=="SELL" else [])
    out=[]
    for source,level,quality,rank in raw:
        if level is None or not (level>entry if direction=="BUY" else level<entry): continue
        d=abs(level-entry); da=d/max(atr,1e-9); rej=[]
        if da<MIN_TARGET_CLEARANCE_ATR: rej.append("CLEARANCE_TOO_SMALL")
        if da>MAX_TARGET_EXTENSION_ATR: rej.append("EXTENSION_TOO_FAR")
        if source.startswith("STRUCTURE_"): quality=min(quality,SECONDARY_TARGET_QUALITY)
        if source=="LIQUIDITY_EVENT":
            ext=_text(e4.get("liquidity_externality")); state=_text(e4.get("auction_state")); info=_text(e4.get("auction_information"))
            if ext=="EXTERNAL": quality+=5
            elif ext=="INTERNAL": quality-=10
            if state=="PENDING": rej.append("AUCTION_PENDING")
            if info=="LOW_INFORMATION": rej.append("LOW_INFORMATION_LIQUIDITY")
        quality=max(0,min(100,quality)); out.append({"hierarchy_rank":rank,"source":source,"level":level,"distance":d,"distance_atr":da,"quality":quality,"credible":quality>=TARGET_QUALITY_MIN and not rej,"rejection":rej})
    return sorted(out,key=lambda x:(x["hierarchy_rank"],x["distance"]))


def _select_target(levels,direction,entry,atr,e4):
    candidates=_target_candidates(levels,direction,entry,atr,e4); credible=[x for x in candidates if x["credible"]]
    if not credible: return {"source":None,"level":None,"distance":0.0,"distance_atr":0.0,"quality":0.0,"hierarchy_rank":None,"credible":False,"rejection":["NO_CREDIBLE_OPPOSING_BARRIER"],"candidate_trace":candidates,"selection_rule":"HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}
    return {**min(credible,key=lambda x:(x["hierarchy_rank"],x["distance"])),"candidate_trace":candidates,"selection_rule":"HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}


def _space(e5,target,direction):
    key="available_space_atr_long" if direction=="BUY" else "available_space_atr_short"; e5s=_num(e5.get(key)) if e5.get(key) is not None else 0; ts=_num(target.get("distance_atr")) if target.get("credible") else 0; vals=[]
    if e5s>0: vals.append(("E5_LOCATION",e5s))
    if ts>0: vals.append(("TARGET_BARRIER",ts))
    if not vals: return {"state":"UNAVAILABLE","e5_available_space_atr":e5s,"target_barrier_space_atr":ts,"effective_available_space_atr":0,"space_consistency_delta_atr":None,"space_source":"NO_USABLE_SPACE_EVIDENCE","space_ok":False,"space_conflict":False}
    eff=min(v for _,v in vals); delta=abs(e5s-ts) if len(vals)==2 else None; conflict=delta is not None and delta>=SPACE_CONFLICT_ATR; state="CONFLICTED" if conflict else ("CONSTRAINED" if eff<MIN_SPACE_ATR else "USABLE")
    return {"state":state,"e5_available_space_atr":e5s,"target_barrier_space_atr":ts,"effective_available_space_atr":eff,"space_consistency_delta_atr":delta,"space_source":"MIN(E5_LOCATION,TARGET_BARRIER)" if len(vals)==2 else vals[0][0],"space_ok":state=="USABLE","space_conflict":conflict}


def _stop(direction,entry,atr,levels):
    candidates=([("PROTECTED_LOW",levels.get("protected_low"),100.0),("STRUCTURE_LOW_20",levels.get("structure_low_20"),80.0)] if direction=="BUY" else [("PROTECTED_HIGH",levels.get("protected_high"),100.0),("STRUCTURE_HIGH_20",levels.get("structure_high_20"),80.0)] if direction=="SELL" else [])
    candidates=[x for x in candidates if x[1] is not None and ((direction=="BUY" and x[1]<entry) or (direction=="SELL" and x[1]>entry))]
    if not candidates:
        fallback=entry-FALLBACK_STOP_ATR*atr if direction=="BUY" else entry+FALLBACK_STOP_ATR*atr
        return {"source":None,"level":None,"stop":fallback,"basis":"ATR_FALLBACK_LOWER_CONFIDENCE","quality":0.0,"candidate_trace":[],"structural":False}
    source,level,quality=min(candidates,key=lambda x:abs(entry-x[1])); stop=level-RISK_ATR_BUFFER*atr if direction=="BUY" else level+RISK_ATR_BUFFER*atr
    return {"source":source,"level":level,"stop":stop,"basis":"STRUCTURAL_LEVEL_PLUS_ATR_BUFFER","quality":quality,"candidate_trace":candidates,"structural":True}


def _stop_stability(risk,atr,bars):
    series=_atr_series(bars); current=risk/max(atr,1e-9); prior=series[-6:-1] if len(series)>=6 else series[:-1]
    if not prior: return {"state":"UNAVAILABLE","current_stop_atr":current,"ratio_to_prior":None}
    ref=median(prior); normalized=risk/max(ref,1e-9); ratio=current/max(normalized,1e-9)
    return {"state":"STABLE" if .75<=ratio<=1.35 else "UNSTABLE","current_stop_atr":current,"prior_atr_median":ref,"prior_normalized_stop_atr":normalized,"ratio_to_prior":ratio}


def _survival(bars,entry,direction,atr,risk):
    window=bars[-min(len(bars),MAE_LOOKBACK):]
    if not window or atr<=0: return {"state":"UNAVAILABLE","max_adverse_excursion_atr":None,"median_adverse_excursion_atr":None,"p95_adverse_excursion_atr":None,"survival_margin_atr":None,"window_bars":0}
    adverse=[(max(0,entry-_num(b.get("low"))) if direction=="BUY" else max(0,_num(b.get("high"))-entry))/atr for b in window]; adverse.sort(); maximum=max(adverse); med=median(adverse); p95=adverse[min(len(adverse)-1,int((len(adverse)-1)*.95))]; margin=risk/max(atr,1e-9)-p95
    return {"state":"ROBUST" if margin>=MIN_SURVIVAL_MARGIN_ATR else "FRAGILE" if margin>=0 else "NON_SURVIVABLE","max_adverse_excursion_atr":maximum,"median_adverse_excursion_atr":med,"p95_adverse_excursion_atr":p95,"survival_margin_atr":margin,"window_bars":len(window)}


def _execution(snapshot,atr):
    spread=_first_num(snapshot,("spread","spread_price","current_spread")) or 0; slippage=_first_num(snapshot,("slippage","slippage_price","expected_slippage")) or 0; total=max(0,spread+slippage)
    return {"spread":spread,"slippage":slippage,"total_cost":total,"cost_atr":total/atr if atr>0 else float("inf")}


def _volatility(bars,atr):
    series=_atr_series(bars)
    if atr<=0 or len(series)<2: return {"state":"INVALID","last_range_atr":0,"expansion_ratio":0,"atr_stability":"INVALID","atr_drift":0}
    lr=max(0,_num(bars[-1].get("high"))-_num(bars[-1].get("low"))); pr=max(0,_num(bars[-2].get("high"))-_num(bars[-2].get("low"))); recent=mean(series[-5:]) if len(series)>=5 else mean(series); baseline=mean(series[-min(len(series),ATR_PERIOD):]); drift=recent/max(baseline,1e-9); expansion=lr/max(pr,1e-9)
    return {"state":"EXPANSION_EXTREME" if lr/atr>=2.5 else "EXPANSION" if lr/atr>=1.75 or expansion>=2 else "COMPRESSION" if lr/atr<=.6 else "NORMAL","last_range_atr":lr/atr,"expansion_ratio":expansion,"atr_stability":"STABLE" if .65<=drift<=1.5 else "UNSTABLE","atr_drift":drift}


def _probability(*sources):
    keys=("historical_probability","win_probability","success_probability","trade_probability","probability","estimated_probability")
    for source,data in sources:
        for key in keys:
            if key not in data: continue
            raw=_num(data.get(key),-1)
            if not (0<=raw<=100): continue
            p=raw if raw<=1 else raw/100
            sample=_first_num(data,("sample_size","historical_sample","samples","n")); confidence=_num(data.get("probability_confidence",data.get("confidence",0)))
            if 0<confidence<=1: confidence*=100
            quality=50.0
            if sample is not None: quality+=20 if sample>=50 else 10 if sample>=20 else 0
            quality+=min(30,confidence*.30)
            if sample is None: quality=min(quality,70)
            return {"state":"AVAILABLE","value":p,"percent":p*100,"source":f"{source}.{key}","sample_size":sample,"confidence_percent":confidence or None,"quality":quality,"quality_state":"STRONG" if quality>=75 else "ADEQUATE" if quality>=MIN_PROBABILITY_QUALITY else "WEAK"}
    return {"state":"UNAVAILABLE","value":None,"percent":None,"source":None,"sample_size":None,"confidence_percent":None,"quality":0.0,"quality_state":"UNAVAILABLE"}


def _economics(risk,reward,execution_cost,probability):
    if risk<=0 or reward<=0: return {"state":"UNRESOLVED","probability":probability.get("value"),"gross_reward_r":0,"execution_cost_r":0,"effective_reward_r":0,"effective_rr":0,"break_even_probability":1,"probability_edge":None,"expected_value_r":None,"expected_value_price":None,"edge_class":"UNRESOLVED","asymmetry":"INVALID"}
    gross=reward/risk; cost_r=execution_cost/risk; effective=max(0,gross-cost_r); be=1/(1+effective) if effective>0 else 1; p=probability.get("value")
    if p is None: return {"state":"UNQUANTIFIED","probability":None,"gross_reward_r":gross,"execution_cost_r":cost_r,"effective_reward_r":effective,"effective_rr":effective,"break_even_probability":be,"probability_edge":None,"expected_value_r":None,"expected_value_price":None,"edge_class":"PROBABILITY_UNAVAILABLE","asymmetry":"UNQUANTIFIED"}
    ev=p*effective-(1-p); ev_price=p*max(0,reward-execution_cost)-(1-p)*risk; edge=p-be; asym="STRONG" if effective>=2 else "POSITIVE" if effective>=MIN_RR else "WEAK"
    return {"state":"QUANTIFIED","probability":p,"gross_reward_r":gross,"execution_cost_r":cost_r,"effective_reward_r":effective,"effective_rr":effective,"break_even_probability":be,"probability_edge":edge,"expected_value_r":ev,"expected_value_price":ev_price,"edge_class":"POSITIVE_EXPECTANCY" if ev>=MIN_ECONOMIC_EDGE and edge>0 else "MARGINAL_EXPECTANCY" if ev>=0 else "NEGATIVE_EXPECTANCY","asymmetry":asym}


def _sensitivity(entry,stop,target,atr,direction,probability,cost):
    if probability.get("value") is None or atr<=0 or stop is None or target is None: return {"state":"UNAVAILABLE","scenarios":[],"worst_ev_r":None,"fragility":"UNAVAILABLE"}
    p=probability["value"]; scenarios=[]
    for name,shift in (("ENTRY_WORST",.20),("ENTRY_BEST",-.20),("STOP_WORST",.20),("TARGET_WORST",-.20)):
        en=entry; st=stop; tp=target
        if name.startswith("ENTRY"): en=entry+(shift*atr if direction=="BUY" else -shift*atr)
        elif name.startswith("STOP"): st=stop-(shift*atr if direction=="BUY" else -shift*atr)
        else: tp=target-(shift*atr if direction=="BUY" else -shift*atr)
        r=abs(en-st); rew=abs(tp-en); rr=rew/max(r,1e-9); eff=max(0,rr-cost/max(r,1e-9)); ev=p*eff-(1-p); scenarios.append({"scenario":name,"risk_atr":r/atr,"reward_atr":rew/atr,"effective_rr":eff,"expected_value_r":ev})
    worst=min(x["expected_value_r"] for x in scenarios)
    return {"state":"ROBUST" if worst>=0 else "FRAGILE","scenarios":scenarios,"worst_ev_r":worst,"fragility":"ROBUST" if worst>=0 else "ECONOMICS_FRAGILE"}


def _risk_budget(snapshot,risk):
    budget=_first_num(snapshot,("risk_budget","max_risk_price")); pct=_first_num(snapshot,("risk_percent","risk_pct","max_risk_percent")); capital=_first_num(snapshot,("capital","account_equity","equity"))
    if budget is None and pct is not None and capital is not None: budget=capital*pct/100
    if budget is None: return {"state":"UNSPECIFIED","budget":None,"risk_distance":risk,"utilization":None,"position_size":None,"sizing_state":"NOT_COMPUTABLE"}
    if risk<=0: return {"state":"INVALID","budget":budget,"risk_distance":risk,"utilization":None,"position_size":None,"sizing_state":"INVALID_RISK"}
    size=budget/risk
    return {"state":"WITHIN_BUDGET","budget":budget,"risk_distance":risk,"utilization":1.0,"position_size":size,"sizing_state":"COMPUTABLE"}


def analyze_e8(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Independent E8 economics/risk gate. E9 retains final trade authority."""
    bars=list(snapshot.get("bars") or []); e3,e4,e5,e6,e7=(_evidence(upstream.get(k)) for k in ("E3","E4","E5","E6","E7")); base={"architecture":ARCHITECTURE,"version":VERSION,"question":QUESTION,"reasoning_role":"TRADE_ECONOMICS_RISK_ANALYST","decision_authority":"E9","trade_decision_authority":False,"closed_candle_only":True,"lookahead":False}
    if len(bars)<MIN_BARS: return EngineResult("E8",NAME,False,0.0,{**base,"state":"UNRESOLVED","economic_state":"UNRESOLVED","risk_gate":"RISK_NOT_READY","trade_plan":{},"observations":[f"closed_candles={len(bars)} minimum_required={MIN_BARS}"],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"missing_evidence":["SUFFICIENT_CLOSED_CANDLE_DATA"],"gate_matrix":{}},("INSUFFICIENT_DATA",))
    direction=_direction(e6); setup=_setup(e6); confirmation,confirmation_trace=_confirmation(e7); entry=_num(bars[-1].get("close")); atr=_atr(bars); data_valid=entry>0 and atr>0; levels=_levels(e3,e4,e5,bars) if data_valid and direction in {"BUY","SELL"} else {}
    target=_select_target(levels,direction,entry,atr,e4) if levels else {"source":None,"level":None,"distance_atr":0,"quality":0,"hierarchy_rank":None,"credible":False,"rejection":["NO_LEVEL_MODEL"],"candidate_trace":[],"selection_rule":"UNAVAILABLE"}; stop_model=_stop(direction,entry,atr,levels) if levels else {"source":None,"level":None,"stop":None,"quality":0,"candidate_trace":[],"basis":"UNAVAILABLE","structural":False}; stop=stop_model.get("stop"); structural_stop=stop_model.get("level"); structural_breach=bool(structural_stop is not None and ((direction=="BUY" and entry<=structural_stop) or (direction=="SELL" and entry>=structural_stop))); execution=_execution(snapshot,atr); volatility=_volatility(bars,atr); probability=_probability(("E6",e6),("E7",e7),("E5",e5),("E4",e4),("E3",e3),("SNAPSHOT",snapshot))
    risk=abs(entry-stop) if stop is not None else 0; reward=abs(target["level"]-entry) if target.get("level") is not None else 0; stop_atr=risk/max(atr,1e-9) if risk else 0; real_rr=reward/risk if risk>0 and reward>0 else 0; stop_stability=_stop_stability(risk,atr,bars) if risk else {"state":"UNAVAILABLE"}; survival=_survival(bars,entry,direction,atr,risk) if risk else {"state":"UNAVAILABLE"}; space=_space(e5,target,direction) if levels else {"state":"UNAVAILABLE","effective_available_space_atr":0,"space_ok":False,"space_conflict":False}; economics=_economics(risk,reward,execution["total_cost"],probability); sensitivity=_sensitivity(entry,stop,target.get("level"),atr,direction,probability,execution["total_cost"]); risk_budget=_risk_budget(snapshot,risk)
    counter=[]; missing=[]
    if not data_valid: counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY","SELL"}: counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN","NONE","UNRESOLVED"}: missing.append("VALID_SETUP_THESIS")
    if confirmation!="CONFIRMED": missing.append("ENTRY_CONFIRMATION")
    if structural_breach: counter.append("STRUCTURAL_INVALIDATION_BREACHED")
    if not stop_model.get("structural"): counter.append("STRUCTURAL_STOP_UNAVAILABLE")
    if stop_atr<MIN_STOP_ATR: counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
    if stop_atr>MAX_STOP_ATR: counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
    if stop_stability.get("state")=="UNSTABLE": counter.append("STOP_GEOMETRY_UNSTABLE")
    if survival.get("state")=="NON_SURVIVABLE": counter.append("STOP_NOT_SURVIVABLE")
    elif survival.get("state")=="FRAGILE": counter.append("STOP_SURVIVAL_MARGIN_THIN")
    if not target.get("credible"): counter.append("NO_USABLE_STRUCTURAL_TARGET")
    if target.get("distance_atr",0)>MAX_TARGET_EXTENSION_ATR: counter.append("TARGET_TOO_FAR_FOR_M5_EXECUTION")
    if real_rr<MIN_RR: counter.append("REAL_RR_BELOW_MINIMUM")
    if not space["space_ok"]: counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
    if space["space_conflict"]: counter.append("SPACE_EVIDENCE_CONFLICT")
    if volatility["state"]=="EXPANSION_EXTREME": counter.append("VOLATILITY_RISK_HIGH")
    elif volatility["state"]=="EXPANSION": counter.append("VOLATILITY_EXPANSION_RISK")
    if volatility["atr_stability"]=="UNSTABLE": counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"]>MAX_EXECUTION_COST_ATR: counter.append("EXECUTION_COST_TOO_HIGH")
    if probability["state"]!="AVAILABLE": counter.append("PROBABILITY_UNQUANTIFIED")
    elif probability["value"]<MIN_PROBABILITY: counter.append("PROBABILITY_BELOW_MINIMUM")
    if probability.get("quality",0)<MIN_PROBABILITY_QUALITY: counter.append("PROBABILITY_QUALITY_WEAK")
    if economics["edge_class"]=="NEGATIVE_EXPECTANCY": counter.append("NEGATIVE_EXPECTANCY")
    if economics["state"]=="QUANTIFIED" and economics["expected_value_r"]<MIN_ECONOMIC_EDGE: counter.append("ECONOMIC_EDGE_BELOW_MINIMUM")
    if sensitivity["state"]=="FRAGILE": counter.append("ECONOMICS_SENSITIVITY_FRAGILE")
    if risk_budget["state"]=="INVALID": counter.append("RISK_BUDGET_INVALID")
    if risk_budget["state"]=="UNSPECIFIED": missing.append("RISK_BUDGET_OPTIONAL_INPUT_NOT_PROVIDED")
    liq=levels.get("liquidity_event_level") if levels else None; opposing_liquidity=None; opposing_liquidity_r=None
    if liq is not None and target.get("level") is not None and min(entry,target["level"])<liq<max(entry,target["level"]): opposing_liquidity=liq; opposing_liquidity_r=abs(liq-entry)/max(risk,1e-9); counter.append("OPPOSING_LIQUIDITY_ON_TARGET_PATH")
    gate={"DATA_INTEGRITY":data_valid,"DIRECTION":direction in {"BUY","SELL"},"SETUP_THESIS":setup.upper() not in {"UNKNOWN","NONE","UNRESOLVED"},"ENTRY_CONFIRMATION":confirmation=="CONFIRMED","STRUCTURAL_INVALIDATION":not structural_breach,"STRUCTURAL_STOP":bool(stop_model.get("structural")),"STOP_GEOMETRY":MIN_STOP_ATR<=stop_atr<=MAX_STOP_ATR and stop_stability.get("state")=="STABLE","SURVIVAL":survival.get("state")=="ROBUST","TARGET_HIERARCHY":bool(target.get("credible")),"SPACE":space["space_ok"],"RR":real_rr>=MIN_RR,"EXECUTION":volatility["state"] not in {"EXPANSION_EXTREME","INVALID"} and volatility["atr_stability"]=="STABLE" and execution["cost_atr"]<=MAX_EXECUTION_COST_ATR,"PROBABILITY":probability["state"]=="AVAILABLE" and probability.get("value",0)>=MIN_PROBABILITY and probability.get("quality",0)>=MIN_PROBABILITY_QUALITY,"EXPECTED_VALUE":economics["state"]=="QUANTIFIED" and _num(economics.get("expected_value_r"),-999)>=MIN_ECONOMIC_EDGE,"ECONOMIC_EDGE":economics["edge_class"]=="POSITIVE_EXPECTANCY","SENSITIVITY":sensitivity["state"]=="ROBUST","RISK_BUDGET":risk_budget["state"] in {"WITHIN_BUDGET","UNSPECIFIED"}}
    ready=all(gate.values()); lifecycle={f"{i:02d}_{name}":"PASS" if gate[name] else "FAIL" for i,name in enumerate(gate,1)}; lifecycle[f"{len(gate)+1:02d}_FINAL_RISK_GATE"]="RISK_READY" if ready else "RISK_NOT_READY"; state="ATTRACTIVE" if ready else "UNRESOLVED"; score=100.0 if ready else 40.0; counter=list(dict.fromkeys(counter)); missing=list(dict.fromkeys(missing)); effective_rr=economics.get("effective_rr",0); be=economics.get("break_even_probability"); p=probability.get("percent"); ev_r=economics.get("expected_value_r"); ev_price=economics.get("expected_value_price")
    observations=[f"direction={direction}",f"setup={setup}",f"confirmation={confirmation}",f"entry={entry:.6f}",f"atr={atr:.6f}",f"risk_distance_atr={stop_atr:.3f}",f"survival_state={survival.get('state')}",f"target={target.get('level') if target.get('level') is not None else 'NONE'}",f"effective_space_atr={space.get('effective_available_space_atr',0):.3f}",f"real_rr={real_rr:.3f}",f"effective_rr={effective_rr:.3f}",f"break_even_probability={be*100:.2f}%" if be is not None else "break_even_probability=UNAVAILABLE",f"probability={p:.2f}%" if p is not None else "probability=UNAVAILABLE",f"probability_quality={probability.get('quality',0):.1f}",f"expected_value_r={ev_r if ev_r is not None else 'UNAVAILABLE'}",f"economic_edge={economics.get('edge_class')}",f"asymmetry={economics.get('asymmetry')}",f"sensitivity={sensitivity.get('state')}",f"worst_sensitivity_ev_r={sensitivity.get('worst_ev_r')}",f"risk_budget_state={risk_budget.get('state')}",f"position_size={risk_budget.get('position_size')}",f"risk_lifecycle={lifecycle[f'{len(gate)+1:02d}_FINAL_RISK_GATE']}"]
    if counter: observations.append("vetoes="+",".join(counter))
    if missing: observations.append("missing="+",".join(missing))
    trade_plan={"valid":bool(data_valid and direction in {"BUY","SELL"}),"entry":entry,"direction":direction,"stop_loss":stop,"structural_stop":structural_stop,"invalidation_basis":stop_model.get("basis"),"invalidation_source":stop_model.get("source"),"stop_validity":"STRUCTURAL" if stop_model.get("structural") else "FALLBACK_LOWER_CONFIDENCE","stop_quality":stop_model.get("quality",0),"target":target.get("level"),"target_source":target.get("source"),"target_quality":target.get("quality",0),"target_hierarchy_rank":target.get("hierarchy_rank"),"target_distance_atr":target.get("distance_atr",0),"target_candidate_trace":target.get("candidate_trace",[]),"target_rejection":target.get("rejection",[]),"risk_distance":risk,"risk_distance_atr":stop_atr,"reward_distance":reward,"reward_distance_atr":reward/max(atr,1e-9),"real_rr":real_rr,"effective_rr":effective_rr,"break_even_probability":be,"probability":probability.get("value"),"probability_percent":probability.get("percent"),"probability_source":probability.get("source"),"probability_quality":probability.get("quality"),"probability_sample_size":probability.get("sample_size"),"expected_value_r":ev_r,"expected_value_price":ev_price,"probability_edge":economics.get("probability_edge"),"economic_edge":economics.get("edge_class"),"asymmetry":economics.get("asymmetry"),"sensitivity":sensitivity,"risk_budget":risk_budget,"max_adverse_excursion_atr":survival.get("max_adverse_excursion_atr"),"p95_adverse_excursion_atr":survival.get("p95_adverse_excursion_atr"),"survival_margin_atr":survival.get("survival_margin_atr"),"survival_state":survival.get("state"),"opposing_liquidity":opposing_liquidity,"opposing_liquidity_r":opposing_liquidity_r}
    output={**base,"state":state,"economic_state":state,"risk_gate":lifecycle[f"{len(gate)+1:02d}_FINAL_RISK_GATE"],"direction":direction,"setup":setup,"confirmation":confirmation,"confirmation_trace":confirmation_trace,"trade_plan":trade_plan,"structural_evidence":{**levels,"structural_breach":structural_breach,"stop_model":stop_model},"dynamic_target":target,"location_evidence":space,"risk_model":{"atr":atr,"atr_period":ATR_PERIOD,"volatility":volatility,"execution":execution,"stop_stability":stop_stability,"survival":survival},"probability_evidence":probability,"trade_economics":economics,"sensitivity_analysis":sensitivity,"risk_budget":risk_budget,"gate_matrix":gate,"lifecycle":lifecycle,"counter_evidence":counter,"missing_evidence":missing,"observations":observations,"professional_reasoning":{"causal_chain":f"ENTRY={entry:.6f}->STRUCTURAL_STOP={structural_stop if structural_stop is not None else 'NONE'}->STOP={stop if stop is not None else 'NONE'}->TARGET={target.get('level') if target.get('level') is not None else 'NONE'}->REAL_RR={real_rr:.3f}->EFFECTIVE_RR={effective_rr:.3f}->P={p if p is not None else 'NA'}->EV_R={ev_r if ev_r is not None else 'NA'}->SENSITIVITY={sensitivity.get('state')}->RISK_BUDGET={risk_budget.get('state')}","structural_stop_reasoning":f"source={stop_model.get('source') or 'NONE'};quality={stop_model.get('quality',0):.1f};structural={stop_model.get('structural',False)};fallback_never_counts_as_ready=True","target_hierarchy_reasoning":f"selected={target.get('source') or 'NONE'};rank={target.get('hierarchy_rank')};selection_rule={target.get('selection_rule')};candidates={target.get('candidate_trace',[])}","survival_reasoning":f"state={survival.get('state')};max_AE={survival.get('max_adverse_excursion_atr')};p95_AE={survival.get('p95_adverse_excursion_atr')};margin={survival.get('survival_margin_atr')}","economic_reasoning":f"P={p if p is not None else 'UNAVAILABLE'}%;Effective_RR={effective_rr};BE_P={be};ProbabilityEdge={economics.get('probability_edge')};EV_R={ev_r};EV_price={ev_price};Asymmetry={economics.get('asymmetry')};SensitivityWorstEV={sensitivity.get('worst_ev_r')}","risk_budget_reasoning":f"state={risk_budget.get('state')};budget={risk_budget.get('budget')};risk_distance={risk};position_size={risk_budget.get('position_size')}","risk_veto":"PASS" if ready else "VETO: "+";".join(counter+missing+["ECONOMICS_NOT_READY"])},"decision_path":"E8 validates economics, risk, survivability, probability quality and robustness only; E9 retains final trade authority."}
    return EngineResult("E8",NAME,ready,score,output,tuple(counter+missing+([] if ready else ["ECONOMICS_NOT_READY"])))
