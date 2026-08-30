from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Setup Brain"; QUESTION="What setup is forming, in what direction, and at what stage?"; ARCHITECTURE="E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V29"; VERSION="29.0"
MIN_BARS=60; ATR_PERIOD=14; MIN_SPACE_ATR=.75; MAX_EVENT_AGE_BARS=3
SETUP_FAMILIES=("LIQUIDITY_REVERSAL","AUCTION_ACCEPTANCE_CONTINUATION","BREAKOUT_RETEST","TREND_PULLBACK","BREAKOUT","IMPULSE_CONTINUATION")
LIFECYCLE=("ABSENT","FORMING","VALIDATING","MATURE","FAILED","INVALIDATED","EXPIRED")

def _payload(u,n):
    r=u.get(n); return r.output if r else {}
def _text(v): return str(v or "").upper().strip()
def _norm(v):
    t=_text(v)
    if t in {"UP","BULLISH","BUY","BUYERS","LONG","TREND_UP"}: return "BUY"
    if t in {"DOWN","BEARISH","SELL","SELLERS","SHORT","TREND_DOWN"}: return "SELL"
    return "NEUTRAL"
def _num(v,d=0.):
    try:return float(v)
    except (TypeError,ValueError):return d
def _dedupe(v):return list(dict.fromkeys(str(x) for x in v if x))
def _atr(bars):
    s=bars[-(ATR_PERIOD+1):]
    if len(s)<2:return 0.
    tr=[]
    for i,c in enumerate(s):
        h,l=_num(c.get("high")),_num(c.get("low")); p=_num(s[i-1].get("close")) if i else 0.
        tr.append(max(0.,h-l) if i==0 else max(h-l,abs(h-p),abs(l-p)))
    return mean(tr[-ATR_PERIOD:])
def _auction(e):
    ev=_text(e.get("event",e.get("finding"))); st=_text(e.get("auction_state",e.get("state")))
    terminal=st in {"CONFIRMED","TERMINALLY_CONFIRMED","ACCEPTED","REJECTED"} or "TERMINAL" in st
    d="NEUTRAL"
    if any(x in ev for x in ("HIGH_SWEEP_REJECTION","HIGH_FAILED_BREAK_RECLAIM")):d="SELL"
    elif any(x in ev for x in ("LOW_SWEEP_REJECTION","LOW_FAILED_BREAK_RECLAIM")):d="BUY"
    elif any(x in ev for x in ("HIGH_ACCEPTANCE","HIGH_BREAK")):d="BUY"
    elif any(x in ev for x in ("LOW_ACCEPTANCE","LOW_BREAK")):d="SELL"
    return {"event":ev,"state":st,"terminal":terminal,"pending":st=="PENDING" or "PENDING" in ev,"age_bars":max(0,int(_num(e.get("event_age_bars")))),"direction":d,"level":_num(e.get("event_level")),"event_id":str(e.get("event_id") or e.get("event_candle_id") or "")}
