"""E1 Professional Market-State Brain V8.
Hierarchical context arbitration; E1 only, no trade authority."""
from __future__ import annotations
from typing import Any
from .e1_professional_layer_v7 import analyze_e1_professional_v7, _atr, _ema, _slope, _structure_direction

MIN_GAP_ATR=0.50
MIN_SLOPE_ATR=0.20
TRANSITION_SCORE=3

def _dir(v: Any)->str:
    s=str(v or "").upper()
    return "UP" if s in {"UP","BULLISH","TREND_UP"} else "DOWN" if s in {"DOWN","BEARISH","TREND_DOWN"} else "NEUTRAL"

def _opp(d:str)->str:
    return "DOWN" if d=="UP" else "UP" if d=="DOWN" else "NEUTRAL"

def _recent_pressure(bars:list[dict[str,Any]], atr:float)->str:
    if atr<=0 or len(bars)<2:return "NEUTRAL"
    x=bars[-5:]; delta=float(x[-1]["close"])-float(x[0]["close"])
    return "UP" if delta>=0.15*atr else "DOWN" if delta<=-0.15*atr else "NEUTRAL"

def _transition(dominant:str,ema:str,structure:str,s20:float,s40:float,gap:float,recent:str,base:str)->dict[str,Any]:
    if dominant not in {"UP","DOWN"}: return {"score":0,"watch":base in {"WATCH","DETECTED","VALIDATED","PRESENT"},"committed":False,"evidence":[]}
    o=_opp(dominant); score=0; ev=[]
    if ema==o: score+=1; ev.append("EMA_RELATION_OPPOSITE")
    if structure==o: score+=2; ev.append("STRUCTURE_OPPOSITE")
    if (o=="DOWN" and s20<=-MIN_SLOPE_ATR and s40<=-MIN_SLOPE_ATR) or (o=="UP" and s20>=MIN_SLOPE_ATR and s40>=MIN_SLOPE_ATR): score+=1; ev.append("LONG_SLOPES_OPPOSITE")
    if (o=="DOWN" and gap<=-MIN_GAP_ATR) or (o=="UP" and gap>=MIN_GAP_ATR): score+=1; ev.append("EMA_GAP_OPPOSITE")
    if recent==o: score+=1; ev.append("RECENT_PRESSURE_OPPOSITE")
    committed=score>=TRANSITION_SCORE and structure==o
    return {"score":score,"watch":score>=2 or base in {"WATCH","DETECTED","VALIDATED","PRESENT"},"committed":committed,"evidence":ev}

def _arb(base:str,ema:str,structure:str,s20:float,s40:float,gap:float,recent:str,base_transition:str)->dict[str,Any]:
    if ema in {"UP","DOWN"} and structure==ema: dominant=ema; basis="STRUCTURE_EMA_ALIGNMENT"
    elif ema in {"UP","DOWN"} and abs(gap)>=MIN_GAP_ATR and ((ema=="UP" and s20>=MIN_SLOPE_ATR and s40>=MIN_SLOPE_ATR) or (ema=="DOWN" and s20<=-MIN_SLOPE_ATR and s40<=-MIN_SLOPE_ATR)): dominant=ema; basis="EMA_LONG_HORIZON_ALIGNMENT"
    elif structure in {"UP","DOWN"} and ((structure=="UP" and s20>=MIN_SLOPE_ATR and s40>=MIN_SLOPE_ATR) or (structure=="DOWN" and s20<=-MIN_SLOPE_ATR and s40<=-MIN_SLOPE_ATR)): dominant=structure; basis="STRUCTURE_LONG_HORIZON_ALIGNMENT"
    elif s20>=MIN_SLOPE_ATR and s40>=MIN_SLOPE_ATR: dominant="UP"; basis="LONG_HORIZON_ALIGNMENT"
    elif s20<=-MIN_SLOPE_ATR and s40<=-MIN_SLOPE_ATR: dominant="DOWN"; basis="LONG_HORIZON_ALIGNMENT"
    else: dominant="NEUTRAL"; basis="NO_DOMINANT_CONTEXT"
    te=_transition(dominant,ema,structure,s20,s40,gap,recent,base_transition)
    if te["committed"]: state="TRANSITION"; transition="CONFIRMED"
    elif dominant=="UP": state="TREND_UP"; transition="WATCH" if te["watch"] else "ABSENT"
    elif dominant=="DOWN": state="TREND_DOWN"; transition="WATCH" if te["watch"] else "ABSENT"
    else: state=base if base in {"RANGE","COMPRESSION","EXPANSION","TRANSITION"} else "UNCLEAR"; transition="WATCH" if te["watch"] else "ABSENT"
    phase="IMPULSE" if recent==dominant else "PULLBACK" if dominant in {"UP","DOWN"} and recent==_opp(dominant) else "CONSOLIDATION" if dominant in {"UP","DOWN"} else "UNRESOLVED"
    return {"market_state":state,"dominant_direction":dominant,"dominant_basis":basis,"market_phase":phase,"current_pressure":"BULLISH" if recent=="UP" else "BEARISH" if recent=="DOWN" else "NEUTRAL","counter_pressure":"PULLBACK_WITHIN_TREND" if phase=="PULLBACK" else "NONE","transition":transition,"transition_committed":te["committed"],"transition_evidence":te}

