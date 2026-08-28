from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V4"


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    bars = snapshot.get("bars") or []
    return [b for b in bars if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2: return 0.0
    trs=[]; prev=float(bars[0]["close"])
    for b in bars[-period:]:
        h,l,c=map(float,(b["high"],b["low"],b["close"]))
        trs.append(max(h-l,abs(h-prev),abs(l-prev))); prev=c
    return mean(trs) if trs else 0.0


def _ema(values: list[float], period: int) -> float:
    if not values: return 0.0
    a=2.0/(period+1.0); v=values[0]
    for x in values[1:]: v=a*x+(1-a)*v
    return v


def _pivots(bars: list[dict[str, Any]], wing: int=2):
    highs=[]; lows=[]
    for i in range(wing,len(bars)-wing):
        w=bars[i-wing:i+wing+1]; hi=float(bars[i]["high"]); lo=float(bars[i]["low"])
        if hi>=max(float(x["high"]) for x in w): highs.append(hi)
        if lo<=min(float(x["low"]) for x in w): lows.append(lo)
    return highs,lows


def _unavailable() -> dict[str,Any]:
    return {"role":"OPPORTUNITY_REGIME_ANALYST","question":QUESTION,"finding":"INSUFFICIENT_DATA","state":"UNAVAILABLE","regime":"UNRESOLVED","direction":"NEUTRAL","opportunity":"NONE","opportunity_state":"WAIT","opportunity_maturity":"UNPROVEN","independence":"E2_FIRST_E1_CROSS_CHECK","auction_intent":"UNKNOWN","conditional_map":[],"opportunity_hierarchy":{},"hard_veto":["INSUFFICIENT_MARKET_DATA"],"requires_downstream_confirmation":True,"entry":None,"decision":None,"reasons":["INSUFFICIENT_MARKET_DATA"]}


def analyze_e2(snapshot: dict[str,Any]) -> dict[str,Any]:
    """Independent E2 opportunity brain. E1 is cross-check only; E2 never issues entry/final decisions."""
    bs=_bars(snapshot)
    if len(bs)<MIN_BARS: return _unavailable()
    h=[float(b["high"]) for b in bs]; l=[float(b["low"]) for b in bs]; c=[float(b["close"]) for b in bs]; o=[float(b["open"]) for b in bs]
    atr=max(_atr(bs),1e-12); last=c[-1]; e20=_ema(c,20); e50=_ema(c,50); gap=(e20-e50)/atr
    e20p=_ema(c[:-5],20); e50p=_ema(c[:-5],50); s20=(e20-e20p)/atr; s50=(e50-e50p)/atr; slope5=(c[-1]-c[-6])/atr; slope20=(c[-1]-c[-21])/atr
    ranges=[max(float(b["high"])-float(b["low"]),0) for b in bs]; avg20=max(mean(ranges[-20:]),1e-12); vr=mean(ranges[-5:])/avg20
    travel=max(sum(ranges[-12:]),1e-12); eff=abs(c[-1]-c[-13])/travel
    hi20,lo20=max(h[-21:-1]),min(l[-21:-1]); hi40,lo40=max(h[-41:-1]),min(l[-41:-1]); width=max(hi40-lo40,1e-12); pos=max(0,min(1,(last-lo40)/width))
    ph,pl=_pivots(bs); hh=len(ph)>=2 and ph[-1]>ph[-2]; lh=len(ph)>=2 and ph[-1]<ph[-2]; hl=len(pl)>=2 and pl[-1]>pl[-2]; ll=len(pl)>=2 and pl[-1]<pl[-2]
    bull=hh and hl; bear=lh and ll
    up=sum((gap>.35,s20>.08,s50>-.05,slope5>.20,slope20>.45,bull,eff>=.30)); down=sum((gap<-.35,s20<-.08,s50<.05,slope5<-.20,slope20<-.45,bear,eff>=.30))
    span=max(h[-1]-l[-1],1e-12); body=abs(last-o[-1])/span; cp=(last-l[-1])/span; uw=(h[-1]-max(o[-1],last))/span; lw=(min(o[-1],last)-l[-1])/span
    broke_up,broke_dn=last>hi20,last<lo20; sweep_up=h[-1]>hi20 and last<=hi20; sweep_dn=l[-1]<lo20 and last>=lo20
    acc_up=broke_up and cp>=.65 and body>=.45; acc_dn=broke_dn and cp<=.35 and body>=.45; rej_up=sweep_up and cp<=.45 and uw>=.20; rej_dn=sweep_dn and cp>=.55 and lw>=.20
    disp_up=body>=.60 and cp>=.75 and span>=1.25*avg20; disp_dn=body>=.60 and cp<=.25 and span>=1.25*avg20
    balanced=abs(slope20)<.65 and eff<.30 and width/atr<8.5

    # Auction intent: initiative is not control until displacement + follow-through agree.
    follow_up=int(sum(x>0 for x in [c[-1]-c[-2],c[-2]-c[-3],c[-3]-c[-4]])); follow_dn=int(sum(x<0 for x in [c[-1]-c[-2],c[-2]-c[-3],c[-3]-c[-4]]))
    net5=(last-c[-5])/atr
    if acc_up and follow_up>=2: auction_intent="BUY_SIDE_ACCEPTANCE"
    elif acc_dn and follow_dn>=2: auction_intent="SELL_SIDE_ACCEPTANCE"
    elif rej_up: auction_intent="FAILED_HIGH_AUCTION"
    elif rej_dn: auction_intent="FAILED_LOW_AUCTION"
    elif up>=5 and net5>.50: auction_intent="BUYER_INITIATIVE_PENDING_ACCEPTANCE"
    elif down>=5 and net5<-.50: auction_intent="SELLER_INITIATIVE_PENDING_ACCEPTANCE"
    elif balanced: auction_intent="TWO_SIDED_BALANCE"
    else: auction_intent="UNCOMMITTED_AUCTION"

    candidates=[]
    def add(name,direction,regime,structure,acceptance=False,rejection=False,pullback=False,displacement=False):
        space=max((hi40-last)/atr,0) if direction=="UP" else max((last-lo40)/atr,0); loc=(.10<=pos<=.75) if direction=="UP" else (.25<=pos<=.90); extended=(pos>=.92 if direction=="UP" else pos<=.08)
        veto=[]
        if not loc: veto.append("LOCATION_NOT_ADVANTAGEOUS")
        if space<1.0: veto.append("INSUFFICIENT_OPPOSING_SPACE")
        if extended: veto.append("OVEREXTENDED_LOCATION")
        if name=="BREAKOUT_CONTINUATION" and not acceptance: veto.append("NO_ACCEPTANCE")
        if rejection and ((direction=="UP" and pos>=.70) or (direction=="DOWN" and pos<=.30)): veto.append("FAILED_AUCTION")
        structure_score=1 if structure else 0; q=max(0,min(1,.22*structure_score+.20*float(acceptance or displacement)+.18*float(pullback)+.14*float(loc)+.14*min(space/3,1)+.12*min(eff/.55,1)-.18*float(rejection)-.18*float(extended)))
        candidates.append({"name":name,"direction":direction,"regime":regime,"quality":q,"space_atr":space,"vetoes":veto,"eligible":not veto,"structure":structure,"acceptance":acceptance,"pullback":pullback,"rejection":rejection,"displacement":displacement})
    if up>=4: add("TREND_PULLBACK_CONTINUATION","UP","TREND",bull,False,rej_up,False,disp_up)
    if down>=4: add("TREND_PULLBACK_CONTINUATION","DOWN","TREND",bear,False,rej_dn,False,disp_dn)
    if acc_up: add("BREAKOUT_CONTINUATION","UP","BREAKOUT",bull,True,rej_up,False,disp_up)
    if acc_dn: add("BREAKOUT_CONTINUATION","DOWN","BREAKOUT",bear,True,rej_dn,False,disp_dn)
    if rej_dn and pos<=.30: add("LIQUIDITY_REVERSAL","UP","MEAN_REVERSION",bull,False,True,False,disp_up)
    if rej_up and pos>=.70: add("LIQUIDITY_REVERSAL","DOWN","MEAN_REVERSION",bear,False,True,False,disp_dn)
    eligible=sorted((x for x in candidates if x["eligible"]),key=lambda x:(x["quality"],x["space_atr"]),reverse=True); best=eligible[0] if eligible else None; second=eligible[1] if len(eligible)>1 else None
    competing=bool(best and second and best["direction"]!=second["direction"] and abs(best["quality"]-second["quality"])<.12)
    direction=best["direction"] if best and not competing else "NEUTRAL"; regime=best["regime"] if best and not competing else ("RANGE" if balanced else "TRANSITION")
    opportunity=best["name"] if best and not competing else ("WAIT_FOR_RANGE_EDGE" if regime=="RANGE" else "WAIT_FOR_REPRICING")
    phase="ACCEPTANCE" if best and best["acceptance"] else "REJECTION" if best and best["rejection"] else "DEVELOPING" if best else "BALANCED"
    space=max((hi40-last)/atr,0) if direction=="UP" else max((last-lo40)/atr,0) if direction=="DOWN" else 0
    veto=[]
    if competing: veto.append("COMPETING_HYPOTHESES")
    if best is None: veto.append("NO_ELIGIBLE_OPPORTUNITY")
    if direction=="DOWN" and pos<=.12 and space<.5: veto.append("SHORT_CHASE_AT_DISCOUNT_WITH_NO_SPACE")
    if direction=="UP" and pos>=.88 and space<.5: veto.append("LONG_CHASE_AT_PREMIUM_WITH_NO_SPACE")
    if auction_intent in {"UNCOMMITTED_AUCTION","BUYER_INITIATIVE_PENDING_ACCEPTANCE","SELLER_INITIATIVE_PENDING_ACCEPTANCE"}: veto.append("AUCTION_ACCEPTANCE_NOT_PROVEN")
    paths=[]
    if direction=="UP": paths += ["IF pullback holds + buyer acceptance returns -> upside continuation strengthens","IF opposing structure wins -> bullish thesis invalidated"]
    elif direction=="DOWN": paths += ["IF pullback holds + seller acceptance returns -> downside continuation strengthens","IF opposing structure wins -> bearish thesis invalidated"]
    else: paths += ["IF directional evidence converges -> thesis strengthens","IF counter-evidence dominates -> remain neutral"]
    paths += ["IF range edge rejects -> rotation develops","IF range break + acceptance -> breakout repricing develops"]
    if auction_intent=="FAILED_HIGH_AUCTION": paths.append("IF rejection receives downside follow-through -> short-side reversal opportunity strengthens")
    if auction_intent=="FAILED_LOW_AUCTION": paths.append("IF rejection receives upside follow-through -> long-side reversal opportunity strengthens")
    hierarchy={"primary":opportunity,"secondary":("LIQUIDITY_REVERSAL" if "FAILED" in auction_intent else "BREAKOUT_REPRICING"),"alternative":"RANGE_ROTATION","invalidation":"opposing structure wins or auction acceptance fails","no_trade_when":veto or ["downstream confirmation absent"]}
    counter=[]
    e1=snapshot.get("E1_result") or {}; e1f=str(e1.get("finding","")).upper()
    if e1f and direction!="NEUTRAL" and direction not in e1f and "TRANSITION" not in e1f: counter.append("E1_COUNTER_EVIDENCE_RETAINED_NOT_OVERRIDDEN")
    reasons=(['HARD_VETO_PRESENT'] if veto else [])+(["COUNTER_EVIDENCE_PRESENT"] if counter else [])+["CONDITIONAL_OPPORTUNITY_MAP","INDEPENDENT_THESIS"]
    return {"role":"OPPORTUNITY_REGIME_ANALYST","question":QUESTION,"finding":f"Independent E2 thesis: {regime}/{direction} creates {opportunity} at {phase}; thesis is conditional and requires downstream confirmation.","state":"ANALYSIS_COMPLETE","regime":regime,"direction":direction,"phase":phase,"opportunity":opportunity,"opportunity_state":"WAIT" if veto else "DEVELOPING","opportunity_maturity":"CONDITIONAL" if best else "UNPROVEN","quality":"CONDITIONAL","opportunity_quality":round(best["quality"],3) if best else 0.0,"opportunity_decision":"WAIT","edge_assessment":"ASYMMETRIC" if best and best["space_atr"]>=1.5 and not veto else "NO_EDGE","alignment_with_e1":"COUNTER_EVIDENCE" if counter else "INCONCLUSIVE","independence":"E2_FIRST_E1_CROSS_CHECK","auction_state":"ACCEPTED" if "ACCEPTANCE" in auction_intent else "FAILED" if "FAILED" in auction_intent else "UNRESOLVED","auction_intent":auction_intent,"auction_phase":"ACCEPTANCE" if "ACCEPTANCE" in auction_intent else "REJECTION" if "FAILED" in auction_intent else "INITIATIVE_PENDING","location_context":"EDGE_LOW" if pos<=.20 else "EDGE_HIGH" if pos>=.80 else "MID_RANGE","regime_confidence":round(max(up,down)/7,3),"confidence":round(best["quality"],3) if best else 0.0,"opportunity_score":round(best["quality"],3) if best else 0.0,"decision_factors":[f"up_evidence={up}/7",f"down_evidence={down}/7",f"efficiency12={eff:.3f}",f"volatility_ratio={vr:.3f}",f"position_40={pos:.3f}",f"opposing_space_atr={space:.3f}"],"counter_evidence":counter+(["auction acceptance not yet proven"] if "PENDING" in auction_intent else []),"counter_evidence_severity":"HIGH" if veto else "MODERATE","missing_evidence":["closed-candle acceptance/follow-through"],"invalidation_evidence":["opposing structure wins","auction thesis fails to receive follow-through"],"why_not_trade":hierarchy["no_trade_when"],"conditional_map":paths,"opportunity_hierarchy":hierarchy,"hard_veto":veto,"requires_downstream_confirmation":True,"entry":None,"trigger":None,"decision":None,"professional_reasoning":{"question":QUESTION,"conclusion":"WAIT_UNTIL_OPPORTUNITY_PROVES_ITSELF" if veto else "CONDITIONAL_OPPORTUNITY","why_now":f"Auction intent={auction_intent}; opportunity={opportunity}.","expected_path":paths,"required_evidence":["acceptance or rejection follow-through","opposing-space remains adequate","thesis remains structurally valid"],"invalidation_conditions":["opposing structure wins","auction acceptance fails","opposing space disappears"],"timing":"WAIT","independent_thesis":True,"e1_used_as":"CROSS_CHECK_ONLY","entry_authorized":False}}
