"""Production-V2 E4 Professional Liquidity & Auction Brain.

E4 independently answers: where is liquidity, who took it, and did price
accept or reject the auction? It is analysis-only. E9 owns execution decisions.
"""
from __future__ import annotations
from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V12_LIQUIDITY_AUCTION"
MIN_BARS = 30


def _num(x: Any) -> float | None:
    try:
        y = float(x)
        return y if isfinite(y) else None
    except (TypeError, ValueError):
        return None


def _bars(snapshot: Any) -> list[dict[str, float]]:
    source = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    out = []
    for b in source:
        if not isinstance(b, dict):
            continue
        v = {k: _num(b.get(k)) for k in ("open", "high", "low", "close")}
        if all(x is not None for x in v.values()) and v["high"] >= max(v["open"], v["close"]) and v["low"] <= min(v["open"], v["close"]) and v["high"] >= v["low"]:
            out.append(v)  # type: ignore[arg-type]
    return out


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if not bars:
        return 0.0
    trs = []
    prev = None
    for b in bars[-period:]:
        tr = b["high"] - b["low"] if prev is None else max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev))
        trs.append(tr)
        prev = b["close"]
    return mean(trs) if trs else 0.0


def _pivots(bars: list[dict[str, float]], wing: int = 2):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        w = bars[i-wing:i+wing+1]
        if bars[i]["high"] >= max(x["high"] for x in w):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in w):
            lows.append((i, bars[i]["low"]))
    return highs, lows


