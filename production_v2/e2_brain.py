from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V3"


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    prev = float(bars[0]["close"])
    for b in bars[-period:]:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    return mean(trs) if trs else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1.0 - alpha) * value
    return value


def _direction(value: Any) -> str:
    v = str(value or "NEUTRAL").upper().strip()
    return "UP" if v in {"UP", "BULLISH", "BUY", "LONG", "TREND_UP"} else "DOWN" if v in {"DOWN", "BEARISH", "SELL", "SHORT", "TREND_DOWN"} else "NEUTRAL"


def _e1(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = snapshot.get("E1_result") or {}
    return value if isinstance(value, dict) else {}


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        w = bars[i-wing:i+wing+1]; hi, lo = float(bars[i]["high"]), float(bars[i]["low"])
        if hi >= max(float(x["high"]) for x in w): highs.append(hi)
        if lo <= min(float(x["low"]) for x in w): lows.append(lo)
    return highs, lows


def _unavailable() -> dict[str, Any]:
    return {"state":"UNAVAILABLE", "architecture":ARCHITECTURE, "sub_engines_active":False, "reasoning_mode":"SINGLE_PROFESSIONAL_CORE", "question":QUESTION, "thesis":"Insufficient closed-candle history; no opportunity thesis is formed.", "regime":"UNRESOLVED", "direction":"NEUTRAL", "phase":"UNRESOLVED", "opportunity":"NONE", "opportunity_state":"WAIT", "opportunity_maturity":"UNPROVEN", "quality":"UNPROVEN", "opportunity_quality":"LOW", "opportunity_decision":"WAIT", "edge_assessment":"NO_EDGE", "alignment_with_e1":"INCONCLUSIVE", "independence":"E2_FIRST_E1_CROSS_CHECK", "auction_state":"UNKNOWN", "auction_intent":"UNKNOWN", "auction_phase":"TRANSITION", "location_context":"UNKNOWN", "regime_confidence":0.0, "confidence":0.0, "opportunity_score":0.0, "acceptance_quality":"UNPROVEN", "timing_state":"WAIT", "decision_factors":[], "observations":[], "evidence":[], "evidence_map":{}, "counter_evidence":["insufficient closed-candle history"], "counter_evidence_severity":"THESIS_INVALIDATION", "missing_evidence":[f"{MIN_BARS} valid closed candles"], "invalidation_evidence":[], "why_not_trade":["insufficient market data"], "counterfactual":["without sufficient history, no directional thesis is trustworthy"], "decision":None, "entry":None, "trigger":None, "risk":None, "gate":None, "trade_decision_authority":"E9_ONLY", "reason_codes":["INSUFFICIENT_MARKET_DATA"], "professional_reasoning":{"question":QUESTION,"conclusion":"NO_OPPORTUNITY_THESIS","why_now":"Insufficient evidence.","expected_path":"Wait for sufficient closed-candle history.","required_evidence":[f"{MIN_BARS} valid closed candles"],"invalidation_conditions":["data insufficiency"],"timing":"WAIT","opportunity_quality":"LOW","opportunity_decision":"WAIT","edge_assessment":"NO_EDGE","independent_thesis":True,"e1_used_as":"CROSS_CHECK_ONLY","entry_authorized":False}}


def _quality(structure, acceptance, pullback, location, space, efficiency, volatility, rejection, extension) -> float:
    return max(0.0, min(1.0, 0.20*structure + 0.16*acceptance + 0.16*pullback + 0.12*location + 0.12*space + 0.10*efficiency + 0.08*volatility - 0.16*rejection - 0.18*extension))


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """E2 is an independent opportunity brain. It maps present and conditional opportunities; it never creates an entry or trade decision."""
    bs = _bars(snapshot)
    if len(bs) < MIN_BARS: return _unavailable()
    h=[float(b["high"]) for b in bs]; l=[float(b["low"]) for b in bs]; c=[float(b["close"]) for b in bs]; o=[float(b["open"]) for b in bs]
    last=c[-1]; atr=max(_atr(bs),1e-12); ema20=_ema(c,20); ema50=_ema(c,50); ema20p=_ema(c[:-5],20); ema50p=_ema(c[:-5],50)
    gap=(ema20-ema50)/atr; s20=(ema20-ema20p)/atr; s50=(ema50-ema50p)/atr; slope5=(c[-1]-c[-6])/atr; slope20=(c[-1]-c[-21])/atr; slope40=(c[-1]-c[-41])/atr
    ranges=[max(float(b["high"])-float(b["low"]),0.0) for b in bs]; avg20=max(mean(ranges[-20:]),1e-12); vr=mean(ranges[-5:])/avg20; travel=max(sum(ranges[-12:]),1e-12); eff=abs(c[-1]-c[-13])/travel
    hi20,lo20=max(h[-21:-1]),min(l[-21:-1]); hi40,lo40=max(h[-41:-1]),min(l[-41:-1]); width=max(hi40-lo40,1e-12); pos=max(0.0,min(1.0,(last-lo40)/width)); pos20=max(0.0,min(1.0,(last-lo20)/max(hi20-lo20,1e-12)))
    ph,pl=_pivots(bs); hh=len(ph)>=2 and ph[-1]>ph[-2]; lh=len(ph)>=2 and ph[-1]<ph[-2]; hl=len(pl)>=2 and pl[-1]>pl[-2]; ll=len(pl)>=2 and pl[-1]<pl[-2]; bull=hh and hl; bear=lh and ll
    up=sum((gap>0.35,s20>0.08,s50>-0.05,slope5>0.20,slope20>0.45,bull,eff>=0.30)); down=sum((gap<-0.35,s20<-0.08,s50<0.05,slope5<-0.20,slope20<-0.45,bear,eff>=0.30))
    span=max(h[-1]-l[-1],1e-12); body=abs(last-o[-1])/span; cp=(last-l[-1])/span; uw=(h[-1]-max(o[-1],last))/span; lw=(min(o[-1],last)-l[-1])/span
    broke_up,broke_dn=last>hi20,last<lo20; sweep_up=h[-1]>hi20 and last<=hi20; sweep_dn=l[-1]<lo20 and last>=lo20; acc_up=broke_up and cp>=0.65 and body>=0.45; acc_dn=broke_dn and cp<=0.35 and body>=0.45; rej_up=sweep_up and cp<=0.45 and uw>=0.20; rej_dn=sweep_dn and cp>=0.55 and lw>=0.20; disp_up=body>=0.60 and cp>=0.75 and span>=1.25*avg20; disp_dn=body>=0.60 and cp<=0.25 and span>=1.25*avg20
    imp_up=(c[-8]-c[-16])/atr>=1.0 and c[-8]>c[-16]; imp_dn=(c[-16]-c[-8])/atr>=1.0 and c[-8]<c[-16]; ih,il=max(h[-8:-2]),min(l[-8:-2]); ru=max(0.0,(ih-last)/max(ih-il,atr)); rd=max(0.0,(last-il)/max(ih-il,atr)); pb_up=imp_up and .20<=ru<=.65 and last>lo20 and ema20>=ema50 and (lw>=.15 or cp>=.55 or c[-1]>=c[-2]); pb_dn=imp_dn and .20<=rd<=.65 and last<hi20 and ema20<=ema50 and (uw>=.15 or cp<=.45 or c[-1]<=c[-2])
    compressed,expanding=vr<.72,vr>1.28; balanced=abs(slope20)<.65 and eff<.30 and width/atr<8.5

    if acc_up and acc_dn: base_regime,base_dir,auction="TRANSITION","NEUTRAL","TWO_SIDED_ACCEPTANCE"
    elif acc_up and not rej_up: base_regime,base_dir,auction="BREAKOUT","UP","ACCEPTANCE_UP"
    elif acc_dn and not rej_dn: base_regime,base_dir,auction="BREAKOUT","DOWN","ACCEPTANCE_DOWN"
    elif rej_up and not rej_dn and pos>=.70: base_regime,base_dir,auction="MEAN_REVERSION","DOWN","FAILED_AUCTION_HIGH"
    elif rej_dn and not rej_up and pos<=.30: base_regime,base_dir,auction="MEAN_REVERSION","UP","FAILED_AUCTION_LOW"
    elif up>=5 and up>down+1: base_regime,base_dir,auction="TREND","UP","DIRECTIONAL_AUCTION_UP"
    elif down>=5 and down>up+1: base_regime,base_dir,auction="TREND","DOWN","DIRECTIONAL_AUCTION_DOWN"
    elif balanced or (compressed and abs(up-down)<=2): base_regime,base_dir,auction="RANGE","NEUTRAL","BALANCED_AUCTION"
    else: base_regime,base_dir,auction="TRANSITION","NEUTRAL","UNCOMMITTED_AUCTION"

    candidates=[]
    def add(name, direction, regime, structure, acceptance, rejection, pullback, displacement):
        space=max((hi40-last)/atr,0.0) if direction=="UP" else max((last-lo40)/atr,0.0); location=(.10<=pos<=.75) if direction=="UP" else (.25<=pos<=.90); extended=(pos>=.92) if direction=="UP" else (pos<=.08)
        veto=[]
        if not location: veto.append("LOCATION_NOT_ADVANTAGEOUS")
        if space<1.0: veto.append("INSUFFICIENT_OPPOSING_SPACE")
        if extended: veto.append("OVEREXTENDED_LOCATION")
        if rejection and ((direction=="UP" and pos>=.70) or (direction=="DOWN" and pos<=.30)): veto.append("FAILED_AUCTION")
        if name=="BREAKOUT_CONTINUATION" and not acceptance: veto.append("NO_ACCEPTANCE")
        q=_quality(float(structure),float(acceptance or displacement),float(pullback),float(location),max(0.0,min(1.0,space/3.0)),max(0.0,min(1.0,eff/.55)),1.0 if .75<=vr<=1.55 else .35,float(rejection),float(extended))
        candidates.append({"name":name,"direction":direction,"regime":regime,"quality":q,"space_atr":space,"location_ok":location,"extended":bool(extended),"vetoes":veto,"eligible":not veto,"structure":structure,"acceptance":acceptance,"pullback":pullback,"rejection":rejection,"displacement":displacement})
    if up>=4: add("TREND_PULLBACK_CONTINUATION","UP","TREND",bull,acc_up,rej_up,pb_up,disp_up); add("TREND_CONTINUATION","UP","TREND",bull,acc_up,rej_up,False,disp_up)
    if down>=4: add("TREND_PULLBACK_CONTINUATION","DOWN","TREND",bear,acc_dn,rej_dn,pb_dn,disp_dn); add("TREND_CONTINUATION","DOWN","TREND",bear,acc_dn,rej_dn,False,disp_dn)
    if acc_up: add("BREAKOUT_CONTINUATION","UP","BREAKOUT",bull,True,rej_up,False,disp_up)
    if acc_dn: add("BREAKOUT_CONTINUATION","DOWN","BREAKOUT",bear,True,rej_dn,False,disp_dn)
    if rej_dn and pos<=.30: add("LIQUIDITY_REVERSAL","UP","MEAN_REVERSION",bull,False,True,False,disp_up)
    if rej_up and pos>=.70: add("LIQUIDITY_REVERSAL","DOWN","MEAN_REVERSION",bear,False,True,False,disp_dn)
    eligible=sorted([x for x in candidates if x["eligible"]],key=lambda x:(x["quality"],x["space_atr"],x["structure"]),reverse=True); vetoed=[x for x in candidates if not x["eligible"]]; best=eligible[0] if eligible else None; second=eligible[1] if len(eligible)>1 else None; ambiguity=bool(best and second and best["direction"]!=second["direction"] and abs(best["quality"]-second["quality"])<.12)

    if acc_up and not rej_up: intent="BUY_SIDE_REPRICING"
    elif acc_dn and not rej_dn: intent="SELL_SIDE_REPRICING"
    elif rej_up and pos>=.70: intent="FAILED_HIGH_AUCTION"
    elif rej_dn and pos<=.30: intent="FAILED_LOW_AUCTION"
    elif bull and not bear: intent="UPSIDE_CONTROL_WITHOUT_ACCEPTANCE"
    elif bear and not bull: intent="DOWNSIDE_CONTROL_WITHOUT_ACCEPTANCE"
    elif balanced: intent="TWO_SIDED_BALANCE"
    else: intent="UNCOMMITTED_AUCTION"

    if ambiguity: direction,regime,opportunity,phase="NEUTRAL","TRANSITION","WAIT_FOR_REPRICING","AMBIGUOUS"; auction="COMPETING_HYPOTHESES"
    elif best: direction,regime,opportunity=best["direction"],best["regime"],best["name"]; phase="PULLBACK" if opportunity=="TREND_PULLBACK_CONTINUATION" and best["pullback"] else "ACCEPTANCE" if opportunity=="BREAKOUT_CONTINUATION" else "REJECTION" if opportunity=="LIQUIDITY_REVERSAL" else "EXPANSION" if best["displacement"] else "DEVELOPING"
    else: direction,regime= "NEUTRAL",base_regime; opportunity="WAIT_FOR_RANGE_EDGE" if regime=="RANGE" else "WAIT_FOR_REPRICING"; phase="BALANCED" if regime=="RANGE" else "TRANSITION"
    location="EDGE_LOW" if pos<=.20 else "EDGE_HIGH" if pos>=.80 else "MID_RANGE"; space=max((hi40-last)/atr,0.0) if direction=="UP" else max((last-lo40)/atr,0.0) if direction=="DOWN" else 0.0; invalid_dist=max((last-lo40)/atr,0.0) if direction=="UP" else max((hi40-last)/atr,0.0) if direction=="DOWN" else 0.0; space_ok=space>=1.0; overextended=(direction=="UP" and pos>=.92) or (direction=="DOWN" and pos<=.08)

    counter=[]; missing=[]; invalid=[]
    if ambiguity: counter.append("competing directional hypotheses are too close")
    if direction=="UP":
        if ema20<ema50 and not pb_up: counter.append("short-term value structure opposes upside thesis")
        if regime=="TREND" and not bull: counter.append("bullish swing sequence is not fully established")
        if rej_up: counter.append("upside auction shows rejection")
    elif direction=="DOWN":
        if ema20>ema50 and not pb_dn: counter.append("short-term value structure opposes downside thesis")
        if regime=="TREND" and not bear: counter.append("bearish swing sequence is not fully established")
        if rej_dn: counter.append("downside auction shows rejection")
    if direction!= "NEUTRAL" and not space_ok: counter.append("opposing liquidity is too close")
    if overextended: counter.append("price is materially extended")
    if opportunity=="TREND_PULLBACK_CONTINUATION":
        if not (pb_up or pb_dn): missing.append("controlled pullback with directional holding/rejection")
        missing.append("follow-through after pullback")
    elif opportunity=="TREND_CONTINUATION": missing.append("fresh acceptance/displacement and follow-through")
    elif opportunity=="BREAKOUT_CONTINUATION":
        if not expanding: missing.append("volatility expansion and sustained acceptance")
        missing.append("follow-through beyond broken range")
    elif opportunity=="LIQUIDITY_REVERSAL": missing.append("rejection must hold and rotate into value")
    elif opportunity=="WAIT_FOR_RANGE_EDGE": missing.append("meaningful range-edge interaction and rejection")
    else: missing.append("clear directional commitment / repricing")
    if direction=="UP" and rej_up and pos>=.80: invalid.append("upside acceptance failed at a high-value area")
    if direction=="DOWN" and rej_dn and pos<=.20: invalid.append("downside acceptance failed at a low-value area")
    if direction=="UP" and down>=up+2: invalid.append("independent downside evidence dominates")
    if direction=="DOWN" and up>=down+2: invalid.append("independent upside evidence dominates")

    e1r=_e1(snapshot); e1dir=_direction(e1r.get("directional_pressure") or e1r.get("direction")); e1state=str(e1r.get("market_state") or e1r.get("state") or "UNRESOLVED").upper(); alignment="INCONCLUSIVE" if direction=="NEUTRAL" or e1dir=="NEUTRAL" else "ALIGNED" if direction==e1dir else "CONFLICT"
    if alignment=="CONFLICT": counter.append("E1 conflicts with independent E2 thesis")
    bq=float(best["quality"]) if best else 0.0; strength=max(up,down)/7.0; confidence=max(0.0,min(1.0,.50*bq+.30*strength+.20-min(.45,.08*len(counter))-min(.25,.06*len(missing))+(0.04 if alignment=="ALIGNED" else -0.04 if alignment=="CONFLICT" else 0.0))); score=max(0.0,min(1.0,.68*bq+.32*confidence))
    if invalid: maturity,state,quality="INVALIDATED","INVALIDATED","REJECTED"
    elif direction=="NEUTRAL": maturity,state,quality="WAITING","WAIT","UNPROVEN"
    elif counter or missing: maturity,state,quality="DEVELOPING","DEVELOPING","STRONG_CONTEXT" if score>=.70 else "DEVELOPING"
    else: maturity,state,quality="MATURE_CONTEXT","CONTEXT_READY","STRONG" if score>=.78 else "DEVELOPING"
    timing="MISSED" if invalid else "WAIT" if direction=="NEUTRAL" else "LATE" if overextended else "READY_FOR_CONFIRMATION" if missing else "DEVELOPING"; oq="HIGH" if score>=.78 and not counter else "MEDIUM" if score>=.55 else "LOW"; aq="CONFIRMED" if acc_up or acc_dn else "STRONG" if disp_up or disp_dn else "UNPROVEN"
    if invalid or direction=="NEUTRAL": decision,edge=("NO_OPPORTUNITY","NO_EDGE") if invalid else ("WAIT","NO_EDGE")
    elif overextended or not space_ok or counter or missing: decision,edge="WATCH","EDGE_CONDITIONAL"
    elif score>=.72: decision,edge="ACTIONABLE_BIAS","EDGE_PRESENT"
    else: decision,edge="WATCH","EDGE_CONDITIONAL"

    # Branch map is a market-state forecast, not a trade trigger.
    paths=[]
    if direction!="NEUTRAL":
        paths.append({"if":"supporting structure + acceptance/holding persist","then":f"{direction}_THESIS_STRENGTHENS","status":"FAVORABLE"})
        paths.append({"if":"opposing structure becomes dominant","then":"CURRENT_THESIS_INVALIDATED","status":"INVALIDATION"})
    if regime in {"RANGE","TRANSITION"}:
        paths += [{"if":"price reaches a favorable range edge and rejection holds","then":"RANGE_ROTATION_OPPORTUNITY_DEVELOPS","status":"WATCH"},{"if":"price accepts beyond the range boundary with expansion","then":"BREAKOUT_REPRICING_OPPORTUNITY_DEVELOPS","status":"WATCH"}]
    if rej_up and pos>=.70: paths.append({"if":"high rejection holds and price returns into value","then":"DOWN_REVERSAL_OPPORTUNITY_DEVELOPS","status":"WATCH"})
    if rej_dn and pos<=.30: paths.append({"if":"low rejection holds and price returns into value","then":"UP_REVERSAL_OPPORTUNITY_DEVELOPS","status":"WATCH"})

    why=[]
    if direction=="NEUTRAL": why.append("no decisive directional opportunity is established")
    if ambiguity: why.append("competing hypotheses are too close")
    if overextended: why.append("late location: price is materially extended")
    if direction!="NEUTRAL" and not space_ok: why.append("insufficient opposing space")
    why += [f"missing: {x}" for x in missing]+[f"counter-evidence: {x}" for x in counter]+[f"invalidated: {x}" for x in invalid]
    if not why: why.append("E2 provides context only; downstream engines validate confirmation and economics")
    counterfactual=["if supporting structure fails and opposing evidence dominates, abandon the current thesis"] if direction in {"UP","DOWN"} else ["if one side gains sustained acceptance and follow-through, replace neutrality with that directional thesis"]
    expected={"TREND_PULLBACK_CONTINUATION":"impulse -> controlled pullback -> holding/rejection -> confirmation -> continuation","TREND_CONTINUATION":"directional pressure -> acceptance/displacement -> confirmation -> follow-through","BREAKOUT_CONTINUATION":"breakout -> acceptance -> expansion -> follow-through","LIQUIDITY_REVERSAL":"liquidity sweep -> rejection holds -> return into value -> reversal follow-through","WAIT_FOR_RANGE_EDGE":"range edge -> rejection/acceptance decision -> rotation or breakout","WAIT_FOR_REPRICING":"clear commitment -> acceptance -> follow-through"}.get(opportunity,"repricing -> commitment -> maturity")
    summary=[{"name":x["name"],"direction":x["direction"],"quality":round(x["quality"],4),"space_atr":round(x["space_atr"],4),"eligible":x["eligible"],"vetoes":x["vetoes"]} for x in candidates[:8]]
    observations=[f"ema_gap_atr={gap:.3f}",f"ema20_slope_atr={s20:.3f}",f"ema50_slope_atr={s50:.3f}",f"slope5_atr={slope5:.3f}",f"slope20_atr={slope20:.3f}",f"volatility_ratio={vr:.3f}",f"efficiency12={eff:.3f}",f"up_evidence={up}/7",f"down_evidence={down}/7",f"position_40={pos:.3f}",f"position_20={pos20:.3f}",f"opposing_space_atr={space:.3f}",f"auction_intent={intent}",f"eligible_candidates={len(eligible)}",f"vetoed_candidates={len(vetoed)}"]
    thesis=f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {phase}; thesis is {maturity.lower()} and requires downstream confirmation."
    reasoning={"question":QUESTION,"conclusion":thesis,"why_now":f"{auction}; intent={intent}; {location}; opposing space={space:.2f} ATR","expected_path":expected,"required_evidence":list(dict.fromkeys(missing)),"invalidation_conditions":invalid or ["opposing structure becomes dominant","auction invalidates expected path"],"timing":timing,"opportunity_quality":oq,"opportunity_decision":decision,"edge_assessment":edge,"candidate_comparison":summary,"conditional_paths":paths,"counter_evidence_count":len(counter),"counter_evidence":counter,"why_not_trade":why,"counterfactual":counterfactual,"independent_thesis":True,"e1_used_as":"CROSS_CHECK_ONLY","entry_authorized":False}
    codes=[]
    if invalid: codes.append("THESIS_INVALIDATED")
    if alignment=="CONFLICT": codes.append("E1_E2_DIRECTION_CONFLICT")
    if ambiguity: codes.append("COMPETING_HYPOTHESES")
    if missing: codes.append("MISSING_OPPORTUNITY_CONFIRMATION")
    if counter: codes.append("COUNTER_EVIDENCE_PRESENT")
    if vetoed: codes.append("HARD_VETO_PRESENT")
    if paths: codes.append("CONDITIONAL_OPPORTUNITY_MAP")
    if not codes: codes.append("NO_ACTIONABLE_OPPORTUNITY")
    return {"state":"OPPORTUNITY_ANALYSIS_COMPLETE","architecture":ARCHITECTURE,"sub_engines_active":False,"reasoning_mode":"SINGLE_PROFESSIONAL_CORE","question":QUESTION,"thesis":thesis,"regime":regime,"direction":direction,"phase":phase,"opportunity":opportunity,"opportunity_state":state,"opportunity_maturity":maturity,"quality":quality,"opportunity_quality":oq,"opportunity_score":round(score,4),"opportunity_decision":decision,"edge_assessment":edge,"alignment_with_e1":alignment,"independence":"E2_FIRST_E1_CROSS_CHECK","auction_state":auction,"auction_phase":"ACCEPTANCE" if "ACCEPTANCE" in auction else "REJECTION" if "FAILED_AUCTION" in auction else "BALANCE" if "BALANCED" in auction else "REPRICING" if direction!="NEUTRAL" else "TRANSITION","auction_intent":intent,"acceptance_quality":aq,"location_context":location,"regime_confidence":round(strength,4),"confidence":round(confidence,4),"timing_state":timing,"decision_factors":[f"independent_regime={regime}",f"independent_direction={direction}",f"auction_intent={intent}",f"auction_state={auction}",f"opportunity={opportunity}",f"phase={phase}",f"location={location}",f"opportunity_score={score:.3f}",f"decision={decision}"],"observations":observations,"evidence":[f"UP_EVIDENCE={up}/7",f"DOWN_EVIDENCE={down}/7",f"STRUCTURE_BULL={bull}",f"STRUCTURE_BEAR={bear}",f"ACCEPTANCE_UP={acc_up}",f"ACCEPTANCE_DOWN={acc_dn}",f"REJECTION_UP={rej_up}",f"REJECTION_DOWN={rej_dn}",f"EXPANSION={expanding}",f"COMPRESSION={compressed}",f"SPACE_OK={space_ok}",f"E1_STATE={e1state}"],"candidate_comparison":summary,"conditional_opportunity_map":paths,"evidence_map":{"directional_pressure":direction,"location":location,"regime":regime,"auction_state":auction,"auction_intent":intent,"space_ok":space_ok,"overextended":overextended,"alignment_with_e1":alignment,"hypothesis_ambiguity":ambiguity},"counter_evidence":counter,"counter_evidence_severity":"THESIS_INVALIDATION" if invalid else "MATERIAL" if counter else "NONE","missing_evidence":missing,"invalidation_evidence":invalid,"why_not_trade":why,"counterfactual":counterfactual,"opposing_space_atr":round(space,4),"invalidation_distance_atr":round(invalid_dist,4),"decision":None,"entry":None,"trigger":None,"risk":None,"gate":None,"trade_decision_authority":"E9_ONLY","professional_reasoning":reasoning,"reason_codes":list(dict.fromkeys(codes))}
