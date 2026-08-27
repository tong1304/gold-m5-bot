"""Professional E4 — Liquidity & Auction Brain.

E4 is an analysis-only specialist. It answers one question: where is
liquidity, who took it, and did price accept or reject the auction?

Rules: closed OHLC only; liquidity before direction; a wick is an event, not
confirmation; acceptance/rejection needs post-event closed-candle follow-through;
E1-E3 decisions/gates/scores are excluded; E9 is the sole trade authority.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V14"
FOLLOW_WINDOW = 3
MIN_BARS = 30


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _bars(source: Any) -> list[dict[str, Any]]:
    if isinstance(source, dict): source = source.get("bars") or []
    result = []
    for raw in source if isinstance(source, (list, tuple)) else []:
        if not isinstance(raw, dict): continue
        values = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()): continue
        if values["high"] < max(values["open"], values["close"]): continue
        if values["low"] > min(values["open"], values["close"]): continue
        if values["high"] < values["low"]: continue
        result.append({**raw, **values})
    return result


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2: return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = float(bars[i]["high"]), float(bars[i]["low"]), float(bars[i-1]["close"])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return mean(trs[-period:]) if trs else 0.0


def _pivots(bars, wing=2):
    highs, lows = [], []
    for i in range(wing, len(bars)-wing):
        w = bars[i-wing:i+wing+1]
        if bars[i]["high"] >= max(x["high"] for x in w): highs.append((i, float(bars[i]["high"])))
        if bars[i]["low"] <= min(x["low"] for x in w): lows.append((i, float(bars[i]["low"])))
    return highs, lows


def _cluster(levels, tolerance, side, current):
    groups = []
    for item in sorted(levels, key=lambda x:x[1]):
        if not groups or abs(item[1]-mean(p for _,p in groups[-1])) > tolerance: groups.append([item])
        else: groups[-1].append(item)
    zones=[]
    for group in groups:
        prices=[p for _,p in group]; last=max(i for i,_ in group); age=max(0,current-last)
        zones.append({"side":side,"price":mean(prices),"lower":min(prices),"upper":max(prices),"touches":len(group),"last_touch_index":last,"age_bars":age,"kind":"EQUAL_LIQUIDITY" if len(group)>=2 else "SWING_LIQUIDITY","freshness":"FRESH" if age<=24 else "AGED"})
    return zones


def _liquidity_consumption(zones, bars, atr):
    threshold=max(atr*0.05,1e-9); current=len(bars)-1; result=[]
    for zone in zones:
        z=dict(zone); takes=[]
        for i in range(zone["last_touch_index"]+1,len(bars)):
            b=bars[i]
            crossed=b["high"]>zone["upper"]+threshold if zone["side"]=="HIGH" else b["low"]<zone["lower"]-threshold
            if crossed: takes.append(i)
        latest=takes[-1] if takes else None
        z.update({"liquidity_taken":latest is not None,"taken_index":latest,"take_count":len(takes),"recently_taken":latest is not None and current-latest<=FOLLOW_WINDOW,"state":"TAKEN" if latest is not None and current-latest<=FOLLOW_WINDOW else "CONSUMED" if latest is not None else zone["freshness"]})
        result.append(z)
    return result


def _body_ratio(bar):
    span=max(float(bar["high"])-float(bar["low"]),1e-12)
    return abs(float(bar["close"])-float(bar["open"]))/span


def _event_for_zone(bars, zone, atr, index):
    if index<=0: return None
    bar, prev=bars[index],bars[index-1]; span=max(bar["high"]-bar["low"],1e-12)
    upper_wick=(bar["high"]-max(bar["open"],bar["close"]))/span; lower_wick=(min(bar["open"],bar["close"])-bar["low"])/span
    band=max(atr*0.10,1e-9); extension=max(atr*0.15,1e-9); level=zone["upper"] if zone["side"]=="HIGH" else zone["lower"]
    if zone["side"]=="HIGH":
        failed=prev["close"]>level+extension and bar["close"]<=level
        swept=bar["high"]>level+band and bar["close"]<=level+band
        accepted=bar["close"]>level+extension and _body_ratio(bar)>=0.55
        if failed: kind,direction,taker,state,strength="HIGH_FAILED_BREAK_RECLAIM","DOWN","BUYERS","RECLAIMED",0.92
        elif swept and upper_wick>=0.30: kind,direction,taker,state,strength="HIGH_SWEEP_REJECTION","DOWN","BUYERS","TAKEN",0.94
        elif accepted: kind,direction,taker,state,strength="HIGH_ACCEPTANCE","UP","BUYERS","ACCEPTANCE",0.88
        elif swept: kind,direction,taker,state,strength="HIGH_LIQUIDITY_INTERACTION","NEUTRAL","BUYERS","TAKEN",0.55
        else: return None
    else:
        failed=prev["close"]<level-extension and bar["close"]>=level
        swept=bar["low"]<level-band and bar["close"]>=level-band
        accepted=bar["close"]<level-extension and _body_ratio(bar)>=0.55
        if failed: kind,direction,taker,state,strength="LOW_FAILED_BREAK_RECLAIM","UP","SELLERS","RECLAIMED",0.92
        elif swept and lower_wick>=0.30: kind,direction,taker,state,strength="LOW_SWEEP_REJECTION","UP","SELLERS","TAKEN",0.94
        elif accepted: kind,direction,taker,state,strength="LOW_ACCEPTANCE","DOWN","SELLERS","ACCEPTANCE",0.88
        elif swept: kind,direction,taker,state,strength="LOW_LIQUIDITY_INTERACTION","NEUTRAL","SELLERS","TAKEN",0.55
        else: return None
    return {"type":kind,"auction_state":state if state in {"REJECTION","ACCEPTANCE"} else "FAILED_BREAK_RECLAIM" if "FAILED" in kind else "UNRESOLVED","directional_implication":direction,"liquidity_state":state,"liquidity_taker":taker,"response_actor":"SELLERS" if direction=="DOWN" else "BUYERS" if direction=="UP" else "UNCLEAR","strength":strength,"zone":zone,"index":index}


def _find_recent_event(bars, high_zones, low_zones, atr):
    current=len(bars)-1; zones=high_zones+low_zones
    for index in range(current,max(0,current-3),-1):
        for zone in sorted(zones,key=lambda z:abs(z["price"]-bars[index]["close"])):
            touched=bars[index]["high"]>=zone["lower"]-atr*0.10 if zone["side"]=="HIGH" else bars[index]["low"]<=zone["upper"]+atr*0.10
            if touched:
                event=_event_for_zone(bars,zone,atr,index)
                if event: return event
    return {"type":"NO_CONFIRMED_LIQUIDITY_EVENT","auction_state":"UNRESOLVED","directional_implication":"NEUTRAL","liquidity_state":"UNRESOLVED","liquidity_taker":"NONE","response_actor":"NONE","strength":0.30,"zone":None,"index":current}


def _follow_through(event, bars, atr):
    index=int(event.get("index",-1)); zone=event.get("zone") or {}
    if index<0 or index>=len(bars)-1 or not zone: return {"present":False,"bars":0,"reason":"NO_POST_EVENT_CANDLE","invalidated":False}
    direction=str(event.get("directional_implication") or "NEUTRAL").upper(); event_close=float(bars[index]["close"]); upper=float(zone.get("upper",event_close)); lower=float(zone.get("lower",event_close)); distance=max(atr*0.05,1e-9)
    confirmed_bars=0; invalidated=False; checks=[]
    for j in range(index+1,min(len(bars),index+FOLLOW_WINDOW+1)):
        close=float(bars[j]["close"])
        if direction=="DOWN": away=close<event_close-distance; held=close<upper-distance; reclaim=close>upper+distance
        elif direction=="UP": away=close>event_close+distance; held=close>lower+distance; reclaim=close<lower-distance
        else: away=held=reclaim=False
        if reclaim: invalidated=True
        ok=away and held and not reclaim
        if ok: confirmed_bars+=1
        checks.append({"index":j,"close":close,"confirmed":ok,"reclaimed":reclaim})
    return {"present":confirmed_bars>=1 and not invalidated,"bars":confirmed_bars,"reason":"FOLLOW_THROUGH_OBSERVED" if confirmed_bars>=1 and not invalidated else "FOLLOW_THROUGH_ABSENT","invalidated":invalidated,"checks":checks}


def _auction_confirmation(event,bars,atr):
    if not event or not event.get("zone"): return {"state":"UNRESOLVED","confirmed":False,"follow_through":False,"follow_through_bars":0,"reason":"NO_EVENT"}
    follow=_follow_through(event,bars,atr); state=str(event.get("auction_state") or "UNRESOLVED")
    if follow["invalidated"]: return {"state":"INVALIDATED","confirmed":False,"follow_through":False,"follow_through_bars":follow["bars"],"reason":"POST_EVENT_RECLAMATION","detail":follow}
    if follow["present"]:
        final="REJECTION_CONFIRMED" if state in {"REJECTION","FAILED_BREAK_RECLAIM"} else "ACCEPTANCE_CONFIRMED" if state=="ACCEPTANCE" else "UNRESOLVED"
        return {"state":final,"confirmed":final!="UNRESOLVED","follow_through":True,"follow_through_bars":follow["bars"],"reason":"FOLLOW_THROUGH_OBSERVED","detail":follow}
    pending="REJECTION_PENDING" if state in {"REJECTION","FAILED_BREAK_RECLAIM"} else "ACCEPTANCE_PENDING" if state=="ACCEPTANCE" else "UNRESOLVED"
    return {"state":pending,"confirmed":False,"follow_through":False,"follow_through_bars":follow["bars"],"reason":follow["reason"],"detail":follow}


def _context_hint(bus):
    votes=[]
    for engine_id in ("E1","E2","E3"):
        package=(bus or {}).get(engine_id,{})
        evidence=package.get("evidence",package) if isinstance(package,dict) else {}
        output=evidence.get("output",evidence) if isinstance(evidence,dict) else evidence
        text=str(output).upper()
        if any(x in text for x in ("DIRECTION=UP","TREND_STATE=UP","PRESSURE=BULLISH")): votes.append("UP")
        if any(x in text for x in ("DIRECTION=DOWN","TREND_STATE=DOWN","PRESSURE=BEARISH")): votes.append("DOWN")
    return "UP" if votes.count("UP")>votes.count("DOWN") else "DOWN" if votes.count("DOWN")>votes.count("UP") else "NEUTRAL"


def analyze_e4(snapshot=None,evidence_bus=None):
    bars=_bars(snapshot); atr=_atr(bars); context=_context_hint(evidence_bus)
    base={"architecture":ARCHITECTURE,"professional_brain":True,"role":E4_ROLE,"question":PROFESSIONAL_QUESTION,"specialists":{},"specialists_active":False,"specialists_status":"PAUSED","decision":None,"gate":None,"score":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","reasoning_role":E4_ROLE,"upstream_decisions_used":False,"upstream_gates_used":False,"scores_used":False,"score_used":False,"contextual_direction_hint":context,"evidence":{"raw_market_data_used":True,"decisions_used":False,"gates_used":False,"scores_used":False}}
    if len(bars)<MIN_BARS or atr<=0:
        return {**base,"state":"UNAVAILABLE","analysis_status":"INCOMPLETE","finding":"LIQUIDITY_DATA_INSUFFICIENT","direction":"NEUTRAL","directional_implication":"NEUTRAL","confidence":0.0,"evidence_strength":0.0,"observations":[],"liquidity_map":{},"event":{"type":"LIQUIDITY_DATA_INSUFFICIENT","liquidity_state":"UNRESOLVED"},"auction":{"state":"UNRESOLVED","confirmed":False,"follow_through":False,"follow_through_bars":0},"auction_state":"UNRESOLVED","follow_through":{"present":False,"bars":0},"follow_through_bars":0,"auction_confirmation":{"confirmed":False},"auction_confirmation_state":"UNRESOLVED","interaction":{},"context_used":{e:bool((evidence_bus or {}).get(e)) for e in ("E1","E2","E3")},"reasons":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"conflicts":[],"missing_evidence":["CLOSED_CANDLE_HISTORY"]}
    current=len(bars)-1; hp,lp=_pivots(bars); tolerance=max(atr*0.15,1e-9)
    highs=_liquidity_consumption(_cluster(hp[-60:],tolerance,"HIGH",current),bars,atr); lows=_liquidity_consumption(_cluster(lp[-60:],tolerance,"LOW",current),bars,atr)
    event=_find_recent_event(bars,highs,lows,atr); confirmation=_auction_confirmation(event,bars,atr); confirmed=confirmation["confirmed"]; direction=event["directional_implication"] if confirmed else "NEUTRAL"
    reasons=["LIQUIDITY_EVENT_DETECTED",f"LIQUIDITY_TAKER={event.get('liquidity_taker','NONE')}",f"AUCTION_{confirmation['state']}"] if event.get("zone") else ["NO_CONFIRMED_LIQUIDITY_EVENT"]
    if event.get("zone") and not confirmed: reasons.append("AUCTION_RESPONSE_NOT_CONFIRMED")
    follow=confirmation.get("detail") or _follow_through(event,bars,atr)
    return {**base,"state":"ANALYSIS_COMPLETE","analysis_status":"COMPLETE","finding":event["type"],"direction":direction,"directional_implication":direction,"confidence":round(event["strength"] if confirmed else min(event["strength"],0.45),3),"evidence_strength":round(event["strength"],3),"observations":[f"closed_candles={len(bars)}",f"atr14={atr:.6f}",f"high_liquidity_zones={len(highs)}",f"low_liquidity_zones={len(lows)}",f"event={event['type']}",f"liquidity_taker={event.get('liquidity_taker','NONE')}",f"auction_state={confirmation['state']}",f"follow_through_bars={confirmation['follow_through_bars']}",f"contextual_direction={context}"],"liquidity_map":{"high_zones":highs,"low_zones":lows},"event":event,"auction":confirmation,"auction_state":confirmation["state"],"follow_through":follow,"follow_through_bars":confirmation["follow_through_bars"],"auction_confirmation":confirmation,"auction_confirmation_state":confirmation["state"],"interaction":{"rejection":confirmation["state"].startswith("REJECTION"),"acceptance":confirmation["state"].startswith("ACCEPTANCE"),"failed_break_reclaim":"FAILED_BREAK" in event["type"],"liquidity_taker":event.get("liquidity_taker","NONE"),"response_actor":event.get("response_actor","NONE")},"context_used":{e:bool((evidence_bus or {}).get(e)) for e in ("E1","E2","E3")},"reasons":reasons,"conflicts":[],"missing_evidence":[] if confirmed else ["CONFIRMED_AUCTION_RESPONSE"]}


def _classify_auction_response(event,bars,atr,event_index=None):
    if event_index is not None: event={**event,"index":event_index}
    result=_auction_confirmation(event,bars,atr)
    return {"response":result["state"],"confirmed":result["confirmed"],"follow_through_bars":result["follow_through_bars"],"quality":"CONFIRMED" if result["confirmed"] else "PENDING" if result["state"]!="UNRESOLVED" else "UNRESOLVED","reason":result["reason"]}


class SubEngine:
    def run(self, snapshot):
        evidence_bus=snapshot.get("evidence_bus") if isinstance(snapshot,dict) else None
        output=analyze_e4(snapshot,evidence_bus)
        try:
            from .contracts import EngineResult
            return EngineResult("E4", "Liquidity Brain", None, float(output.get("evidence_strength",0.0))*100.0, output, tuple(output.get("reasons",())))
        except Exception:
            return output


__all__=["SubEngine","analyze_e4","_follow_through","_classify_auction_response"]