def _cluster(levels, tolerance: float, current: int, kind: str):
    groups = []
    for item in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(item[1] - mean(x[1] for x in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    zones = []
    for g in groups:
        prices = [x[1] for x in g]
        last_touch = max(x[0] for x in g)
        zones.append({
            "price": mean(prices), "lower": min(prices), "upper": max(prices),
            "touches": len(g), "last_touch_index": last_touch,
            "age_bars": max(0, current-last_touch),
            "type": "EQUAL_LIQUIDITY" if len(g) >= 2 else "SWING_LIQUIDITY",
            "side": kind, "fresh": len(g) >= 2 or current-last_touch <= 30,
        })
    return zones


def _consumption(zone, bars, atr, current):
    z = dict(zone)
    threshold = max(atr * 0.05, 1e-9)
    crossings = []
    for i in range(zone["last_touch_index"] + 1, current + 1):
        b = bars[i]
        crossed = b["high"] > zone["upper"] + threshold if zone["side"] == "HIGH" else b["low"] < zone["lower"] - threshold
        if crossed:
            crossings.append(i)
    recent = [i for i in crossings if current-i <= 2]
    z["historical_crossings"] = crossings[:-len(recent)] if recent else crossings
    z["recent_crossings"] = recent
    z["state"] = "TAKEN" if recent else ("CONSUMED" if crossings else ("FRESH" if zone["fresh"] else "AGED"))
    z["consumed"] = bool(crossings)
    z["last_crossing_index"] = crossings[-1] if crossings else None
    return z


def _candle_quality(b):
    rng = max(b["high"]-b["low"], 1e-9)
    body = abs(b["close"]-b["open"])/rng
    close_pos = (b["close"]-b["low"])/rng
    return rng, body, close_pos


def _find_event(bars, highs, lows, atr, idx):
    b = bars[idx]
    prev = bars[idx-1] if idx else b
    rng, body, close_pos = _candle_quality(b)
    tol = max(atr*0.10, 1e-9)
    candidates = []
    for z in highs:
        if z["recent_crossings"] and z["recent_crossings"][-1] != idx:
            continue
        if b["high"] >= z["upper"] - atr*0.75:
            penetration = b["high"] - z["upper"]
            rejection = penetration > tol and b["close"] <= z["upper"] + tol and (b["high"]-max(b["open"],b["close"])) / rng >= 0.25
            failed = prev["close"] > z["upper"] + atr*0.10 and b["close"] <= z["upper"] + tol
            accepted = b["close"] > z["upper"] + atr*0.15 and body >= 0.55
            if failed:
                candidates.append((3, {"type":"HIGH_FAILED_BREAK_RECLAIM","direction":"DOWN","taker":"BUYERS","liquidity_state":"RECLAIMED","zone":z,"index":idx,"strength":0.90}))
            elif rejection:
                candidates.append((2, {"type":"HIGH_SWEEP_REJECTION","direction":"DOWN","taker":"BUYERS","liquidity_state":"TAKEN","zone":z,"index":idx,"strength":0.88}))
            elif accepted:
                candidates.append((1, {"type":"HIGH_ACCEPTANCE_CANDIDATE","direction":"UP","taker":"BUYERS","liquidity_state":"ACCEPTED","zone":z,"index":idx,"strength":0.70}))
    for z in lows:
        if z["recent_crossings"] and z["recent_crossings"][-1] != idx:
            continue
        if b["low"] <= z["lower"] + atr*0.75:
            penetration = z["lower"] - b["low"]
            rejection = penetration > tol and b["close"] >= z["lower"] - tol and (min(b["open"],b["close"])-b["low"]) / rng >= 0.25
            failed = prev["close"] < z["lower"] - atr*0.10 and b["close"] >= z["lower"] - tol
            accepted = b["close"] < z["lower"] - atr*0.15 and body >= 0.55
            if failed:
                candidates.append((3, {"type":"LOW_FAILED_BREAK_RECLAIM","direction":"UP","taker":"SELLERS","liquidity_state":"RECLAIMED","zone":z,"index":idx,"strength":0.90}))
            elif rejection:
                candidates.append((2, {"type":"LOW_SWEEP_REJECTION","direction":"UP","taker":"SELLERS","liquidity_state":"TAKEN","zone":z,"index":idx,"strength":0.88}))
            elif accepted:
                candidates.append((1, {"type":"LOW_ACCEPTANCE_CANDIDATE","direction":"DOWN","taker":"SELLERS","liquidity_state":"ACCEPTED","zone":z,"index":idx,"strength":0.70}))
    return max(candidates, key=lambda x:x[0])[1] if candidates else None


def _follow_through(event, bars, atr):
    i = event["index"]
    if i >= len(bars)-1:
        return {"present": False, "bars": 0, "reason": "NO_POST_EVENT_CANDLE"}
    z = event["zone"]
    direction = event["direction"]
    count = 0
    for j in range(i+1, min(len(bars), i+3)):
        b = bars[j]
        if direction == "UP" and b["close"] > z["upper"] + atr*0.05:
            count += 1
        if direction == "DOWN" and b["close"] < z["lower"] - atr*0.05:
            count += 1
        if "REJECTION" in event["type"] or "FAILED_BREAK" in event["type"]:
            if direction == "DOWN" and b["close"] < bars[i]["close"] - atr*0.05:
                count += 1
            if direction == "UP" and b["close"] > bars[i]["close"] + atr*0.05:
                count += 1
    return {"present": count >= 1, "bars": count, "reason": "FOLLOW_THROUGH_OBSERVED" if count >= 1 else "FOLLOW_THROUGH_ABSENT"}


def _auction(event, bars, atr):
    if not event or not event.get("zone"):
        return {"response":"UNRESOLVED","follow_through":False,"quality":"UNRESOLVED"}
    f = _follow_through(event, bars, atr)
    typ = event["type"]
    if "REJECTION" in typ or "FAILED_BREAK" in typ:
        return {"response":"REJECTION_CONFIRMED" if f["present"] else "REJECTION_PENDING","follow_through":f["present"],"quality":"CONFIRMED" if f["present"] else "PENDING","follow_through_detail":f}
    if "ACCEPTANCE_CANDIDATE" in typ:
        return {"response":"ACCEPTANCE_CONFIRMED" if f["present"] else "ACCEPTANCE_PENDING","follow_through":f["present"],"quality":"CONFIRMED" if f["present"] else "PENDING","follow_through_detail":f}
    return {"response":"UNRESOLVED","follow_through":f["present"],"quality":"UNRESOLVED"}


def _context_hint(bus):
    votes=[]
    for eid in ("E1","E2","E3"):
        p=(bus or {}).get(eid,{})
        e=p.get("evidence") if isinstance(p,dict) else None
        text=str(e.get("output",e) if isinstance(e,dict) else e or "").upper()
        if any(x in text for x in ("DIRECTION=UP","TREND_STATE=UP","PRESSURE=BULLISH")):
            votes.append("UP")
        if any(x in text for x in ("DIRECTION=DOWN","TREND_STATE=DOWN","PRESSURE=BEARISH")):
            votes.append("DOWN")
    return "UP" if votes.count("UP")>votes.count("DOWN") else "DOWN" if votes.count("DOWN")>votes.count("UP") else "NEUTRAL"


def analyze_e4(snapshot=None, evidence_bus=None):
    bars=_bars(snapshot); atr=_atr(bars); hint=_context_hint(evidence_bus)
    base={"architecture":ARCHITECTURE,"question":QUESTION,"trade_decision_authority":False,"decision_authority":"E9_ONLY","decision":None,"gate":None,"score":None,"contextual_direction_hint":hint,"context_used":{e:bool((evidence_bus or {}).get(e)) for e in ("E1","E2","E3")},"evidence":{"raw_market_data_used":True,"decisions_used":False,"gates_used":False,"scores_used":False}}
    if len(bars)<MIN_BARS or atr<=0:
        return {**base,"state":"UNAVAILABLE","analysis_status":"INCOMPLETE","finding":"LIQUIDITY_DATA_INSUFFICIENT","direction":"NEUTRAL","directional_implication":"NEUTRAL","confidence":0.0,"evidence_strength":0.0,"observations":[],"liquidity_map":{},"event":{"type":"LIQUIDITY_DATA_INSUFFICIENT","liquidity_state":"UNRESOLVED"},"auction":{"response":"UNRESOLVED","follow_through":False,"quality":"UNRESOLVED"},"interaction":{},"auction_state":"UNRESOLVED","reasons":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"conflicts":[],"missing_evidence":["CLOSED_CANDLE_HISTORY"]}
    hi,lo=_pivots(bars); tol=max(atr*0.15,1e-9); current=len(bars)-1
    highs=[_consumption(z,bars,atr,current) for z in _cluster(hi[-60:],tol,current,"HIGH")]
    lows=[_consumption(z,bars,atr,current) for z in _cluster(lo[-60:],tol,current,"LOW")]
    event=None
    for i in range(max(0,current-2),current+1):
        candidate=_find_event(bars,highs,lows,atr,i)
        if candidate:
            event=candidate
    if event is None:
        event={"type":"NO_CONFIRMED_LIQUIDITY_EVENT","direction":"NEUTRAL","taker":"UNCLEAR","liquidity_state":"UNRESOLVED","zone":None,"index":current,"strength":0.25}
    auction=_auction(event,bars,atr)
    confirmed=auction["quality"]=="CONFIRMED"
    direction=event["direction"] if confirmed else "NEUTRAL"
    reasons=[]
    if event["zone"] is not None:
        reasons += ["LIQUIDITY_EVENT_DETECTED",f"TAKER={event['taker']}",f"AUCTION_{auction['response']}"]
        if not confirmed:
            reasons.append("AUCTION_RESPONSE_NOT_CONFIRMED")
    else:
        reasons.append("NO_CONFIRMED_EVENT")
    return {**base,"state":"ANALYSIS_COMPLETE","analysis_status":"COMPLETE","finding":event["type"],"direction":direction,"directional_implication":direction,"confidence":event["strength"] if confirmed else min(event["strength"],0.45),"evidence_strength":event["strength"],"observations":[f"closed_candles={len(bars)}",f"atr14={atr:.6f}",f"high_liquidity_zones={len(highs)}",f"low_liquidity_zones={len(lows)}",f"event={event['type']}",f"taker={event['taker']}",f"auction={auction['response']}",f"follow_through={auction['follow_through']}",f"contextual_direction={hint}"],"liquidity_map":{"high_zones":highs,"low_zones":lows,"fresh_high_zones":sum(z["fresh"] and z["state"] in {"FRESH","TAKEN"} for z in highs),"fresh_low_zones":sum(z["fresh"] and z["state"] in {"FRESH","TAKEN"} for z in lows)},"event":event,"auction":auction,"interaction":{"rejection":"REJECTION" in auction["response"],"acceptance":"ACCEPTANCE" in auction["response"],"failed_break_reclaim":"FAILED_BREAK" in event["type"],"taker":event["taker"]},"auction_state":auction["response"],"reasons":reasons,"conflicts":[],"missing_evidence":[] if confirmed else ["CONFIRMED_AUCTION_RESPONSE"]}

__all__=["analyze_e4"]
