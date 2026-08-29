from __future__ import annotations

from statistics import mean, median
from typing import Any

from .contracts import EngineResult

NAME = "Trade Economics & Risk Brain"
QUESTION = "Is the proposed trade economically attractive and structurally survivable?"
ARCHITECTURE = "E8_PROFESSIONAL_TRADE_ECONOMICS_RISK_BRAIN_V14"
VERSION = "14.0"
MIN_BARS=30; MIN_RR=1.50; ATR_PERIOD=14; RISK_ATR_BUFFER=0.20; FALLBACK_STOP_ATR=1.20
STRUCTURE_LOOKBACK=20; MAE_LOOKBACK=12; MIN_STOP_ATR=0.50; MAX_STOP_ATR=3.50
MIN_SPACE_ATR=0.75; MIN_TARGET_CLEARANCE_ATR=0.10; MAX_TARGET_EXTENSION_ATR=3.50
TP1_FRACTION=0.50; MAX_LIQUIDITY_RISK_R=1.00; MAX_EXECUTION_COST_ATR=0.15
MAX_LAST_RANGE_ATR=2.50; MODERATE_EXPANSION_ATR=1.75; SPACE_CONFLICT_ATR=0.75
TARGET_QUALITY_MIN=70.0; SECONDARY_TARGET_QUALITY=62.0; STOP_STABILITY_MIN_RATIO=0.75
STOP_STABILITY_MAX_RATIO=1.35; MIN_SURVIVAL_MARGIN_ATR=0.15; MIN_ECONOMIC_EDGE=0.10


def _num(v: Any, d: float=0.0) -> float:
    try:
        x=float(v); return x if x==x else d
    except (TypeError,ValueError): return d

def _text(v: Any)->str: return str(v or "").upper().strip()
def _evidence(e: EngineResult|None)->dict[str,Any]: return dict(e.output or {}) if e else {}

def _first_num(m:dict[str,Any], keys:tuple[str,...])->float|None:
    for k in keys:
        try:
            x=float(m[k]);
            if x==x and x>0:return x
        except (KeyError,TypeError,ValueError):pass
    return None

def _direction(e6:dict[str,Any])->str:
    for raw in (e6.get("direction"),e6.get("direction_thesis"),e6.get("thesis_direction")):
        x=_text(raw)
        if x in {"BUY","BULLISH","UP","LONG","BUYERS","TREND_UP"}:return "BUY"
        if x in {"SELL","BEARISH","DOWN","SHORT","SELLERS","TREND_DOWN"}:return "SELL"
    p=_text(e6.get("finding")).split()
    if p and p[0] in {"BUY","BULLISH","UP","LONG"}:return "BUY"
    if p and p[0] in {"SELL","BEARISH","DOWN","SHORT"}:return "SELL"
    return "NEUTRAL"

def _setup(e6:dict[str,Any])->str:
    for k in ("setup","setup_family","setup_type","thesis_setup"):
        if e6.get(k) not in (None,""):return str(e6[k])
    p=str(e6.get("finding") or "").split()
    return p[1] if len(p)>=2 and _text(p[0]) in {"BUY","SELL"} else "UNKNOWN"

