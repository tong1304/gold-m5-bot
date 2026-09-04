from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What opportunity is the market offering right now?"
MIN_BARS = 80
ARCHITECTURE = "E2_PROFESSIONAL_OPPORTUNITY_CORE_V8"
MATURITY_ORDER = {"UNPROVEN": 0, "EMERGING": 1, "DEVELOPING": 2, "CONFIRMED": 3, "ACTIONABLE": 4}


def _text(v: Any) -> str:
    return str(v if v is not None else "").upper().strip()


def _dedupe(xs: list[Any]) -> list[str]:
    return list(dict.fromkeys(_text(x) for x in xs if _text(x)))


def _bars(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for b in (snapshot.get("bars") or []) if isinstance(b, dict) and all(k in b for k in ("open", "high", "low", "close"))]


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else default
    except (TypeError, ValueError):
        return default


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    a = 2.0 / (period + 1.0)
    out = values[0]
    for x in values[1:]:
        out = a * x + (1.0 - a) * out
    return out


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr: list[float] = []
    prev = _num(bars[0].get("close"))
    for b in bars[-period:]:
        h, l = _num(b.get("high")), _num(b.get("low"))
        tr.append(max(h - l, abs(h - prev), abs(l - prev)))
        prev = _num(b.get("close"))
    return mean(tr) if tr else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[float], list[float]]:
    hs, ls = [], []
    for i in range(wing, len(bars) - wing):
        h, l = _num(bars[i]["high"]), _num(bars[i]["low"])
        window = bars[i-wing:i+wing+1]
        if h >= max(_num(x["high"]) for x in window): hs.append(h)
        if l <= min(_num(x["low"]) for x in window): ls.append(l)
    return hs, ls


def _unavailable() -> dict[str, Any]:
    return {
        "role":"OPPORTUNITY_REGIME_ANALYST","question":QUESTION,"finding":"INSUFFICIENT_DATA","state":"UNAVAILABLE",
        "architecture":ARCHITECTURE,"regime":"UNRESOLVED","direction":"NEUTRAL","phase":"UNRESOLVED",
        "opportunity":"NONE","opportunity_state":"WAIT","opportunity_maturity":"UNPROVEN","independence":"E2_FIRST_E1_CROSS_CHECK",
        "auction_state":"UNKNOWN","auction_intent":"UNKNOWN","auction_intent_detail":{},"location_context":"UNKNOWN",
        "opposing_space_atr":0.0,"regime_confidence":0.0,"confidence":0.0,"opportunity_score":0.0,"candidate_hypotheses":[],
        "counter_evidence":[],"counter_evidence_severity":"HIGH","missing_evidence":["sufficient closed-candle market evidence"],
        "confirmation_required":["sufficient closed-candle market evidence"],"invalidation_evidence":[],"why_not_trade":["INSUFFICIENT_MARKET_DATA"],
        "conditional_map":[],"market_tree":{},"opportunity_hierarchy":{},"hard_veto":["INSUFFICIENT_MARKET_DATA"],
        "requires_downstream_confirmation":True,"opportunity_decision":"WAIT","entry":None,"trigger":None,"decision":None,
        "professional_reasoning":{"question":QUESTION,"thesis":"No thesis: insufficient data.","independent_thesis":True,"e1_used_as":"CROSS_CHECK_ONLY","entry_authorized":False},
        "reasoning_mode":"SINGLE_PROFESSIONAL_CORE","sub_engines_active":False,"gate":None,"timing_state":"WAIT",
        "reasons":["INSUFFICIENT_MARKET_DATA"],
    }


