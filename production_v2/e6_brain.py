from __future__ import annotations
from statistics import mean
from typing import Any
from .contracts import EngineResult

NAME="Setup Brain"
QUESTION="What setup is forming, in what direction, and at what stage?"
MIN_BARS=40


def _ema(values:list[float], period:int)->float:
    if not values:return 0.0
    alpha=2.0/(period+1.0); value=values[0]
    for x in values[1:]: value=alpha*x+(1-alpha)*value
    return value


def _norm_direction(value:Any)->str:
    v=str(value or "NEUTRAL").upper().strip()
    if v in {"UP","BULLISH","BUY","LONG","TREND_UP"}: return "BUY"
    if v in {"DOWN","BEARISH","SELL","SHORT","TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _evidence_direction(e1:dict[str,Any],e2:dict[str,Any],e3:dict[str,Any])->tuple[str,list[str],list[str]]:
    support=[]; counter=[]
    e2dir=_norm_direction(e2.get("direction")); e1pressure=_norm_direction(e1.get("directional_pressure"))
    if e2dir in {"BUY","SELL"}:
        direction=e2dir; support.append(f"E2_opportunity_direction={e2dir}")
    elif e1pressure in {"BUY","SELL"}:
        direction=e1pressure; support.append(f"E1_pressure_direction={e1pressure}")
    else: direction="NEUTRAL"
    slope=str(e3.get("slope_context","")).upper()
    if slope in {"UP","DOWN"}:
        slope_dir="BUY" if slope=="UP" else "SELL"
        if direction in {"BUY","SELL"} and slope_dir!=direction: counter.append("STRUCTURE_SLOPE_CONFLICT")
        support.append(f"E3_slope={slope}")
    finding=str(e3.get("finding",e3.get("structure_state",""))).upper()
    internal=str(e3.get("internal_count_state","")).upper(); external=str(e3.get("external_count_state","")).upper()
    if "MIXED" in finding or "MIXED" in internal: counter.append("STRUCTURE_MIXED")
    if direction=="BUY" and external=="DOWN": counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if direction=="SELL" and external=="UP": counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    if "CHOCH" in finding or "CHOCH" in str(e3.get("external_bos","")).upper(): counter.append("STRUCTURE_TRANSITION_EVIDENCE")
    return direction,support,counter


def analyze_e6(snapshot:dict[str,Any],upstream:dict[str,EngineResult])->EngineResult:
    bars=list(snapshot.get("bars") or [])
    base={"question":QUESTION,"reasoning_role":"SETUP_ANALYST","decision_authority":"E9","trade_decision_authority":False}
    if len(bars)<MIN_BARS:
        return EngineResult("E6",NAME,None,0,{**base,"state":"WAIT","setup":"NONE","direction":"NEUTRAL","maturity":"UNRESOLVED","thesis":"UNRESOLVED","supporting_evidence":[],"counter_evidence":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"missing_evidence":["sufficient price history"],"invalidation":["new closed candle"]},("INSUFFICIENT_DATA",))

    c=[float(x["close"]) for x in bars]; h=[float(x["high"]) for x in bars]; l=[float(x["low"]) for x in bars]; o=[float(x["open"]) for x in bars]
    atr=max(mean(max(float(b["high"])-float(b["low"]),abs(float(b["high"])-float(bars[max(0,i-1)]["close"])),abs(float(b["low"])-float(bars[max(0,i-1)]["close"]))) for i,b in enumerate(bars[-14:],max(1,len(bars)-14))),1e-9)
    price=c[-1]; e20=_ema(c,20); e50=_ema(c,50)
    e1=(upstream.get("E1").output if upstream.get("E1") else {}); e2=(upstream.get("E2").output if upstream.get("E2") else {}); e3=(upstream.get("E3").output if upstream.get("E3") else {}); e4=(upstream.get("E4").output if upstream.get("E4") else {}); e5=(upstream.get("E5").output if upstream.get("E5") else {})
    direction,supporting,counter=_evidence_direction(e1,e2,e3)
    e2opp=str(e2.get("opportunity",e2.get("opportunity_type",""))).upper(); e2phase=str(e2.get("phase",e2.get("opportunity_maturity",""))).upper(); e2thesis=str(e2.get("thesis","")).upper()
    loc=str(e5.get("finding",e5.get("location_state",""))).upper(); e4finding=str(e4.get("finding","")).upper()

    body=abs(c[-1]-o[-1]); rng=max(h[-1]-l[-1],1e-9); close_pos=(c[-1]-l[-1])/rng; impulse=body>=0.60*atr
    prior_hi=max(h[-11:-1]); prior_lo=min(l[-11:-1]); breakout=(direction=="BUY" and price>prior_hi) or (direction=="SELL" and price<prior_lo); pullback=abs(price-e20)<=0.85*atr

    if "TREND_PULLBACK_CONTINUATION" in e2opp or "TREND_PULLBACK_CONTINUATION" in e2thesis:
        setup="TREND_PULLBACK_CONTINUATION" if direction in {"BUY","SELL"} else "NONE"
    elif "BREAKOUT" in e2opp and direction in {"BUY","SELL"}: setup="BREAKOUT"
    elif breakout and direction in {"BUY","SELL"}: setup="BREAKOUT"
    elif direction in {"BUY","SELL"} and pullback: setup="TREND_PULLBACK"
    elif direction in {"BUY","SELL"} and impulse: setup="IMPULSE_CONTINUATION"
    else: setup="NONE"

    supporting += [f"E2_opportunity={e2opp or 'UNSPECIFIED'}",f"E2_phase={e2phase or 'UNSPECIFIED'}",f"E1_state={str(e1.get('market_state','UNCLEAR')).upper()}",f"impulse={impulse}",f"breakout={breakout}",f"pullback={pullback}"]
    if loc in {"SPACE_CONSTRAINED","ADVERSE"}: counter.append("LOCATION_CONSTRAINED")
    if e4finding.startswith("HIGH_") and "REJECTION" in e4finding: supporting.append("LIQUIDITY_REJECTION_SUPPORT")
    missing=[] if setup!="NONE" else ["clear_setup_pattern"]
    if setup!="NONE" and e2phase in {"UNPROVEN","WAIT","UNRESOLVED"}: missing.append("opportunity_maturity")
    if setup!="NONE" and not (pullback or breakout or impulse or setup=="TREND_PULLBACK_CONTINUATION"): missing.append("setup_price_behavior")

    thesis="UNRESOLVED" if direction=="NEUTRAL" or setup=="NONE" else f"{direction}_{setup}"
    hard_conflicts={"STRUCTURE_SLOPE_CONFLICT","EXTERNAL_STRUCTURE_COUNTERTREND"}
    maturity=("MATURE" if setup!="NONE" and direction in {"BUY","SELL"} and not any(x in counter for x in hard_conflicts) and "MIXED" not in str(e3.get("finding","")).upper() and loc not in {"SPACE_CONSTRAINED","ADVERSE"}
              else "DEVELOPING" if setup!="NONE" and direction in {"BUY","SELL"} else "UNRESOLVED")
    gate=maturity=="MATURE"; score=90 if gate else 65 if maturity=="DEVELOPING" else 20
    reasons=[] if gate else list(dict.fromkeys(counter+missing or ["SETUP_NOT_MATURE"]))
    return EngineResult("E6",NAME,gate,score,{**base,"state":maturity,"setup":setup,"direction":direction,"maturity":maturity,"thesis":thesis,"opportunity_source":"E2_FIRST_WITH_E1_E3_CROSS_CHECK","supporting_evidence":supporting,"counter_evidence":list(dict.fromkeys(counter)),"missing_evidence":missing,"invalidation":["directional thesis reverses","structure confirms a competing direction","setup price behavior fails","location/path becomes structurally constrained","new closed candle invalidates setup"]},tuple(reasons))
