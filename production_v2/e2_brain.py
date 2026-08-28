from __future__ import annotations
from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V7"


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in (snapshot.get("bars") or []) if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _ema(v: list[float], p: int) -> float:
    if not v: return 0.0
    a = 2.0 / (p + 1.0); x = v[0]
    for y in v[1:]: x = a * y + (1-a) * x
    return x


def _atr(bars: list[dict[str, Any]], p: int = 14) -> float:
    if len(bars) < 2: return 0.0
    start = max(1, len(bars)-p); trs=[]
    for i in range(start, len(bars)):
        h,l = float(bars[i]["high"]), float(bars[i]["low"]); pc=float(bars[i-1]["close"])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return mean(trs) if trs else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    hs=[]; ls=[]
    for i in range(wing, len(bars)-wing):
        w=bars[i-wing:i+wing+1]; h=float(bars[i]["high"]); l=float(bars[i]["low"])
        if h >= max(float(x["high"]) for x in w): hs.append(h)
        if l <= min(float(x["low"]) for x in w): ls.append(l)
    return hs,ls


def _unavailable() -> dict[str, Any]:
    return {"role":"OPPORTUNITY_REGIME_ANALYST","question":QUESTION,"finding":"INSUFFICIENT_DATA","state":"UNAVAILABLE","regime":"UNRESOLVED","direction":"NEUTRAL","opportunity":"NONE","opportunity_state":"WAIT","opportunity_maturity":"UNPROVEN","independence":"E2_INDEPENDENT_E1_CROSS_CHECK","reasoning_mode":"PROFESSIONAL_DISCRETIONARY","trade_decision_authority":"NONE","auction_intent":"UNKNOWN","auction_intent_detail":{},"opportunity_taxonomy":["TREND_CONTINUATION","PULLBACK_CONTINUATION","RANGE_ROTATION","BREAKOUT_REPRICING","LIQUIDITY_REVERSAL","NO_OPPORTUNITY"],"opportunity_hierarchy":{"primary":None,"secondary":[],"rejected":[],"ranked":[]},"primary_thesis":"NEUTRAL_NO_OPPORTUNITY_UNPROVEN","counter_evidence":["INSUFFICIENT_MARKET_DATA"],"invalidation":["DATA_INSUFFICIENT"],"hard_veto":["INSUFFICIENT_MARKET_DATA"],"asymmetric_opportunity":{"directional_space_atr":0.0,"path_quality":0.0,"is_asymmetric":False},"location":{},"opposing_space":{},"conditional_map":[{"if":"IF sufficient closed-candle market data becomes available","then":"THEN rebuild the opportunity map"}],"market_tree":{},"professional_reasoning":{"question":"What is the market offering, not what do I want it to do?","context_vs_trade_decision":"E2 maps opportunity only; it never authorizes entry."},"no_trade_reasoning":["WAIT_FOR_VALID_MARKET_INFORMATION"],"requires_downstream_confirmation":True,"entry":None,"decision":None,"reasons":["INSUFFICIENT_MARKET_DATA"],"observations":[]}


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Independent opportunity brain. E1 is read-only counter-evidence; E2 never issues entry/final decisions."""
    bars=_bars(snapshot)
    if len(bars)<MIN_BARS: return _unavailable()
    hs=[float(b["high"]) for b in bars]; ls=[float(b["low"]) for b in bars]; cs=[float(b["close"]) for b in bars]; os=[float(b["open"]) for b in bars]
    atr=max(_atr(bars),1e-12); last=cs[-1]
    e20,e50=_ema(cs,20),_ema(cs,50); e20p,e50p=_ema(cs[:-5],20),_ema(cs[:-5],50)
    gap=(e20-e50)/atr; s20=(e20-e20p)/atr; s50=(e50-e50p)/atr; s5=(last-cs[-6])/atr; s20p=(last-cs[-21])/atr
    rng=[max(float(b["high"])-float(b["low"]),0.0) for b in bars]; avg20=max(mean(rng[-20:]),1e-12); vr=mean(rng[-5:])/avg20
    travel=max(sum(rng[-12:]),1e-12); eff=abs(last-cs[-13])/travel
    hi20,lo20=max(hs[-21:-1]),min(ls[-21:-1]); hi40,lo40=max(hs[-41:-1]),min(ls[-41:-1]); width=max(hi40-lo40,1e-12); pos=max(0,min(1,(last-lo40)/width))
    ph,pl=_pivots(bars); hh=len(ph)>=2 and ph[-1]>ph[-2]; lh=len(ph)>=2 and ph[-1]<ph[-2]; hl=len(pl)>=2 and pl[-1]>pl[-2]; ll=len(pl)>=2 and pl[-1]<pl[-2]
    bull=hh and hl; bear=lh and ll
    up={"ema_gap":gap>.35,"ema20_slope":s20>.08,"ema50_slope":s50>-.05,"short_slope":s5>.20,"medium_slope":s20p>.45,"structure":bull,"efficiency":eff>=.30}
    dn={"ema_gap":gap<-.35,"ema20_slope":s20<-.08,"ema50_slope":s50<.05,"short_slope":s5<-.20,"medium_slope":s20p<-.45,"structure":bear,"efficiency":eff>=.30}
    uc,dc=sum(up.values()),sum(dn.values())
    span=max(hs[-1]-ls[-1],1e-12); body=abs(last-os[-1])/span; cp=(last-ls[-1])/span; uw=(hs[-1]-max(os[-1],last))/span; lw=(min(os[-1],last)-ls[-1])/span
    broke_up,broke_dn=last>hi20,last<lo20; sweep_hi=hs[-1]>hi20 and last<=hi20; sweep_lo=ls[-1]<lo20 and last>=lo20
    accept_up=broke_up and cp>=.65 and body>=.45; accept_dn=broke_dn and cp<=.35 and body>=.45
    reject_hi=sweep_hi and cp<=.45 and uw>=.20; reject_lo=sweep_lo and cp>=.55 and lw>=.20
    disp_up=body>=.60 and cp>=.75 and span>=1.25*avg20; disp_dn=body>=.60 and cp<=.25 and span>=1.25*avg20
    balanced=abs(s20p)<.65 and eff<.30 and width/atr<8.5
    follow=[cs[-i]-cs[-i-1] for i in range(1,4)]; fu=sum(x>0 for x in follow); fd=sum(x<0 for x in follow); net5=(last-cs[-5])/atr
    prior=max(cs[-11:-5])-min(cs[-11:-5])
    pb_up=gap>.20 and s20>.25 and prior>=.90*atr and -.80<=net5<=.15 and pos<.80
    pb_dn=gap<-.20 and s20<-.25 and prior>=.90*atr and -.15<=net5<=.80 and pos>.20
    if accept_up and fu>=2: intent,phase,strength="BUY_SIDE_ACCEPTANCE","ACCEPTANCE","HIGH"
    elif accept_dn and fd>=2: intent,phase,strength="SELL_SIDE_ACCEPTANCE","ACCEPTANCE","HIGH"
    elif reject_hi: intent,phase,strength="FAILED_HIGH_AUCTION","REJECTION","MODERATE"
    elif reject_lo: intent,phase,strength="FAILED_LOW_AUCTION","REJECTION","MODERATE"
    elif uc>=5 and net5>.50: intent,phase,strength="BUYER_INITIATIVE_PENDING_ACCEPTANCE","INITIATIVE","MODERATE"
    elif dc>=5 and net5<-.50: intent,phase,strength="SELLER_INITIATIVE_PENDING_ACCEPTANCE","INITIATIVE","MODERATE"
    elif balanced: intent,phase,strength="TWO_SIDED_BALANCE","BALANCE","LOW"
    else: intent,phase,strength="UNCOMMITTED_AUCTION","UNRESOLVED","LOW"
    intent_reason={"BUY_SIDE_ACCEPTANCE":"buyers achieved acceptance outside prior range","SELL_SIDE_ACCEPTANCE":"sellers achieved acceptance outside prior range","FAILED_HIGH_AUCTION":"high was explored then rejected","FAILED_LOW_AUCTION":"low was explored then rejected","BUYER_INITIATIVE_PENDING_ACCEPTANCE":"buyers show initiative without proven acceptance","SELLER_INITIATIVE_PENDING_ACCEPTANCE":"sellers show initiative without proven acceptance","TWO_SIDED_BALANCE":"auction remains rotational","UNCOMMITTED_AUCTION":"neither side has durable acceptance"}[intent]

    def cand(name,direction,regime,structure,acceptance=False,rejection=False,pullback=False,displacement=False):
        space=max((hi40-last)/atr,0) if direction=="UP" else max((last-lo40)/atr,0); loc=.10<=pos<=.75 if direction=="UP" else .25<=pos<=.90
        ext=pos>=.92 if direction=="UP" else pos<=.08; veto=[]
        if not loc:veto.append("LOCATION_NOT_ADVANTAGEOUS")
        if space<1.0:veto.append("INSUFFICIENT_OPPOSING_SPACE")
        if ext:veto.append("OVEREXTENDED_LOCATION")
        if name=="BREAKOUT_REPRICING" and not acceptance:veto.append("NO_ACCEPTANCE")
        if name=="PULLBACK_CONTINUATION" and not pullback:veto.append("NO_PULLBACK_STRUCTURE")
        if name=="LIQUIDITY_REVERSAL" and not rejection:veto.append("NO_LIQUIDITY_REJECTION")
        q=max(0,min(1,.18*float(structure)+.18*float(acceptance)+.16*float(pullback)+.16*float(rejection)+.12*float(displacement)+.10*float(loc)+.10*min(space/3,1)))
        return {"name":name,"direction":direction,"regime":regime,"quality":round(q,4),"space_atr":round(space,4),"location_ok":loc,"structure":structure,"acceptance":acceptance,"rejection":rejection,"pullback":pullback,"displacement":displacement,"vetoes":veto,"eligible":not veto}
    c=[]
    if uc>=4:c.append(cand("PULLBACK_CONTINUATION","UP","TREND",bull,pullback=pb_up,displacement=disp_up))
    if dc>=4:c.append(cand("PULLBACK_CONTINUATION","DOWN","TREND",bear,pullback=pb_dn,displacement=disp_dn))
    if accept_up:c.append(cand("BREAKOUT_REPRICING","UP","BREAKOUT",bull,acceptance=True,displacement=disp_up))
    if accept_dn:c.append(cand("BREAKOUT_REPRICING","DOWN","BREAKOUT",bear,acceptance=True,displacement=disp_dn))
    if reject_lo:c.append(cand("LIQUIDITY_REVERSAL","UP","REVERSAL",bull,rejection=True,displacement=disp_up))
    if reject_hi:c.append(cand("LIQUIDITY_REVERSAL","DOWN","REVERSAL",bear,rejection=True,displacement=disp_dn))
    if balanced and pos<=.35:c.append(cand("RANGE_ROTATION","UP","RANGE",True))
    if balanced and pos>=.65:c.append(cand("RANGE_ROTATION","DOWN","RANGE",True))
    ranked=sorted(c,key=lambda x:(x["quality"],x["space_atr"]),reverse=True); eligible=[x for x in ranked if x["eligible"]]
    competing=len(eligible)>=2 and eligible[0]["direction"]!=eligible[1]["direction"] and abs(eligible[0]["quality"]-eligible[1]["quality"])<.12
    hard=[]
    if not eligible: hard.append("NO_ELIGIBLE_OPPORTUNITY")
    if competing: hard.append("COMPETING_HYPOTHESES")
    if intent in {"UNCOMMITTED_AUCTION","BUYER_INITIATIVE_PENDING_ACCEPTANCE","SELLER_INITIATIVE_PENDING_ACCEPTANCE"}: hard.append("AUCTION_ACCEPTANCE_NOT_PROVEN")
    primary=eligible[0] if eligible and not competing else None
    direction=primary["direction"] if primary else "NEUTRAL"; regime=primary["regime"] if primary else ("RANGE" if balanced else "TRANSITION")
    opp=primary["name"] if primary else ("WAIT_FOR_RANGE_EDGE" if balanced else "WAIT_FOR_REPRICING")
    maturity="ACCEPTED" if primary and primary["acceptance"] else "REJECTED" if primary and primary["rejection"] else "DEVELOPING" if primary else "UNPROVEN"
    counter=[]; e1=snapshot.get("E1_result") or {}; ef=str(e1.get("finding","")).upper()
    if direction=="UP" and ("DOWN" in ef or "BEARISH" in ef):counter.append("E1_BEARISH_VIEW_IS_COUNTER_EVIDENCE_NOT_COMMAND")
    if direction=="DOWN" and ("UP" in ef or "BULLISH" in ef):counter.append("E1_BULLISH_VIEW_IS_COUNTER_EVIDENCE_NOT_COMMAND")
    if eff<.15: counter.append("LOW_AUCTION_EFFICIENCY")
    if direction=="UP" and reject_hi: counter.append("FAILED_HIGH_AUCTION_AGAINST_LONG_THESIS")
    if direction=="DOWN" and reject_lo: counter.append("FAILED_LOW_AUCTION_AGAINST_SHORT_THESIS")
    invalid=["IF_price_accepts_through_the_thesis_invalidation_level_THEN_thesis_invalidates"] if direction=="NEUTRAL" else (["IF_price_accepts_below_recent_support_THEN_bullish_thesis_invalidates"] if direction=="UP" else ["IF_price_accepts_above_recent_resistance_THEN_bearish_thesis_invalidates"])
    if primary and primary["name"]=="BREAKOUT_REPRICING": invalid.append("IF_breakout_returns_inside_prior_range_THEN_breakout_thesis_invalidates")
    if primary and primary["name"]=="LIQUIDITY_REVERSAL": invalid.append("IF_rejection_level_is_reclaimed_in_original_direction_THEN_reversal_thesis_invalidates")
    if direction=="UP": maps=[("IF buyers defend the pullback or reclaim","THEN bullish continuation path strengthens"),("IF price loses the defended area","THEN bullish path weakens"),("IF sellers gain confirmed acceptance below opposing structure","THEN bearish path becomes primary")]
    elif direction=="DOWN": maps=[("IF sellers defend the pullback or rejection","THEN bearish continuation path strengthens"),("IF price reclaims the defended area","THEN bearish path weakens"),("IF buyers gain confirmed acceptance above opposing structure","THEN bullish path becomes primary")]
    elif balanced: maps=[("IF range edge rejects","THEN range rotation develops"),("IF range edge fails","THEN rotation thesis weakens"),("IF range breaks and acceptance follows","THEN breakout repricing becomes primary")]
    else: maps=[("IF one side gains closed-candle acceptance","THEN directional opportunity develops"),("IF price remains two-sided and inefficient","THEN directional thesis remains unproven"),("IF the opposite side gains acceptance","THEN opportunity map flips")]
    conditional=[{"if":a,"then":b} for a,b in maps]
    no_trade=list(hard)
    if primary is None:no_trade.append("NO_PRIMARY_OPPORTUNITY_THESIS")
    no_trade.append("E2_HAS_NO_ENTRY_AUTHORITY")
    if primary and not primary["acceptance"] and primary["name"] in {"PULLBACK_CONTINUATION","BREAKOUT_REPRICING"}:no_trade.append("DOWNSTREAM_CONFIRMATION_REQUIRED")
    thesis=f"{direction}_{opp}_{maturity}" if direction!="NEUTRAL" else f"NEUTRAL_{opp}_UNPROVEN"
    return {"role":"OPPORTUNITY_REGIME_ANALYST","question":QUESTION,"finding":thesis,"state":"ANALYSIS_COMPLETE","regime":regime,"direction":direction,"opportunity":opp,"opportunity_state":"WAIT" if hard or primary is None else "DEVELOPING","opportunity_maturity":maturity,"independence":"E2_INDEPENDENT_E1_CROSS_CHECK","reasoning_mode":"PROFESSIONAL_DISCRETIONARY","trade_decision_authority":"NONE","auction_intent":intent,"auction_intent_detail":{"phase":phase,"strength":strength,"reason":intent_reason},"opportunity_taxonomy":["TREND_CONTINUATION","PULLBACK_CONTINUATION","RANGE_ROTATION","BREAKOUT_REPRICING","LIQUIDITY_REVERSAL","NO_OPPORTUNITY"],"opportunity_hierarchy":{"primary":primary,"secondary":eligible[1:3],"rejected":[x for x in ranked if not x["eligible"]],"ranked":ranked,"selection_rule":"HIERARCHY_THEN_HARD_VETO_THEN_DOWNSTREAM_CONFIRMATION"},"primary_thesis":thesis,"counter_evidence":counter,"invalidation":invalid,"hard_veto":hard,"asymmetric_opportunity":{"directional_space_atr":primary["space_atr"] if primary else 0.0,"location_position40":round(pos,4),"path_quality":primary["quality"] if primary else 0.0,"is_asymmetric":bool(primary and primary["space_atr"]>=1.5 and primary["location_ok"])},"location":{"position40":round(pos,4),"range_width_atr":round(width/atr,4),"value_zone":"DISCOUNT" if pos<.35 else "PREMIUM" if pos>.65 else "EQUILIBRIUM"},"opposing_space":{"up_atr":round(max((hi40-last)/atr,0),4),"down_atr":round(max((last-lo40)/atr,0),4)},"conditional_map":conditional,"market_tree":{"current_state":thesis,"strengthen":conditional[0]["then"],"weaken":conditional[1]["then"],"opposite":conditional[2]["then"]},"professional_reasoning":{"question":"What is the market offering, not what do I want it to do?","context_vs_trade_decision":"E2 maps opportunity/context only; E7/E8/E9 own confirmation, economics and final action.","competing_hypotheses":[x["name"]+":"+x["direction"] for x in eligible[:4]],"auction_intent_depth":intent_reason,"discretionary_rule":"Do not force a trade when auction intent, path, location, opposing space or invalidation is unclear."},"no_trade_reasoning":no_trade,"requires_downstream_confirmation":True,"entry":None,"decision":None,"reasons":["E2_INDEPENDENT_ANALYSIS",f"AUCTION_INTENT={intent}",f"OPPORTUNITY={opp}"]+[f"HARD_VETO={x}" for x in hard]+[f"COUNTER={x}" for x in counter],"observations":[f"atr14={atr:.8f}",f"ema_gap_atr={gap:.4f}",f"ema20_slope_atr={s20:.4f}",f"ema50_slope_atr={s50:.4f}",f"slope5_atr={s5:.4f}",f"slope20_atr={s20p:.4f}",f"volatility_ratio={vr:.4f}",f"efficiency12={eff:.4f}",f"up_evidence={uc}/7",f"down_evidence={dc}/7",f"position_40={pos:.4f}",f"opposing_space_atr={primary['space_atr'] if primary else 0.0:.4f}"]}
