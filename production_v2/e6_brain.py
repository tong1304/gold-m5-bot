from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Setup Brain"; QUESTION="What setup is forming, in what direction, and at what stage?"; ARCHITECTURE="E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V31"; VERSION="31.0"
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
def _structure_is_invalidated(e):
    """Only E3's explicit active lifecycle may invalidate E6.

    Do not infer invalidation from descriptive finding text or from a generic
    non-empty invalidation catalogue. E3 is the sole owner of active market
    structure state; downstream brains must consume that state, not recreate it.
    """
    lifecycle=_text(e.get("lifecycle"))
    invalidation=_text(e.get("invalidation"))
    active_flag=e.get("structure_invalidated") is True or e.get("active_invalidation") is True
    explicit_lifecycle=lifecycle=="INVALIDATED"
    explicit_invalidation=invalidation in {
        "ACTIVE_INVALIDATION",
        "STRUCTURE_INVALIDATED",
        "BULLISH_STRUCTURE_INVALIDATED",
        "BEARISH_STRUCTURE_INVALIDATED",
    }
    return bool(active_flag or explicit_lifecycle or explicit_invalidation)
def _direction(e1,e2,e3,e4):
    a=_auction(e4); p=_norm(e1.get("directional_pressure",e1.get("pressure"))); f,i,x=_structure(e3); s=[]; c=[]
    if p!="NEUTRAL":s.append(f"E1_PRESSURE={p}")
    if i!="NEUTRAL":s.append(f"E3_INTERNAL={i}")
    if x!="NEUTRAL":s.append(f"E3_EXTERNAL={x}")
    if a["direction"]!="NEUTRAL":s.append(f"E4_AUCTION={a['direction']}")
    if "MIXED" in f or "TRANSITION" in f:c.append("STRUCTURE_NOT_RESOLVED")
    if i!="NEUTRAL" and x!="NEUTRAL" and i!=x:c.append("EXTERNAL_INTERNAL_STRUCTURE_CONFLICT")
    if p!=a["direction"] and p!="NEUTRAL" and a["direction"]!="NEUTRAL":c.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if p!="NEUTRAL" and i!="NEUTRAL" and p==i:
        d,src=p,"E1_E3_DIRECTIONAL_CORE"
    elif i==x and i!="NEUTRAL":
        d,src=i,"E3_STRUCTURE_CONVERGENCE"
    elif p!="NEUTRAL" and a["direction"]==p:
        d,src=p,"E1_E4_DIRECTIONAL_CORE"
    elif a["terminal"] and a["direction"]!="NEUTRAL":
        d,src=a["direction"],"E4_TERMINAL_AUCTION"
    elif p!="NEUTRAL":
        d,src=p,"E1_CONTEXT_ONLY"
    elif i!="NEUTRAL":
        d,src=i,"E3_STRUCTURE_ONLY"
    elif a["direction"]!="NEUTRAL":
        d,src=a["direction"],"E4_PENDING_HYPOTHESIS"
    else:
        d,src="NEUTRAL","NO_DIRECTIONAL_THESIS"
    if a["pending"] and a["direction"] not in {"NEUTRAL",d}:c.append("E4_PENDING_DIRECTION_NOT_AUTHORITATIVE")
    e2f=_text(e2.get("finding",e2.get("state"))); e2d=_norm(e2.get("direction",e2.get("opportunity_direction")))
    if e2d!="NEUTRAL" and not any(z in e2f for z in ("UNRESOLVED","UNPROVEN","AMBIGUOUS")):
        if d==e2d:s.append(f"E2_DIRECTION={e2d}")
        elif d!="NEUTRAL":c.append("E2_DIRECTION_DISAGREEMENT")
        else:d,src=e2d,"E2_CORROBORATION"
    return d,_dedupe(s),_dedupe(c),src