def _structure(e):return _text(e.get("finding",e.get("structure_state"))),_norm(e.get("internal_state",e.get("internal_count_state"))),_norm(e.get("external_state",e.get("external_count_state")))
def _direction(e1,e2,e3,e4):
    a=_auction(e4); p=_norm(e1.get("directional_pressure",e1.get("pressure"))); f,i,x=_structure(e3); s=[]; c=[]
    if p!="NEUTRAL":s.append(f"E1_PRESSURE={p}")
    if i!="NEUTRAL":s.append(f"E3_INTERNAL={i}")
    if x!="NEUTRAL":s.append(f"E3_EXTERNAL={x}")
    if a["direction"]!="NEUTRAL":s.append(f"E4_AUCTION={a['direction']}")
    if "MIXED" in f or "TRANSITION" in f:c.append("STRUCTURE_NOT_RESOLVED")
    if i!="NEUTRAL" and x!="NEUTRAL" and i!=x:c.append("EXTERNAL_INTERNAL_STRUCTURE_CONFLICT")
    if p!="NEUTRAL" and a["direction"]==p:d,src=p,"E1_E4_DIRECTIONAL_CORE"
    elif i!="NEUTRAL" and a["direction"]==i:d,src=i,"E3_E4_DIRECTIONAL_CORE"
    elif i==x and i!="NEUTRAL":d,src=i,"E3_STRUCTURE_CONVERGENCE"
    elif a["direction"]!="NEUTRAL":d,src=a["direction"],"E4_EVENT_WITH_CONTEXT_CONFLICT"
    elif p!="NEUTRAL":d,src=p,"E1_CONTEXT_ONLY"
    else:d,src="NEUTRAL","NO_DIRECTIONAL_THESIS"
    if p!=a["direction"] and p!="NEUTRAL" and a["direction"]!="NEUTRAL":c.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    e2f=_text(e2.get("finding",e2.get("state"))); e2d=_norm(e2.get("direction",e2.get("opportunity_direction")))
    if e2d!="NEUTRAL" and not any(z in e2f for z in ("UNRESOLVED","UNPROVEN","AMBIGUOUS")):
        if d==e2d:s.append(f"E2_DIRECTION={e2d}")
        elif d!="NEUTRAL":c.append("E2_DIRECTION_DISAGREEMENT")
        else:d,src=e2d,"E2_CORROBORATION"
    return d,_dedupe(s),_dedupe(c),src
def _candidates(d,a,e1,e3,e5,primary_context):
    ev=a["event"]; trend=_norm(e1.get("trend_state",e1.get("finding"))); out=[]
    def add(n,x,b,e,priority="ALTERNATIVE"):
        if x in ("BUY","SELL"):out.append({"name":n,"direction":x,"base_quality":b,"evidence":e,"event_required":True,"hypothesis_priority":priority})
    if "FAILED_BREAK_RECLAIM" in ev or "SWEEP_REJECTION" in ev:
        reversal=a["direction"]
        priority="PRIMARY" if reversal==primary_context else "ALTERNATIVE"
        add("LIQUIDITY_REVERSAL",reversal,82,["E4_LIQUIDITY_EVENT","E4_DIRECTIONAL_RESPONSE"],priority)
    if "ACCEPTANCE" in ev:add("AUCTION_ACCEPTANCE_CONTINUATION",a["direction"],76,["E4_ACCEPTANCE_EVENT","E4_AUCTION_RESPONSE"],"PRIMARY" if a["direction"]==primary_context else "ALTERNATIVE")
    if any(z in ev for z in ("BREAKOUT_RETEST","BREAKOUT","BOS")) or _text(e3.get("bos",e3.get("break_of_structure"))) in {"BREAK","BOS","YES"}:
        add("BREAKOUT_RETEST",d,72,["E3_BREAK_EVENT","E4_AUCTION_CONTEXT"],"PRIMARY" if d==primary_context else "ALTERNATIVE");add("BREAKOUT",d,68,["E3_BOS","E4_AUCTION_CONTEXT"],"PRIMARY" if d==primary_context else "ALTERNATIVE")
    if trend==d and "PULLBACK" in _text(e1.get("finding",e1.get("trend_state"))):add("TREND_PULLBACK",d,66,["E1_TREND_ALIGNMENT","E3_STRUCTURE"],"PRIMARY")
    rp,vr=_text(e5.get("repricing_state")),_text(e5.get("value_response"))
    if d in ("BUY","SELL") and ("REPRICING_STARTING" in rp or "ACCEPTED_ABOVE_VALUE" in vr or "ACCEPTED_BELOW_VALUE" in vr):add("IMPULSE_CONTINUATION",d,60,["E5_REPRICING_CONTEXT","E1_DIRECTIONAL_CONTEXT"],"PRIMARY" if d==primary_context else "ALTERNATIVE")
    return out
def _evidence(src,statement,kind="SUPPORT",strength="MEDIUM"):return {"source":src,"kind":kind,"strength":strength,"statement":statement}
def _identity(setup,d,e3,a,e5):
    anchor=a.get("event_id") or (f"LEVEL:{a['level']:.5f}" if a.get("level") else "")
    basis="E4_EVENT_ID" if a.get("event_id") else "E4_EVENT_LEVEL"
    if not anchor:anchor=f"VALUE:{_num(e5.get('value_distance_atr')):.3f}";basis="E5_VALUE_CONTEXT"
    return f"{setup}:{d}:{anchor}",basis