def _confirmation(e7:dict[str,Any])->tuple[str,list[str]]:
    obs=[]
    for k in ("confirmation","confirmation_state","trigger_state","proof_state"):
        if e7.get(k) not in (None,""):obs.append(_text(e7[k]))
    proof=e7.get("proof_gates")
    if isinstance(proof,dict):
        for k in ("confirmation","closed_candle_confirmation","follow_through"):
            v=proof.get(k)
            if v is True or v in {"PASS","CONFIRMED","PROVEN","VALID","VALIDATED"}:obs.append("CONFIRMED")
            elif v is False or v in {"FAIL","PENDING","UNAVAILABLE","NOT_PROVEN"}:obs.append("NOT_CONFIRMED")
    for k in ("confirmed","confirmation_proven","closed_candle_confirmed"):
        if k in e7:obs.append("CONFIRMED" if bool(e7[k]) else "NOT_CONFIRMED")
    rs=[_text(x) for x in (e7.get("reason_codes") or e7.get("reasons") or [])]
    if any(x in {"PROOF_GATES_INCOMPLETE","VALID_CLOSED_CANDLE_TRIGGER_MISSING","TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION","LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for x in rs):return "NOT_CONFIRMED",obs+rs
    if any(x in {"CONFIRMATION_PROVEN","CAUSAL_FOLLOW_THROUGH_PROVEN"} for x in rs):return "CONFIRMED",obs+rs
    return ("CONFIRMED" if any(x in {"CONFIRMED","PROVEN","VALIDATED"} for x in obs) else "NOT_CONFIRMED"),obs+rs

def _atr(bars:list[dict[str,Any]],period:int=ATR_PERIOD)->float:
    tr=[]
    for i in range(max(1,len(bars)-period),len(bars)):
        h,l,pc=_num(bars[i].get("high")),_num(bars[i].get("low")),_num(bars[i-1].get("close"))
        if h>0 and l>=0 and pc>0:tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return mean(tr) if tr else 0.0

def _atr_series(bars:list[dict[str,Any]],period:int=ATR_PERIOD)->list[float]:
    tr=[]
    for i in range(1,len(bars)):
        h,l,pc=_num(bars[i].get("high")),_num(bars[i].get("low")),_num(bars[i-1].get("close"))
        if h>0 and l>=0 and pc>0:tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return [mean(tr[max(0,i-period+1):i+1]) for i in range(len(tr))]

def _levels(e3,e4,e5,bars):
    r=bars[-(STRUCTURE_LOOKBACK+1):-1]; hs=[_num(x.get("high")) for x in r if _num(x.get("high"))>0]; ls=[_num(x.get("low")) for x in r if _num(x.get("low"))>0]
    return {"protected_high":_first_num(e3,("protected_high","external_protected_high","internal_protected_high")),"protected_low":_first_num(e3,("protected_low","external_protected_low","internal_protected_low")),"next_resistance":_first_num(e5,("next_resistance","nearest_resistance","resistance")),"next_support":_first_num(e5,("next_support","nearest_support","support")),"liquidity_event_level":_first_num(e4,("event_level","liquidity_level","nearest_liquidity","opposing_liquidity_level")),"structure_high_20":max(hs) if hs else None,"structure_low_20":min(ls) if ls else None}

def _targets(levels,direction,entry,atr,e4):
    raw=[("RESISTANCE",levels.get("next_resistance"),92,1),("PROTECTED_HIGH",levels.get("protected_high"),90,2),("LIQUIDITY_EVENT",levels.get("liquidity_event_level"),80,3),("STRUCTURE_HIGH_20",levels.get("structure_high_20"),70,4)] if direction=="BUY" else [("SUPPORT",levels.get("next_support"),92,1),("PROTECTED_LOW",levels.get("protected_low"),90,2),("LIQUIDITY_EVENT",levels.get("liquidity_event_level"),80,3),("STRUCTURE_LOW_20",levels.get("structure_low_20"),70,4)] if direction=="SELL" else []
    out=[]
    for src,lev,q,rank in raw:
        if lev is None or (direction=="BUY" and lev<=entry) or (direction=="SELL" and lev>=entry):continue
        dist=abs(lev-entry); da=dist/max(atr,1e-9); rej=[]
        if da<MIN_TARGET_CLEARANCE_ATR:rej.append("CLEARANCE_TOO_SMALL")
        if da>MAX_TARGET_EXTENSION_ATR:rej.append("EXTENSION_TOO_FAR")
        if src.startswith("STRUCTURE_"):q=min(q,SECONDARY_TARGET_QUALITY)
        if src=="LIQUIDITY_EVENT":
            ext,state,info=_text(e4.get("liquidity_externality")),_text(e4.get("auction_state")),_text(e4.get("auction_information"))
            if ext=="EXTERNAL":q+=5
            elif ext=="INTERNAL":q-=10
            if state=="PENDING":rej.append("AUCTION_PENDING")
            if info=="LOW_INFORMATION":rej.append("LOW_INFORMATION_LIQUIDITY")
        q=max(0,min(100,q));out.append({"hierarchy_rank":rank,"source":src,"level":lev,"distance":dist,"distance_atr":da,"quality":q,"credible":q>=TARGET_QUALITY_MIN and not rej,"rejection":rej})
    return sorted(out,key=lambda x:(x["hierarchy_rank"],x["distance"]))

def _target(levels,direction,entry,atr,e4):
    c=_targets(levels,direction,entry,atr,e4); good=[x for x in c if x["credible"]]
    if not good:return {"source":None,"level":None,"distance":0.0,"distance_atr":0.0,"quality":0.0,"credible":False,"rejection":["NO_CREDIBLE_OPPOSING_BARRIER"],"candidate_trace":c,"selection_rule":"HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}
    return {**min(good,key=lambda x:(x["hierarchy_rank"],x["distance"])),"candidate_trace":c,"selection_rule":"HIERARCHY_THEN_NEAREST_CREDIBLE_BARRIER"}

def _space(e5,target,direction):
    k="available_space_atr_long" if direction=="BUY" else "available_space_atr_short"; present=e5.get(k) is not None; e=_num(e5.get(k)) if present else 0; t=_num(target.get("distance_atr")) if target.get("credible") else 0; vals=[]
    if present and e>0:vals.append(("E5_LOCATION",e))
    if target.get("credible") and t>0:vals.append(("TARGET_BARRIER",t))
    if not vals:return {"state":"UNAVAILABLE","e5_available_space_atr":e,"target_barrier_space_atr":t,"effective_available_space_atr":0,"space_consistency_delta_atr":None,"space_source":"NO_USABLE_SPACE_EVIDENCE","space_ok":False,"space_conflict":False}
    effective=min(v for _,v in vals);delta=abs(e-t) if len(vals)==2 else None;conflict=delta is not None and delta>=SPACE_CONFLICT_ATR;state="CONFLICTED" if conflict else ("CONSTRAINED" if effective<MIN_SPACE_ATR else "USABLE")
    return {"state":state,"e5_available_space_atr":e,"target_barrier_space_atr":t,"effective_available_space_atr":effective,"space_consistency_delta_atr":delta,"space_source":"MIN(E5_LOCATION,TARGET_BARRIER)" if len(vals)==2 else vals[0][0],"space_ok":state=="USABLE","space_conflict":conflict}

def _volatility(bars,atr):
    s=_atr_series(bars)
    if atr<=0 or len(s)<2:return {"state":"INVALID","last_range_atr":0,"expansion_ratio":0,"atr_stability":"INVALID","atr_drift":0}
    lr=max(0,_num(bars[-1].get("high"))-_num(bars[-1].get("low")));pr=max(0,_num(bars[-2].get("high"))-_num(bars[-2].get("low")));dr=(mean(s[-5:]) if len(s)>=5 else mean(s))/max(mean(s[-min(len(s),ATR_PERIOD):]),1e-9);la=lr/atr;er=lr/max(pr,1e-9)
    state="EXPANSION_EXTREME" if la>=MAX_LAST_RANGE_ATR else "EXPANSION" if la>=MODERATE_EXPANSION_ATR or er>=2 else "COMPRESSION" if la<=.60 else "NORMAL"
    return {"state":state,"last_range_atr":la,"expansion_ratio":er,"atr_stability":"STABLE" if .65<=dr<=1.50 else "UNSTABLE","atr_drift":dr}

def _execution(s,atr):
    sp=_first_num(s,("spread","spread_price","current_spread")) or 0;sl=_first_num(s,("slippage","slippage_price","expected_slippage")) or 0;tot=sp+sl
    return {"spread":sp,"slippage":sl,"total_cost":tot,"cost_atr":tot/atr if atr>0 else float("inf")}

def _liquidity(e4):return {"liquidity_quality":_first_num(e4,("liquidity_quality",)) or 0,"auction_quality":_first_num(e4,("auction_quality",)) or 0,"proximity":_text(e4.get("liquidity_proximity")),"externality":_text(e4.get("liquidity_externality")),"auction_state":_text(e4.get("auction_state")),"information":_text(e4.get("auction_information"))}

def _stop(direction,entry,atr,levels):
    raw=[("PROTECTED_LOW",levels.get("protected_low"),100), ("STRUCTURE_LOW_20",levels.get("structure_low_20"),80)] if direction=="BUY" else [("PROTECTED_HIGH",levels.get("protected_high"),100),("STRUCTURE_HIGH_20",levels.get("structure_high_20"),80)] if direction=="SELL" else []
    c=[x for x in raw if x[1] is not None and ((direction=="BUY" and x[1]<entry) or (direction=="SELL" and x[1]>entry))]
    if not c:return {"source":None,"level":None,"stop":entry+(-FALLBACK_STOP_ATR*atr if direction=="BUY" else FALLBACK_STOP_ATR*atr),"basis":"ATR_FALLBACK_LOWER_CONFIDENCE","quality":0,"candidate_trace":c}
    src,lev,q=min(c,key=lambda x:abs(entry-x[1]));stop=lev+(-RISK_ATR_BUFFER*atr if direction=="BUY" else RISK_ATR_BUFFER*atr)
    return {"source":src,"level":lev,"stop":stop,"basis":"STRUCTURAL_LEVEL_PLUS_ATR_BUFFER","quality":q,"candidate_trace":c}

def _stop_stability(risk,atr,bars):
    s=_atr_series(bars);cur=risk/max(atr,1e-9);prior=s[-6:-1] if len(s)>=6 else s[:-1]
    if not prior:return {"state":"UNAVAILABLE","current_stop_atr":cur,"ratio_to_prior":None}
    ref=median(prior);prior_norm=risk/max(ref,1e-9);ratio=cur/max(prior_norm,1e-9)
    return {"state":"STABLE" if STOP_STABILITY_MIN_RATIO<=ratio<=STOP_STABILITY_MAX_RATIO else "UNSTABLE","current_stop_atr":cur,"prior_atr_median":ref,"prior_normalized_stop_atr":prior_norm,"ratio_to_prior":ratio}

def _survival(bars,entry,direction,atr,risk):
    w=bars[-min(len(bars),MAE_LOOKBACK):]
    if not w or atr<=0:return {"state":"UNAVAILABLE","max_adverse_excursion_atr":0,"median_adverse_excursion_atr":0,"p95_adverse_excursion_atr":0,"survival_margin_atr":0,"window_bars":0}
    a=[max(0,entry-_num(b.get("low")))/atr if direction=="BUY" else max(0,_num(b.get("high"))-entry)/atr for b in w];a.sort();mx=max(a);med=median(a);p95=a[min(len(a)-1,int((len(a)-1)*.95))];margin=risk/max(atr,1e-9)-mx
    return {"state":"ROBUST" if margin>=MIN_SURVIVAL_MARGIN_ATR else "FRAGILE" if margin>=0 else "NON_SURVIVABLE","max_adverse_excursion_atr":mx,"median_adverse_excursion_atr":med,"p95_adverse_excursion_atr":p95,"survival_margin_atr":margin,"window_bars":len(w)}

def _probability(*maps):
    for source,m in maps:
        for k in ("historical_probability","win_probability","success_probability","trade_probability","probability","estimated_probability"):
            if k in m:
                x=_num(m.get(k),-1)
                if 0<=x<=1:return {"state":"AVAILABLE","value":x,"percent":x*100,"source":f"{source}.{k}"}
                if 1<x<=100:return {"state":"AVAILABLE","value":x/100,"percent":x,"source":f"{source}.{k}"}
    return {"state":"UNAVAILABLE","value":None,"percent":None,"source":None}

def _economics(risk,reward,cost,prob):
    gross=reward/max(risk,1e-9) if risk>0 else 0;cost_r=cost/max(risk,1e-9) if risk>0 else 0;net=max(0,gross-cost_r);be=1/(1+net) if net>0 else 1;p=prob.get("value")
    if p is None:return {"state":"STRUCTURAL_ONLY","probability":None,"gross_reward_r":gross,"execution_cost_r":cost_r,"net_reward_r":net,"break_even_probability":be,"probability_edge":None,"expected_value_r":None,"edge":None,"edge_class":"PROBABILITY_UNAVAILABLE"}
    ev=p*net-(1-p);pe=p-be;cls="POSITIVE_EXPECTANCY" if ev>=MIN_ECONOMIC_EDGE and pe>0 else "MARGINAL_EXPECTANCY" if ev>=0 else "NEGATIVE_EXPECTANCY"
    return {"state":"QUANTIFIED","probability":p,"gross_reward_r":gross,"execution_cost_r":cost_r,"net_reward_r":net,"break_even_probability":be,"probability_edge":pe,"expected_value_r":ev,"edge":ev,"edge_class":cls}

def analyze_e8(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    """Independent E8 economics/risk brain. It never fabricates probability and E9 keeps final authority."""
    bars=list(snapshot.get("bars") or []);e3,e4,e5,e6,e7=(_evidence(upstream.get(k)) for k in ("E3","E4","E5","E6","E7"));base={"architecture":ARCHITECTURE,"version":VERSION,"question":QUESTION,"reasoning_role":"TRADE_ECONOMICS_RISK_ANALYST","decision_authority":"E9","trade_decision_authority":False,"closed_candle_only":True,"lookahead":False}
    if len(bars)<MIN_BARS:return EngineResult("E8",NAME,False,0,{**base,"state":"UNRESOLVED","economic_state":"UNRESOLVED","risk_gate":"RISK_NOT_READY","trade_plan":{},"observations":[f"closed_candles={len(bars)} minimum_required={MIN_BARS}"],"supporting_evidence":[],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"missing_evidence":["SUFFICIENT_CLOSED_CANDLE_DATA"],"gate_matrix":{}},("INSUFFICIENT_DATA",))
    direction,setup=_direction(e6),_setup(e6);confirmation,confirmation_trace=_confirmation(e7);entry,atr=_num(bars[-1].get("close")),_atr(bars);vol=_volatility(bars,atr);execution=_execution(snapshot,atr);liq=_liquidity(e4);counter=[];missing=[];data_valid=entry>0 and atr>0
    if not data_valid:counter.append("RISK_DATA_INVALID")
    if direction not in {"BUY","SELL"}:counter.append("NO_VALID_DIRECTION")
    if setup.upper() in {"UNKNOWN","NONE","UNRESOLVED"}:missing.append("VALID_SETUP_THESIS")
    if confirmation!="CONFIRMED":missing.append("ENTRY_CONFIRMATION")
    levels=_levels(e3,e4,e5,bars) if data_valid and direction in {"BUY","SELL"} else {};target=_target(levels,direction,entry,atr,e4) if levels else {"source":None,"level":None,"distance_atr":0,"quality":0,"credible":False,"candidate_trace":[]};sm=_stop(direction,entry,atr,levels) if levels else {"source":None,"level":None,"stop":None,"quality":0,"candidate_trace":[]};stop=sm.get("stop");struct=sm.get("level");source=sm.get("source");breach=bool(struct is not None and ((direction=="BUY" and entry<=struct) or (direction=="SELL" and entry>=struct)))
    if breach:counter.append("STRUCTURAL_INVALIDATION_BREACHED")
    plan={};space={"state":"UNAVAILABLE","effective_available_space_atr":0,"e5_available_space_atr":0,"target_barrier_space_atr":0,"space_consistency_delta_atr":None,"space_source":"UNAVAILABLE","space_ok":False,"space_conflict":False};ss={"state":"UNAVAILABLE","current_stop_atr":0,"ratio_to_prior":None};surv={"state":"UNAVAILABLE","max_adverse_excursion_atr":0,"median_adverse_excursion_atr":0,"p95_adverse_excursion_atr":0,"survival_margin_atr":0};risk=reward=rr=0;tl=None;opposing=False;liq_r=0
    prob=_probability(("E6",e6),("E7",e7),("E5",e5),("E4",e4),("E3",e3),("SNAPSHOT",snapshot))
    if data_valid and direction in {"BUY","SELL"}:
        risk=abs(entry-stop) if stop is not None else 0;ss=_stop_stability(risk,atr,bars);surv=_survival(bars,entry,direction,atr,risk);space=_space(e5,target,direction);tl=target.get("level");reward=abs(tl-entry) if tl is not None else 0;rr=reward/max(risk,1e-9) if tl is not None and risk>0 else 0;ll=levels.get("liquidity_event_level");opposing=ll is not None and tl is not None and min(entry,tl)<ll<max(entry,tl);liq_r=abs(ll-entry)/max(risk,1e-9) if opposing and risk else 0
        if struct is None:counter.append("STRUCTURAL_STOP_UNAVAILABLE")
        if source is None:counter.append("STOP_LOSS_FALLBACK_LOWER_CONFIDENCE")
        if tl is None:missing.append("NO_USABLE_STRUCTURAL_TARGET")
        if risk/max(atr,1e-9)<MIN_STOP_ATR:counter.append("STOP_TOO_TIGHT_FOR_VOLATILITY")
        if risk/max(atr,1e-9)>MAX_STOP_ATR:counter.append("STOP_TOO_WIDE_FOR_ECONOMICS")
        if ss["state"]=="UNSTABLE":counter.append("STOP_GEOMETRY_UNSTABLE")
        if surv["state"]=="NON_SURVIVABLE":counter.append("STOP_NOT_SURVIVABLE")
        elif surv["state"]=="FRAGILE":counter.append("STOP_SURVIVAL_MARGIN_THIN")
        if tl is not None and rr<MIN_RR:counter.append("REAL_RR_BELOW_MINIMUM")
        if not target.get("credible"):counter.append("DYNAMIC_TARGET_NOT_USABLE")
        if target.get("distance_atr",0)>MAX_TARGET_EXTENSION_ATR:counter.append("TARGET_TOO_FAR_FOR_M5_EXECUTION")
        if not space["space_ok"]:counter.append("EFFECTIVE_SPACE_BELOW_MINIMUM")
        if space["space_conflict"]:counter.append("SPACE_EVIDENCE_CONFLICT")
        if opposing:
            counter.append("OPPOSING_LIQUIDITY_ON_TARGET_PATH")
            if liq["externality"]=="EXTERNAL":counter.append("EXTERNAL_LIQUIDITY_PATH_RISK")
            if liq_r<=MAX_LIQUIDITY_RISK_R:counter.append("OPPOSING_LIQUIDITY_PATH_RISK")
            if liq["auction_state"]=="PENDING":counter.append("LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED")
        econ=_economics(risk,reward,execution["total_cost"],prob);eff=econ["net_reward_r"];tp1=entry+reward*TP1_FRACTION if direction=="BUY" else entry-reward*TP1_FRACTION
        plan={"valid":True,"entry":entry,"direction":direction,"stop_loss":stop,"structural_stop":struct,"invalidation_basis":sm.get("basis"),"invalidation_source":source,"stop_validity":"STRUCTURAL" if source else "FALLBACK_LOWER_CONFIDENCE","stop_quality":sm.get("quality",0),"stop_candidate_trace":sm.get("candidate_trace",[]),"take_profit_1":tp1,"take_profit_2":tl,"target_source":target.get("source"),"target_quality":target.get("quality",0),"target_hierarchy_rank":target.get("hierarchy_rank"),"target_distance_atr":target.get("distance_atr",0),"target_candidate_trace":target.get("candidate_trace",[]),"target_rejection":target.get("rejection",[]),"risk_distance":risk,"risk_distance_atr":risk/max(atr,1e-9),"reward_distance":reward,"reward_distance_atr":reward/max(atr,1e-9) if reward else 0,"available_space_atr":space["effective_available_space_atr"],"e5_available_space_atr":space["e5_available_space_atr"],"target_barrier_space_atr":space["target_barrier_space_atr"],"space_consistency_delta_atr":space["space_consistency_delta_atr"],"space_source":space["space_source"],"space_state":space["state"],"real_rr":rr,"effective_rr":eff,"rr_tp1":reward*TP1_FRACTION/max(risk,1e-9) if risk else 0,"rr_tp2":rr,"break_even_probability":econ["break_even_probability"],"probability":prob.get("value"),"probability_percent":prob.get("percent"),"probability_source":prob.get("source"),"expected_value_r":econ.get("expected_value_r"),"economic_edge":econ.get("edge_class"),"probability_edge":econ.get("probability_edge"),"net_reward_r":econ.get("net_reward_r"),"stop_stability":ss["state"],"survival_state":surv["state"],"max_adverse_excursion_atr":surv["max_adverse_excursion_atr"],"median_adverse_excursion_atr":surv["median_adverse_excursion_atr"],"p95_adverse_excursion_atr":surv["p95_adverse_excursion_atr"],"survival_margin_atr":surv["survival_margin_atr"],"structural_breach":breach,"opposing_liquidity":ll if opposing else None,"opposing_liquidity_r":liq_r}
    else:econ=_economics(0,0,execution["total_cost"],prob);counter.append("RISK_MODEL_UNAVAILABLE")
    if vol["state"]=="EXPANSION_EXTREME":counter.append("VOLATILITY_RISK_HIGH")
    elif vol["state"]=="EXPANSION":counter.append("VOLATILITY_EXPANSION_RISK")
    if vol["atr_stability"]=="UNSTABLE":counter.append("ATR_STABILITY_RISK")
    if execution["cost_atr"]>MAX_EXECUTION_COST_ATR:counter.append("EXECUTION_COST_TOO_HIGH")
    if econ["edge_class"]=="NEGATIVE_EXPECTANCY":counter.append("NEGATIVE_EXPECTANCY")
    critical={"RISK_DATA_INVALID","NO_VALID_DIRECTION","STRUCTURAL_INVALIDATION_BREACHED","STRUCTURAL_STOP_UNAVAILABLE","STOP_LOSS_FALLBACK_LOWER_CONFIDENCE","STOP_TOO_TIGHT_FOR_VOLATILITY","STOP_TOO_WIDE_FOR_ECONOMICS","STOP_GEOMETRY_UNSTABLE","STOP_NOT_SURVIVABLE","STOP_SURVIVAL_MARGIN_THIN","NO_USABLE_STRUCTURAL_TARGET","EFFECTIVE_SPACE_BELOW_MINIMUM","REAL_RR_BELOW_MINIMUM","OPPOSING_LIQUIDITY_PATH_RISK","EXTERNAL_LIQUIDITY_PATH_RISK","LIQUIDITY_AUCTION_NOT_TERMINALLY_CONFIRMED","VOLATILITY_RISK_HIGH","ATR_STABILITY_RISK","EXECUTION_COST_TOO_HIGH","DYNAMIC_TARGET_NOT_USABLE","TARGET_TOO_FAR_FOR_M5_EXECUTION","SPACE_EVIDENCE_CONFLICT","NEGATIVE_EXPECTANCY"};counter=list(dict.fromkeys(counter));missing=list(dict.fromkeys(missing))
    gd=data_valid;gdir=direction in {"BUY","SELL"};gsetup=setup.upper() not in {"UNKNOWN","NONE","UNRESOLVED"};gconf=confirmation=="CONFIRMED";ginv=not breach;gstop=bool(plan) and source is not None and MIN_STOP_ATR<=plan.get("risk_distance_atr",99)<=MAX_STOP_ATR and ss["state"]=="STABLE" and surv["state"]=="ROBUST";gtarget=bool(target.get("credible"));gspace=space["space_ok"];grr=bool(plan) and plan.get("effective_rr",0)>=MIN_RR;gexec=vol["state"] not in {"EXPANSION_EXTREME","INVALID"} and vol["atr_stability"]=="STABLE" and execution["cost_atr"]<=MAX_EXECUTION_COST_ATR;gev=econ["state"]!="QUANTIFIED" or _num(econ.get("expected_value_r"),-999)>=MIN_ECONOMIC_EDGE;ready=gtarget and gspace and grr and gstop and ginv and gexec and gev and not any(x in critical for x in counter) and not missing
    lifecycle={"01_DATA_INTEGRITY":"PASS" if gd else "FAIL","02_DIRECTION":"PASS" if gdir else "FAIL","03_SETUP_CONFIRMATION":"PASS" if gsetup and gconf else "FAIL","04_STRUCTURAL_INVALIDATION":"PASS" if ginv else "FAIL","05_STOP_VALIDITY":"PASS" if source else "FAIL","06_STOP_SURVIVABILITY":"PASS" if gstop else "FAIL","07_TARGET_HIERARCHY":"PASS" if gtarget else "FAIL","08_SPACE_VALIDATION":"PASS" if gspace else "FAIL","09_EFFECTIVE_RR":"PASS" if grr else "FAIL","10_EXECUTION_VOLATILITY":"PASS" if gexec else "FAIL","11_EXPECTED_VALUE":"PASS" if gev else "FAIL","12_ECONOMICS":"PASS" if ready else "FAIL","13_RISK_GATE":"RISK_READY" if ready else "RISK_NOT_READY"}
    state="ATTRACTIVE" if ready else "CONDITIONAL" if plan and not any(x in critical for x in counter) and not missing else "UNATTRACTIVE" if plan else "UNRESOLVED";score=95 if ready else 65 if state=="CONDITIONAL" else 30 if state=="UNATTRACTIVE" else 15
    obs=[f"direction={direction}",f"setup={setup}",f"confirmation={confirmation}",f"entry={entry:.6f}",f"atr={atr:.6f}",f"stop={stop:.6f}" if stop is not None else "stop=NONE",f"stop_validity={plan.get('stop_validity','NONE')}",f"risk_distance_atr={plan.get('risk_distance_atr',0):.3f}",f"target={tl:.6f}" if tl is not None else "target=NONE",f"target_source={target.get('source') or 'NONE'}",f"target_hierarchy_rank={target.get('hierarchy_rank','NONE')}",f"effective_space_atr={space.get('effective_available_space_atr',0):.3f}",f"real_rr={rr:.3f}",f"effective_rr={plan.get('effective_rr',0):.3f}",f"break_even_probability={econ.get('break_even_probability',1)*100:.2f}%",f"probability={prob.get('percent') if prob.get('percent') is not None else 'UNAVAILABLE'}",f"expected_value_r={econ.get('expected_value_r') if econ.get('expected_value_r') is not None else 'UNAVAILABLE'}",f"economic_edge={econ.get('edge_class')}",f"max_adverse_excursion_atr={surv.get('max_adverse_excursion_atr',0):.3f}",f"p95_adverse_excursion_atr={surv.get('p95_adverse_excursion_atr',0):.3f}",f"survival_margin_atr={surv.get('survival_margin_atr',0):.3f}",f"survival_state={surv.get('state')}",f"risk_lifecycle={lifecycle['13_RISK_GATE']}",f"economic_lifecycle={state}"]
    if counter:obs.append("vetoes="+",".join(counter))
    if missing:obs.append("missing="+",".join(missing))
    output={**base,"state":state,"economic_state":state,"risk_lifecycle":lifecycle["13_RISK_GATE"],"economic_lifecycle":state,"risk_gate":"RISK_READY" if ready else "RISK_NOT_READY","direction":direction,"setup":setup,"confirmation":confirmation,"confirmation_trace":confirmation_trace,"trade_plan":plan,"risk_model":{"atr":atr,"atr_period":ATR_PERIOD,"volatility_state":vol["state"],"last_range_atr":vol["last_range_atr"],"expansion_ratio":vol["expansion_ratio"],"atr_stability":vol["atr_stability"],"atr_drift":vol["atr_drift"],"stop_stability":ss,"survival":surv,"execution_cost_atr":execution["cost_atr"]},"structural_evidence":{**levels,"structural_breach":breach,"invalidation_source":source,"stop_model":sm},"liquidity_evidence":liq,"location_evidence":space,"dynamic_target":target,"probability_evidence":prob,"trade_economics":econ,"lifecycle":lifecycle,"gate_matrix":{"8E_stop_validity":lifecycle["05_STOP_VALIDITY"],"8F_stop_survivability":lifecycle["06_STOP_SURVIVABILITY"],"8G_target_hierarchy":lifecycle["07_TARGET_HIERARCHY"],"8H_available_space":lifecycle["08_SPACE_VALIDATION"],"8I_effective_rr":lifecycle["09_EFFECTIVE_RR"],"8K_expected_value":lifecycle["11_EXPECTED_VALUE"],"8L_trade_economics":lifecycle["12_ECONOMICS"],"8M_final_risk_gate":lifecycle["13_RISK_GATE"]},"counter_evidence":counter,"missing_evidence":missing,"observations":obs,"professional_reasoning":{"entry_stop_target_chain":f"ENTRY={entry:.6f}->INVALIDATION={struct if struct is not None else 'NONE'}->STOP={stop if stop is not None else 'NONE'}->TARGET={tl if tl is not None else 'NONE'}->REAL_RR={rr:.3f}->EFFECTIVE_RR={plan.get('effective_rr',0):.3f}","structural_stop_reasoning":f"source={source or 'NONE'};quality={sm.get('quality',0):.1f};fallback_is_non_ready=True","target_hierarchy_reasoning":f"selected={target.get('source') or 'NONE'};rank={target.get('hierarchy_rank','NONE')};candidates={target.get('candidate_trace',[])};hierarchy_before_distance=True","stop_survivability":f"state={surv.get('state')};max_AE={surv.get('max_adverse_excursion_atr',0):.3f};p95_AE={surv.get('p95_adverse_excursion_atr',0):.3f};margin={surv.get('survival_margin_atr',0):.3f}","expected_value_reasoning":f"probability={prob.get('percent') if prob.get('percent') is not None else 'UNAVAILABLE'}%;break_even={econ.get('break_even_probability',1)*100:.2f}%;probability_edge={econ.get('probability_edge') if econ.get('probability_edge') is not None else 'UNAVAILABLE'};EV_R={econ.get('expected_value_r') if econ.get('expected_value_r') is not None else 'UNAVAILABLE'};class={econ.get('edge_class')}","economic_veto":"PASS" if ready else "VETO: "+";".join(counter+missing+["ECONOMICS_NOT_READY"]),"lifecycle":lifecycle},"decision_path":"E8 validates structural risk, target hierarchy, survivability and trade economics only; E9 retains final trade authority."}
    return EngineResult("E8",NAME,ready,float(score),output,tuple(counter+missing+([] if ready else ["ECONOMICS_NOT_READY"])))