def _candidates(d,a,e1,e3,e5):
    ev=a["event"]; trend=_norm(e1.get("trend_state",e1.get("finding"))); out=[]
    def add(n,x,b,e):
        if x in ("BUY","SELL"):out.append({"name":n,"direction":x,"base_quality":b,"evidence":e,"event_required":True})
    event_direction=a["direction"]; event_can_drive_setup=a["terminal"] or event_direction in {"NEUTRAL",d}
    if ("FAILED_BREAK_RECLAIM" in ev or "SWEEP_REJECTION" in ev) and event_can_drive_setup:add("LIQUIDITY_REVERSAL",event_direction,82,["E4_LIQUIDITY_EVENT","E4_DIRECTIONAL_RESPONSE"])
    if "ACCEPTANCE" in ev and event_can_drive_setup:add("AUCTION_ACCEPTANCE_CONTINUATION",event_direction,76,["E4_ACCEPTANCE_EVENT","E4_AUCTION_RESPONSE"])
    if any(z in ev for z in ("BREAKOUT_RETEST","BREAKOUT","BOS")) or _text(e3.get("bos",e3.get("break_of_structure"))) in {"BREAK","BOS","YES"}:
        add("BREAKOUT_RETEST",d,72,["E3_BREAK_EVENT","E4_AUCTION_CONTEXT"]);add("BREAKOUT",d,68,["E3_BOS","E4_AUCTION_CONTEXT"])
    if trend==d and "PULLBACK" in _text(e1.get("finding",e1.get("trend_state"))):add("TREND_PULLBACK",d,66,["E1_TREND_ALIGNMENT","E3_STRUCTURE"])
    rp,vr=_text(e5.get("repricing_state")),_text(e5.get("value_response"))
    if d in ("BUY","SELL") and ("REPRICING_STARTING" in rp or "ACCEPTED_ABOVE_VALUE" in vr or "ACCEPTED_BELOW_VALUE" in vr):add("IMPULSE_CONTINUATION",d,60,["E5_REPRICING_CONTEXT","E1_DIRECTIONAL_CONTEXT"])
    return out
def _evidence(src,statement,kind="SUPPORT",strength="MEDIUM"):return {"source":src,"kind":kind,"strength":strength,"statement":statement}
def _identity(setup,d,e3,a,e5):
    anchor=a.get("event_id") or (f"LEVEL:{a['level']:.5f}" if a.get("level") else ""); basis="E4_EVENT_ID" if a.get("event_id") else "E4_EVENT_LEVEL"
    if not anchor:anchor=f"VALUE:{_num(e5.get('value_distance_atr')):.3f}";basis="E5_VALUE_CONTEXT"
    return f"{setup}:{d}:{anchor}",basis