def _result(state,setup,d,stage,maturity,thesis,q,conf,exists,sup,con,miss,next_req,inv,cands,rejected,trace,ledger):
    sup,con,miss,next_req,inv=map(_dedupe,(sup,con,miss,next_req,inv)); reasons=_dedupe(con+["SETUP_NOT_TRADE_READY"])
    selected=trace.get("selected_hypothesis") or setup
    out={"architecture":ARCHITECTURE,"version":VERSION,"question":QUESTION,"role":"SETUP_FORMATION_REASONER","reasoning_role":"SETUP_FORMATION_REASONER","decision_authority":"E9","trade_decision_authority":False,"state":state,"setup_state":state,"finding":state,"setup":setup,"setup_family":setup,"candidate_setup":setup,"candidate_setup_identity":trace.get("candidate_identity"),"candidate_identity_basis":trace.get("candidate_identity_basis"),"candidate_setup_thesis":thesis,"direction":d,"direction_thesis":thesis,"direction_source":trace.get("direction_source"),"stage":stage,"formation_stage":stage,"lifecycle":stage,"lifecycle_states":list(LIFECYCLE),"maturity":maturity,"thesis":thesis,"setup_exists":exists,"trade_ready":False,"trade_readiness":"NOT_READY","setup_quality":round(max(0,min(100,q)),2),"confidence":round(max(0,min(100,conf)),2),"candidate_setups":[c["name"] for c in cands],"candidate_states":cands,"selected_hypothesis":selected,"rejected_hypotheses":_dedupe(rejected),"rejected_setups":_dedupe(rejected),"supporting_evidence":sup,"counter_evidence":con,"missing_evidence":miss,"missing_proof":miss,"next_required_evidence":next_req,"invalidation":inv,"evidence_ledger":ledger,"reasoning_trace":trace,"reason_codes":reasons,"professional_reasoning":{"conclusion":thesis,"selected_hypothesis":selected,"why_it_is_forming":sup,"what_is_wrong_with_the_thesis":con,"what_is_missing":miss,"what_must_happen_next":next_req,"what_invalidates_it":inv,"formation_stage":stage,"maturity":maturity,"setup_quality":round(max(0,min(100,q)),2),"confidence":round(max(0,min(100,conf)),2),"decision_boundary":"E6 describes and stages the setup; E9 alone decides whether a trade is permitted."}}
    return EngineResult("E6",NAME,False,max(0,min(100,q)),out,tuple(reasons))