def _classify_opportunity(*, up: int, down: int, auction: str, balanced: bool, acceptance: bool, rejection: bool,
                          space_atr: float, location_ok: bool) -> dict[str, Any]:
    """Classify opportunity maturity without turning auction evidence into a trade thesis."""
    if up >= 5 and up - down >= 2:
        direction = "BUY"
    elif down >= 5 and down - up >= 2:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    # E2 may confirm the auction event, but it must not call the opportunity
    # itself CONFIRMED. Surviving causal thesis ownership belongs to E6.
    if acceptance and direction != "NEUTRAL":
        maturity, finding = "DEVELOPING", "AUCTION_ACCEPTANCE_CONFIRMED_OPPORTUNITY_DEVELOPING"
    elif rejection and direction != "NEUTRAL":
        maturity, finding = "DEVELOPING", "AUCTION_REJECTION_CONFIRMED_OPPORTUNITY_DEVELOPING"
    elif direction != "NEUTRAL":
        maturity, finding = "DEVELOPING", "CONDITIONAL_DIRECTIONAL_OPPORTUNITY"
    elif balanced:
        maturity, finding = "EMERGING", "BALANCED_AUCTION"
    else:
        maturity, finding = "UNPROVEN", "UNRESOLVED"

    missing, blockers = [], []
    if direction != "NEUTRAL" and not acceptance and not rejection:
        missing.append("closed-candle acceptance/follow-through proves the auction")
        blockers.append("AUCTION_CONFIRMATION_PENDING")
    if direction != "NEUTRAL" and not location_ok:
        missing.append("advantageous location")
        blockers.append("LOCATION_NOT_ADVANTAGEOUS")
    if direction != "NEUTRAL" and space_atr < 1.0:
        missing.append("adequate opposing space")
        blockers.append("INSUFFICIENT_OPPOSING_SPACE")
    if auction in {"UNCOMMITTED_AUCTION", "BUYER_INITIATIVE_PENDING_ACCEPTANCE", "SELLER_INITIATIVE_PENDING_ACCEPTANCE"}:
        blockers.append("AUCTION_ACCEPTANCE_NOT_PROVEN")
    if direction == "NEUTRAL":
        blockers.append("DIRECTIONAL_EDGE_NOT_ESTABLISHED")
    return {"direction":direction,"finding":finding,"opportunity_maturity":maturity,"missing_evidence":_dedupe(missing),"blockers":_dedupe(blockers)}


def _candidate(name: str, direction: str, structure: bool, acceptance: bool, rejection: bool, pullback: bool,
               displacement: bool, location_ok: bool, space_atr: float, auction: str, efficiency: float) -> dict[str, Any]:
    vetoes=[]
    if not structure: vetoes.append("STRUCTURE_NOT_ESTABLISHED")
    if not location_ok: vetoes.append("LOCATION_NOT_ADVANTAGEOUS")
    if space_atr < 1.0: vetoes.append("INSUFFICIENT_OPPOSING_SPACE")
    if name == "AUCTION_ACCEPTANCE_CONTINUATION" and not acceptance: vetoes.append("ACCEPTANCE_NOT_PROVEN")
    if name == "LIQUIDITY_REVERSAL" and not rejection: vetoes.append("FAILED_AUCTION_NOT_PROVEN")
    if name == "TREND_PULLBACK_CONTINUATION" and not pullback: vetoes.append("PULLBACK_NOT_ESTABLISHED")
    if name == "TREND_PULLBACK_CONTINUATION" and not (acceptance or displacement): vetoes.append("CONTINUATION_EVIDENCE_NOT_ESTABLISHED")
    quality = 0.22*structure + 0.22*acceptance + 0.18*rejection + 0.16*pullback + 0.10*displacement + 0.06*location_ok + 0.06*min(space_atr/3,1)
    return {"name":name,"direction":direction,"evidence_score":round(quality,3),"quality":round(quality,3),"space_atr":round(space_atr,3),
            "structure":structure,"acceptance":acceptance,"rejection":rejection,"pullback":pullback,"displacement":displacement,
            "location_ok":location_ok,"auction_intent":auction,"eligible":not vetoes,"vetoes":vetoes,"efficiency":round(efficiency,3)}