def _result(state,setup,d,stage,maturity,thesis,q,conf,exists,sup,con,miss,next_req,inv,cands,rejected,trace,ledger):
    sup,con,miss,next_req,inv=map(_dedupe,(sup,con,miss,next_req,inv)); reasons=_dedupe(con+["SETUP_NOT_TRADE_READY"]); selected=trace.get("selected_hypothesis") or setup
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
    e1,e2,e3,e4,e5=(_payload(upstream,n) for n in ("E1","E2","E3","E4","E5"))
    if _structure_is_invalidated(e3):
        finding=_text(e3.get("finding",e3.get("structure_state"))) or "STRUCTURE_INVALIDATED"
        return _result("INVALIDATED","NONE","NEUTRAL","INVALIDATED","INVALIDATED","No setup survives because E3 has explicitly invalidated the active market structure.",0,100,False,[],["E3_STRUCTURE_INVALIDATED",finding],["a new closed-candle structure lifecycle after invalidation"],["E3 must establish a new valid structure before E6 can form a setup"],[finding],[],[],{"selected_hypothesis":None,"direction_source":"E3_STRUCTURE_INVALIDATION","lifecycle_owner":"E3"},[_evidence("E3",f"structure_lifecycle={_text(e3.get('lifecycle')) or 'INVALIDATED'}; finding={finding}","INVALIDATION","HIGH")])
    a=_auction(e4);d,ds,dc,src=_direction(e1,e2,e3,e4);opp=_text(e2.get("finding",e2.get("state"))) or "UNRESOLVED";struct,internal,external=_structure(e3);space=_num(e5.get("available_space_atr_long") if d=="BUY" else e5.get("available_space_atr_short"));location=bool(e5)
    causal={"context":bool(e1),"event":bool(a["event"]),"response":a["terminal"] or _text(e4.get("response_actor")) not in {"","UNKNOWN","NONE"},"structure":not ("MIXED" in struct or "TRANSITION" in struct) and internal!="NEUTRAL" and external!="NEUTRAL"}; causal_count=sum(causal.values())
    contradictions=list(dc)
    if "MIXED" in struct or "TRANSITION" in struct:contradictions+=["STRUCTURE_CONFLICT"]
    if a["pending"] and not a["terminal"]:contradictions+=["AUCTION_PENDING"]
    if not location:contradictions+=["LOCATION_CONFLICT"]
    if d in ("BUY","SELL") and space<MIN_SPACE_ATR:contradictions+=["SPACE_CONFLICT"]
    if internal!="NEUTRAL" and external!="NEUTRAL" and internal!=external:contradictions+=["STRUCTURE_INTERNAL_EXTERNAL_CONFLICT"]
    contradictions=_dedupe(contradictions);cands=_candidates(d,a,e1,e3,e5);scored=[]
    for c in cands:
        q=float(c["base_quality"]);sup=list(c["evidence"]);con=[];miss=[]
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
        proof={"context":causal["context"],"event":causal["event"],"response":causal["response"],"structure":causal["structure"],"direction":c["direction"]==d and d!="NEUTRAL","location":location,"space":space>=MIN_SPACE_ATR,"freshness":a["age_bars"]<=MAX_EVENT_AGE_BARS}
        scored.append({**c,"causal_score":round(max(0,min(100,q)),2),"supporting_evidence":_dedupe(sup),"counter_evidence":_dedupe(con),"missing_proof":_dedupe(miss),"proof_gates":proof,"causal_minimum":causal,"anti_overfit_pass":anti})
    scored.sort(key=lambda x:(x["causal_score"],sum(bool(v) for v in x["proof_gates"].values())),reverse=True);sel=scored[0] if scored else None
    if not sel:return _result("NO_SETUP","NONE",d,"ABSENT","UNRESOLVED","No plausible setup survives causal screening.",10,65,False,ds,contradictions,["causal_setup_evidence"],["context + event + response + structure"],[],scored,[],{"selected_hypothesis":None},[])
    setup=sel["name"];identity,identity_basis=_identity(setup,d,e3,a,e5);proof=sel["proof_gates"];rejected=[f"{x['name']}:OUTRANKED_BY_{setup}:SCORE_{x['causal_score']:.2f}" for x in scored[1:]]
    explicit=(a["terminal"] and a["direction"] in ("BUY","SELL") and a["direction"]!=sel["direction"]) or _structure_is_invalidated(e3);stale=a["age_bars"]>MAX_EVENT_AGE_BARS
    if stale:stage=mat="EXPIRED";q=min(sel["causal_score"],40);conf=30;thesis=f"{d} {setup} expired because its initiating event is stale."
    elif explicit:stage=mat="INVALIDATED";q=min(sel["causal_score"],35);conf=25;thesis=f"{d} {setup} is invalidated by explicit opposing evidence."
    elif all(proof.values()) and causal_count==4 and sel["anti_overfit_pass"] and not contradictions:stage=mat="MATURE";q=max(82,sel["causal_score"]);conf=min(96,80+sel["causal_score"]*.14);thesis=f"{d} {setup} is mature: context, event, response and structure form a coherent causal chain."
    elif proof["direction"] and proof["event"] and proof["response"] and sel["anti_overfit_pass"]:stage=mat="VALIDATING";q=sel["causal_score"];conf=72;thesis=f"{d} {setup} is validating: the thesis is alive, but proof gates remain incomplete."
    else:stage=mat="FORMING";q=sel["causal_score"];conf=62;thesis=f"{d} {setup} is forming: a plausible hypothesis exists, but its causal chain is incomplete."
    sup=ds+sel["supporting_evidence"];con=contradictions+sel["counter_evidence"];miss=sel["missing_proof"];next_req=[]
    if not proof["event"]:next_req.append("a causal setup event, not an isolated observation")
    if not proof["response"]:next_req.append("closed-candle response to the event")
    if not proof["structure"]:next_req.append("structure agreement or confirmed structural response")
    if opp in {"UNRESOLVED","UNPROVEN","AMBIGUOUS"}:next_req.append("E2 opportunity acceptance/follow-through")
    if space<MIN_SPACE_ATR and d in ("BUY","SELL"):next_req.append(f"structural space >= {MIN_SPACE_ATR:.2f} ATR")
    if contradictions:next_req.append("resolve or absorb the active contradiction before maturity")
    if setup=="LIQUIDITY_REVERSAL":inv=["closed-candle acceptance back through liquidity anchor","opposing confirmed auction response","protected structure breaks against reversal"]
    elif setup in {"BREAKOUT","BREAKOUT_RETEST","AUCTION_ACCEPTANCE_CONTINUATION"}:inv=["closed-candle rejection back through acceptance/breakout anchor","failed follow-through","structure invalidates continuation"]
    elif setup=="TREND_PULLBACK":inv=["trend no longer agrees with setup direction","protected structure breaks","pullback fails to continue"]
    else:inv=["closed-candle structure invalidates directional thesis","opposing confirmed auction response"]
    if a["level"]:inv.append(f"anchor_level={a['level']:.5f}")
    ledger=[_evidence("E1",f"observation={_text(e1.get('finding')) or 'NONE'}","OBSERVATION","HIGH"),_evidence("E1",f"interpretation=direction={_norm(e1.get('directional_pressure',e1.get('pressure')))}","INTERPRETATION","MEDIUM"),_evidence("E2",f"observation=opportunity={opp}","OBSERVATION","HIGH"),_evidence("E3",f"observation=structure={struct}","STRUCTURE","HIGH"),_evidence("E4",f"observation=event={a['event'] or 'NONE'}","EVENT","HIGH"),_evidence("E4",f"interpretation=auction={a['direction']},state={a['state'] or 'NONE'}","INTERPRETATION","HIGH"),_evidence("E5",f"observation=space_atr={space:.4f}","CONSTRAINT","HIGH"),_evidence("E6",f"counter_evidence={','.join(_dedupe(con)) or 'NONE'}","COUNTER","HIGH")]
    trace={"summary":f"E1->E2->E3->E4->E5->contradiction_engine->hypothesis_competition->lifecycle={stage}","decision":"DESCRIBE_SETUP_ONLY","selected_hypothesis":setup,"candidate_identity":identity,"candidate_identity_basis":identity_basis,"direction_source":src,"causal_minimum":causal,"causal_minimum_rule":"context + event + response + structure must align for maturity","anti_overfitting":{"pass":sel["anti_overfit_pass"],"rule":"event alone cannot create a mature setup"},"hypothesis_competition":{"primary":setup,"ranked":[{"name":x["name"],"direction":x["direction"],"causal_score":x["causal_score"],"proof_gates":x["proof_gates"],"rejected":x is not sel} for x in scored]},"contradiction_engine":{"direction":_dedupe([x for x in contradictions if "DIRECTION" in x]),"structure":_dedupe([x for x in contradictions if "STRUCTURE" in x]),"auction":_dedupe([x for x in contradictions if "AUCTION" in x]),"location":_dedupe([x for x in contradictions if "LOCATION" in x]),"space":_dedupe([x for x in contradictions if "SPACE" in x])},"thesis_status":"INVALIDATED" if explicit else ("EXPIRED" if stale else "ALIVE"),"lifecycle_rule":"contradiction weakens; explicit invalidating evidence kills; stale event expires","evidence_integrity":{"status":"PASS" if all((e1,e2,e3,e4,e5)) else "PARTIAL","upstream_is_source_of_truth":True}}
    return _result(stage,setup,d,stage,mat,thesis,q,conf,True,sup,con,miss,next_req,inv,scored,rejected,trace,ledger)