def analyze_e6(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or [])
    if len(bars)<MIN_BARS:return _result("NO_SETUP","NONE","NEUTRAL","ABSENT","UNRESOLVED","Insufficient closed-candle evidence.",0,100,False,[],["INSUFFICIENT_HISTORY"],["sufficient_closed_candle_data"],[f"wait for at least {MIN_BARS} valid closed candles"],["insufficient_history"],[],[],{"selected_hypothesis":None},[_evidence("DATA",f"closed_candles={len(bars)}","CONSTRAINT","HIGH")])
    try:
        if _atr(bars)<=0:raise ValueError
        for c in bars[-MIN_BARS:]:
            for k in ("open","high","low","close"):
                if float(c[k])!=float(c[k]):raise ValueError
    except (KeyError,TypeError,ValueError):return _result("NO_SETUP","NONE","NEUTRAL","ABSENT","UNRESOLVED","Invalid closed-candle OHLC.",0,100,False,[],["INVALID_MARKET_DATA"],["valid_closed_candle_ohlc"],["provide valid closed-candle OHLC values"],["invalid_market_data"],[],[],{"selected_hypothesis":None},[_evidence("DATA","closed-candle OHLC validation failed","CONSTRAINT","HIGH")])
    e1,e2,e3,e4,e5=(_payload(upstream,n) for n in ("E1","E2","E3","E4","E5"));a=_auction(e4);d,ds,dc,src=_direction(e1,e2,e3,e4);opp=_text(e2.get("finding",e2.get("state"))) or "UNRESOLVED";struct,internal,external=_structure(e3);space=_num(e5.get("available_space_atr_long") if d=="BUY" else e5.get("available_space_atr_short"));location=bool(e5)
    context_votes=[_norm(e1.get("directional_pressure",e1.get("pressure"))),internal,external];context_votes=[x for x in context_votes if x!="NEUTRAL"]
    primary_context=max(set(context_votes),key=context_votes.count) if context_votes else "NEUTRAL";context_consensus=(context_votes.count(primary_context)/len(context_votes)) if context_votes else 0.0
    causal={"context":bool(e1),"event":bool(a["event"]),"response":a["terminal"] or _text(e4.get("response_actor")) not in {"","UNKNOWN","NONE"},"structure":not ("MIXED" in struct or "TRANSITION" in struct) and internal!="NEUTRAL" and external!="NEUTRAL"}; causal_count=sum(causal.values())
    contradictions=list(dc)
    if "MIXED" in struct or "TRANSITION" in struct:contradictions+=["STRUCTURE_CONFLICT"]
    if a["pending"] and not a["terminal"]:contradictions+=["AUCTION_PENDING"]
    if not location:contradictions+=["LOCATION_CONFLICT"]
    if d in ("BUY","SELL") and space<MIN_SPACE_ATR:contradictions+=["SPACE_CONFLICT"]
    if internal!="NEUTRAL" and external!="NEUTRAL" and internal!=external:contradictions+=["STRUCTURE_INTERNAL_EXTERNAL_CONFLICT"]
    contradictions=_dedupe(contradictions);cands=_candidates(d,a,e1,e3,e5,primary_context);scored=[]
    for c in cands:
        q=float(c["base_quality"]);sup=list(c["evidence"]);con=[];miss=[];counter_trend=c["direction"]!=primary_context and primary_context!="NEUTRAL"
        if counter_trend:
            q-=18;con.append("COUNTER_TREND_HYPOTHESIS")
            if not a["terminal"]:q-=18;con.append("REVERSAL_REQUIRES_TERMINAL_AUCTION");miss.append("terminal_auction_confirmation")
            if internal==primary_context or external==primary_context:q-=10;con.append("STRUCTURE_STILL_SUPPORTS_PRIMARY_CONTEXT");miss.append("structural_reversal_evidence")
        if c["direction"]!=d:q-=25;con.append("DIRECTION_MISMATCH")
        if a["terminal"]:q+=8
        else:q-=5;miss.append("terminal_auction_confirmation")
        if opp in {"UNRESOLVED","UNPROVEN","AMBIGUOUS",""}:q-=8;miss.append("opportunity_acceptance_follow_through")
        else:q+=4;sup.append("E2_OPPORTUNITY_RESOLVED")
        if "MIXED" in struct or "TRANSITION" in struct:q-=7;miss.append("structure_resolution")
        else:q+=6;sup.append("E3_STRUCTURE_RESOLVED")
        if space>=MIN_SPACE_ATR:q+=6;sup.append(f"SPACE_OK={space:.3f}ATR")
        else:q-=15;con.append("SPACE_CONFLICT");miss.append("sufficient_structural_space")
        for x in contradictions:
            if x not in con:con.append(x)
        anti=causal_count>=3 and sum(causal.values())-int(causal["event"])>=2
        if not anti:q-=12;miss.append("independent_context_response_structure_support")
        proof={"context":causal["context"],"event":causal["event"],"response":causal["response"],"structure":causal["structure"],"direction":c["direction"]==d and d!="NEUTRAL","location":location,"space":space>=MIN_SPACE_ATR,"freshness":a["age_bars"]<=MAX_EVENT_AGE_BARS,"terminal_auction":a["terminal"] if counter_trend else True,"structural_reversal":not counter_trend or (internal!=primary_context and external!=primary_context)}
        scored.append({**c,"causal_score":round(max(0,min(100,q)),2),"supporting_evidence":_dedupe(sup),"counter_evidence":_dedupe(con),"missing_proof":_dedupe(miss),"proof_gates":proof,"causal_minimum":causal,"anti_overfit_pass":anti,"context_role":"ALTERNATIVE" if counter_trend else "PRIMARY_CONTEXT_ALIGNED"})
    def rank(c):
        reversal_confirmed=c["direction"]!=primary_context and a["terminal"]
        return (1 if c["direction"]==primary_context else (0 if not reversal_confirmed else 1),c["causal_score"],sum(bool(v) for v in c["proof_gates"].values()))
    scored.sort(key=rank,reverse=True);sel=scored[0] if scored else None
    if not sel:return _result("NO_SETUP","NONE",d,"ABSENT","UNRESOLVED","No plausible setup survives causal screening.",10,65,False,ds,contradictions,["causal_setup_evidence"],["context + event + response + structure"],[],scored,[],{"selected_hypothesis":None},[])
    setup=sel["name"];identity,identity_basis=_identity(setup,sel["direction"],e3,a,e5);proof=sel["proof_gates"];rejected=[f"{x['name']}:OUTRANKED_BY_{setup}:SCORE_{x['causal_score']:.2f}" for x in scored[1:]];maturity=round(max(0,min(100,sel["causal_score"])),2)
    stage="MATURE" if maturity>=82 and all(proof.values()) else ("VALIDATING" if maturity>=60 else "FORMING")
    if sel["direction"]!=primary_context and not a["terminal"]:stage="FORMING"
    exists=bool(sel) and stage not in {"FAILED","INVALIDATED","EXPIRED"};thesis=f"{sel['direction']} {setup} is {stage.lower()}: the thesis is {'context-aligned' if sel['direction']==primary_context else 'counter-trend and requires independent reversal proof'}."
    sup=ds+sel["supporting_evidence"]+(["PRIMARY_CONTEXT_ALIGNMENT"] if sel["direction"]==primary_context else []);con=dc+sel["counter_evidence"];miss=sel["missing_proof"];next_req=[]
    if not a["terminal"] and sel["direction"]!=primary_context:next_req.append("terminal_auction_confirmation")
    if sel["direction"]!=primary_context and (internal==primary_context or external==primary_context):next_req.append("structural_reversal_evidence")
    next_req+=miss;inv=["auction invalidates if event ages beyond MAX_EVENT_AGE_BARS without confirmation"]
    inv.append("loss_of_dominant_context" if sel["direction"]==primary_context else "failure_to_reclaim_or_close_beyond_reversal_level")
    ledger=[_evidence("E1",f"dominant_context={primary_context}; consensus={context_consensus:.2f}","SUPPORT" if sel["direction"]==primary_context else "COUNTER_EVIDENCE","HIGH"),_evidence("E4",f"auction={a['event']}; state={a['state']}; terminal={a['terminal']}","SUPPORT","HIGH"),_evidence("E3",f"internal={internal}; external={external}","SUPPORT" if sel["direction"]==primary_context else "COUNTER_EVIDENCE","HIGH"),_evidence("E5",f"available_space_atr={space:.3f}","SUPPORT" if space>=MIN_SPACE_ATR else "COUNTER_EVIDENCE","MEDIUM")]
    trace={"selected_hypothesis":setup,"candidate_identity":identity,"candidate_identity_basis":identity_basis,"direction_source":src,"directional_evidence":ds,"directional_conflicts":dc,"dominant_context":primary_context,"context_consensus":round(context_consensus,3),"hypothesis_role":"PRIMARY_CONTEXT_ALIGNED" if sel["direction"]==primary_context else "ALTERNATIVE_COUNTER_TREND","counter_trend_gate":"PASSED" if sel["direction"]==primary_context or a["terminal"] else "BLOCKED","reversal_requires_terminal_auction":sel["direction"]!=primary_context,"explicit_reversal_proof":sel["direction"]!=primary_context and a["terminal"]}
    return _result("SETUP_FORMING" if stage in {"FORMING","VALIDATING"} else "SETUP_MATURE",setup,sel["direction"],stage,maturity,thesis,sel["causal_score"],min(100,60+sel["causal_score"]*.4),exists,sup,con,miss,_dedupe(next_req),inv,scored,rejected,trace,ledger)