def _opportunity_blockers(*, direction: str, maturity: str, eligible: bool, base_blockers: list[str]) -> list[str]:
    """Separate a visible developing opportunity from absence of an opportunity path."""
    blockers = list(base_blockers)
    if direction in {"BUY", "SELL"} and not eligible:
        if maturity in {"DEVELOPING", "EMERGING", "CONFIRMED"}:
            blockers.append("NO_TRADEABLE_OPPORTUNITY_PATH_YET")
        else:
            blockers.append("NO_ELIGIBLE_OPPORTUNITY_PATH")
    return _dedupe(blockers)


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    bars = _bars(snapshot)
    if len(bars) < MIN_BARS: return _unavailable()
    closes=[_num(b["close"]) for b in bars]; highs=[_num(b["high"]) for b in bars]; lows=[_num(b["low"]) for b in bars]; opens=[_num(b["open"]) for b in bars]
    atr=max(_atr(bars),1e-12); last=closes[-1]
    e20,e50=_ema(closes,20),_ema(closes,50); prev20=_ema(closes[:-5],20); prev50=_ema(closes[:-5],50)
    gap=(e20-e50)/atr; s20=(e20-prev20)/atr; s50=(e50-prev50)/atr; s5=(last-closes[-6])/atr; s20p=(last-closes[-21])/atr
    ranges=[max(b["high"]-b["low"],0) for b in bars]; avg20=max(mean(ranges[-20:]),1e-12); efficiency=abs(last-closes[-13])/max(sum(ranges[-12:]),1e-12)
    hi20=max(highs[-21:-1]); lo20=min(lows[-21:-1]); hi40=max(highs[-41:-1]); lo40=min(lows[-41:-1]); width=max(hi40-lo40,1e-12); pos=max(0,min(1,(last-lo40)/width))
    ph,pl=_pivots(bars); bullish=len(ph)>=2 and ph[-1]>ph[-2] and len(pl)>=2 and pl[-1]>pl[-2]; bearish=len(ph)>=2 and ph[-1]<ph[-2] and len(pl)>=2 and pl[-1]<pl[-2]
    up=sum((gap>.35,s20>.08,s50>-.05,s5>.20,s20p>.45,bullish,efficiency>=.30)); down=sum((gap<-.35,s20<-.08,s50<.05,s5<-.20,s20p<-.45,bearish,efficiency>=.30))
    span=max(highs[-1]-lows[-1],1e-12); body=abs(last-opens[-1])/span; cp=(last-lows[-1])/span; uw=(highs[-1]-max(opens[-1],last))/span; lw=(min(opens[-1],last)-lows[-1])/span
    broke_up=last>hi20; broke_down=last<lo20; sweep_high=highs[-1]>hi20 and last<=hi20; sweep_low=lows[-1]<lo20 and last>=lo20
    acceptance_up=broke_up and cp>=.65 and body>=.45; acceptance_down=broke_down and cp<=.35 and body>=.45
    rejection_high=sweep_high and cp<=.45 and uw>=.20; rejection_low=sweep_low and cp>=.55 and lw>=.20
    displacement_up=body>=.60 and cp>=.75 and span>=1.25*avg20; displacement_down=body>=.60 and cp<=.25 and span>=1.25*avg20
    follow_up=sum(closes[-i]>closes[-i-1] for i in range(1,4)); follow_down=sum(closes[-i]<closes[-i-1] for i in range(1,4)); net5=(last-closes[-5])/atr
    if acceptance_up and follow_up>=2: auction="BUY_SIDE_ACCEPTANCE"; phase="ACCEPTANCE"; strength="HIGH"; reason="buyers broke and held the prior boundary with follow-through"
    elif acceptance_down and follow_down>=2: auction="SELL_SIDE_ACCEPTANCE"; phase="ACCEPTANCE"; strength="HIGH"; reason="sellers broke and held the prior boundary with follow-through"
    elif rejection_high: auction="FAILED_HIGH_AUCTION"; phase="REJECTION"; strength="MODERATE"; reason="price swept the prior high and closed back inside"
    elif rejection_low: auction="FAILED_LOW_AUCTION"; phase="REJECTION"; strength="MODERATE"; reason="price swept the prior low and closed back inside"
    elif up>=5 and net5>.5: auction="BUYER_INITIATIVE_PENDING_ACCEPTANCE"; phase="INITIATIVE"; strength="MODERATE"; reason="buyers show initiative but acceptance is not proven"
    elif down>=5 and net5<-.5: auction="SELLER_INITIATIVE_PENDING_ACCEPTANCE"; phase="INITIATIVE"; strength="MODERATE"; reason="sellers show initiative but acceptance is not proven"
    elif abs(s20p)<.65 and efficiency<.30 and width/atr<8.5: auction="TWO_SIDED_BALANCE"; phase="BALANCE"; strength="LOW"; reason="price is rotational and directionally inefficient"
    else: auction="UNCOMMITTED_AUCTION"; phase="UNRESOLVED"; strength="LOW"; reason="neither side has sufficient closed-candle auction proof"
    balanced=auction=="TWO_SIDED_BALANCE"; long_loc=.10<=pos<=.75; short_loc=.25<=pos<=.90; long_space=max((hi40-last)/atr,0); short_space=max((last-lo40)/atr,0)
    base=_classify_opportunity(up=up,down=down,auction=auction,balanced=balanced,acceptance=acceptance_up or acceptance_down,rejection=rejection_high or rejection_low,space_atr=long_space if up>=down else short_space,location_ok=long_loc if up>=down else short_loc)
    direction=base["direction"]; candidates=[]
    if bullish and rejection_low: candidates.append(_candidate("LIQUIDITY_REVERSAL","BUY",bullish,False,True,False,displacement_up,long_loc,long_space,auction,efficiency))
    if bearish and rejection_high: candidates.append(_candidate("LIQUIDITY_REVERSAL","SELL",bearish,False,True,False,displacement_down,short_loc,short_space,auction,efficiency))
    if acceptance_up: candidates.append(_candidate("AUCTION_ACCEPTANCE_CONTINUATION","BUY",bullish,True,False,False,displacement_up,long_loc,long_space,auction,efficiency))
    if acceptance_down: candidates.append(_candidate("AUCTION_ACCEPTANCE_CONTINUATION","SELL",bearish,True,False,False,displacement_down,short_loc,short_space,auction,efficiency))
    prior_up=closes[-6]>closes[-11]; prior_down=closes[-6]<closes[-11]; retr_up=last<max(closes[-2],closes[-3]) and last>min(closes[-6:-1]); retr_down=last>min(closes[-2],closes[-3]) and last<max(closes[-6:-1])
    pull_up=bullish and prior_up and retr_up and not rejection_high; pull_down=bearish and prior_down and retr_down and not rejection_low
    if pull_up: candidates.append(_candidate("TREND_PULLBACK_CONTINUATION","BUY",bullish,False,False,True,displacement_up,long_loc,long_space,auction,efficiency))
    if pull_down: candidates.append(_candidate("TREND_PULLBACK_CONTINUATION","SELL",bearish,False,False,True,displacement_down,short_loc,short_space,auction,efficiency))
    if not candidates and direction in {"BUY","SELL"}: candidates.append(_candidate("DIRECTIONAL_CONTINUATION_WATCH",direction,bullish if direction=="BUY" else bearish,acceptance_up if direction=="BUY" else acceptance_down,False,False,displacement_up if direction=="BUY" else displacement_down,long_loc if direction=="BUY" else short_loc,long_space if direction=="BUY" else short_space,auction,efficiency))
    eligible=[c for c in candidates if c["eligible"]]
    blockers=_opportunity_blockers(direction=direction,maturity=base["opportunity_maturity"],eligible=bool(eligible),base_blockers=base["blockers"])
    if direction!="NEUTRAL" and (long_space if direction=="BUY" else short_space)<1.0: blockers.append("OPPOSING_SPACE_CONSTRAINED")
    blockers=_dedupe(blockers); missing=list(base["missing_evidence"])
    if direction in {"BUY","SELL"} and "adequate opposing space" not in missing and (long_space if direction=="BUY" else short_space)<1.0: missing.append("adequate opposing space")
    confidence=100*(0.45*(max(up,down)/7)+0.25*(abs(up-down)/7)+0.15*min(efficiency/.5,1)+0.15*min((long_space if direction=="BUY" else short_space)/2,1)) if direction!="NEUTRAL" else 100*(0.5*min(abs(up-down)/3,1)+0.5*(1 if balanced else 0))
    maturity=base["opportunity_maturity"]
    decision="WAIT" if maturity!="ACTIONABLE" else "CONDITIONAL"
    public_direction = "UP" if direction == "BUY" else "DOWN" if direction == "SELL" else "NEUTRAL"
    regime = "TREND" if direction != "NEUTRAL" and not balanced else "RANGE" if balanced else "TRANSITION"
    reasoning = {"question":QUESTION,"conclusion":f"{public_direction} opportunity is {maturity.lower()} based on closed-candle evidence.","why_now":reason,"expected_path":"AUCTION_ACCEPTANCE_AND_FOLLOW_THROUGH" if direction != "NEUTRAL" else "WAIT_FOR_DIRECTIONAL_EVIDENCE","required_evidence":_dedupe(missing),"invalidation_conditions":["closed-candle invalidation of the directional auction or structural thesis"],"timing":"READY_FOR_CONFIRMATION" if maturity=="CONFIRMED" else "DEVELOPING" if direction != "NEUTRAL" else "WAIT","opportunity_quality":round(confidence,2),"counter_evidence_count":len(blockers),"independent_thesis":True,"e1_used_as":"CROSS_CHECK_ONLY","entry_authorized":False}
    return {
        "role":"OPPORTUNITY_REGIME_ANALYST","question":QUESTION,"finding":base["finding"],"state":"ANALYSIS_COMPLETE","architecture":ARCHITECTURE,
        "regime":regime,
        "direction":public_direction,"opportunity_direction":public_direction,
        "reasoning_mode":"SINGLE_PROFESSIONAL_CORE","sub_engines_active":False,"gate":None,"timing_state":reasoning["timing"],"independence":"E2_FIRST_E1_CROSS_CHECK","phase":phase,"auction_state":"CONFIRMED" if phase=="ACCEPTANCE" else "PENDING" if phase in {"INITIATIVE","UNRESOLVED"} else "REJECTED",
        "auction_intent":auction,"auction_intent_detail":{"strength":strength,"reason":reason,"closed_candle_only":True,"follow_through_up":follow_up,"follow_through_down":follow_down},
        "location_context":"FAVORABLE" if (long_loc if direction=="BUY" else short_loc) else "CONSTRAINED","opposing_space_atr":round(long_space if direction=="BUY" else short_space,3),
        "regime_confidence":round(confidence/100,3),"confidence":round(confidence/100,3),"opportunity_score":round(confidence,2),"opportunity_maturity":maturity,
        "opportunity_state":"VISIBLE_PENDING_PROOF" if direction!="NEUTRAL" and maturity!="CONFIRMED" else "VISIBLE","candidate_hypotheses":candidates,
        "candidate_setups":candidates,"counter_evidence":blockers,"counter_evidence_severity":"HIGH" if blockers else "LOW","missing_evidence":_dedupe(missing),
        "confirmation_required":_dedupe(missing),"invalidation_evidence":[],"why_not_trade":blockers,"conditional_map":[{"condition":"AUCTION_CONFIRMED","path":"CONTINUATION" if direction else "WAIT"},{"condition":"AUCTION_REJECTED","path":"REVERSAL_WATCH"}],
        "market_tree":{"directional_evidence":{"up":up,"down":down},"auction":auction,"balanced":balanced,"position40":round(pos,3)},"opportunity_hierarchy":{"direction":"E2","auction":"E2","execution":"E9"},
        "hard_veto":[],"requires_downstream_confirmation":True,"opportunity_decision":decision,"entry":None,"trigger":None,"decision":None,
        "professional_reasoning":{**reasoning,"thesis":reasoning["conclusion"],"evidence_hierarchy":["closed_candle_auction","structure","directional_pressure","location","space"],"maturity_boundary":"E2 may classify opportunity maturity; E7/E8/E9 control confirmation, economics and execution."},
        "reasons":_dedupe(blockers+["E2_OPPORTUNITY_CLASSIFICATION","CLOSED_CANDLE_ONLY","NO_LOOKAHEAD"]),
    }