def analyze_e1_professional_v8(bars:list[dict[str,Any]]|None)->dict[str,Any]:
    out=dict(analyze_e1_professional_v7(bars))
    if out.get("analysis_status")=="INCOMPLETE": return out
    clean=[b for b in (bars or []) if isinstance(b,dict) and all(k in b for k in ("open","high","low","close"))]
    if len(clean)<50:
        out["analysis_status"]="INCOMPLETE"; out["reasons"]=list(dict.fromkeys([*(out.get("reasons") or []),"INSUFFICIENT_CANDLES_FOR_V8"])); return out
    closes=[float(b["close"]) for b in clean]; atr=_atr(clean); e20,e50=_ema(closes,20),_ema(closes,50); gap=(e20-e50)/max(atr,1e-12); ema="UP" if e20>e50 else "DOWN" if e20<e50 else "NEUTRAL"; structure=_structure_direction(clean); s20,s40=_slope(closes,atr,20),_slope(closes,atr,40); recent=_recent_pressure(clean,atr); base=str(out.get("market_state") or "UNCLEAR").upper(); bt=str(out.get("transition_status") or out.get("transition") or "NONE").upper(); a=_arb(base,ema,structure,s20,s40,gap,recent,bt)
    out.update({"market_state":a["market_state"],"trend_state":a["dominant_direction"] if a["market_state"] in {"TREND_UP","TREND_DOWN"} else "NONE","directional_state":"CONFIRMED" if a["dominant_direction"] in {"UP","DOWN"} else "UNRESOLVED","dominant_direction":a["dominant_direction"],"market_phase":a["market_phase"],"directional_pressure":a["dominant_direction"],"current_pressure":a["current_pressure"],"counter_pressure":a["counter_pressure"],"transition":a["transition"],"transition_status":"COMMITTED" if a["transition_committed"] else a["transition"],"transition_committed":a["transition_committed"],"e1_contract_version":"PROFESSIONAL_MARKET_STATE_V8","e1_trade_authority":False,"trade_decision_authority":False,"v8_arbitration":a})
    pr=dict(out.get("professional_reasoning") or {}); thesis=dict(pr.get("primary_thesis") or {}); thesis.update({"direction":a["dominant_direction"],"market_state":a["market_state"],"phase":a["market_phase"],"transition":a["transition"],"status":"CONFIRMED" if a["dominant_direction"] in {"UP","DOWN"} else "UNRESOLVED"});
    if a["counter_pressure"]=="PULLBACK_WITHIN_TREND": thesis["counter_evidence"]=list(dict.fromkeys([*(thesis.get("counter_evidence") or []),"COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL"]))
    sm=dict(pr.get("state_machine") or {}); sm.update({"version":"V8","dominant_direction":a["dominant_direction"],"dominant_basis":a["dominant_basis"],"market_state":a["market_state"],"market_phase":a["market_phase"],"current_pressure":a["current_pressure"],"counter_pressure":a["counter_pressure"],"transition":a["transition"],"transition_committed":a["transition_committed"],"transition_evidence":a["transition_evidence"],"rule":"Structure and long-horizon context define the dominant regime; short counter-pressure changes phase, not regime. Transition requires multi-factor structural evidence."}); pr.update({"state_machine":sm,"primary_thesis":thesis,"market_state":a["market_state"],"dominant_direction":a["dominant_direction"],"market_phase":a["market_phase"],"current_pressure":a["current_pressure"],"counter_pressure":a["counter_pressure"],"decision_boundary":"MARKET_STATE_ONLY_NO_SETUP_NO_ENTRY_NO_RISK_NO_TRADE_DECISION"}); out["professional_reasoning"]=pr
    reasons=list(dict.fromkeys([*(out.get("reasons") or []),"V8_HIERARCHICAL_CONTEXT_ARBITRATION","V8_TRANSITION_REQUIRES_STRUCTURAL_CONFIRMATION"]));
    if a["counter_pressure"]=="PULLBACK_WITHIN_TREND": reasons.append("V8_COUNTER_PRESSURE_IS_PULLBACK_NOT_REVERSAL")
    if a["transition_committed"]: reasons.append("V8_TRANSITION_STRUCTURALLY_CONFIRMED")
    out["reasons"]=list(dict.fromkeys(reasons)); trace=list(out.get("reasoning_trace") or []); trace.extend([f"V8_DOMINANT_CONTEXT -> {a['dominant_direction']} basis={a['dominant_basis']}",f"V8_PHASE -> {a['market_phase']} recent_pressure={recent}",f"V8_TRANSITION -> {a['transition']} score={a['transition_evidence']['score']} committed={a['transition_committed']}","V8_PRIORITY -> structure/long-horizon context > short-term pressure","V8_DECISION_BOUNDARY -> market-state only; no setup/entry/risk/trade authority"]); out["reasoning_trace"]=trace; return out
