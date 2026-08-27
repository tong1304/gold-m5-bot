from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

NAME = "Liquidity & Auction Brain"
QUESTION = "Where is liquidity, who interacted with it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_BRAIN"
MIN_BARS = 40


def _valid_bars(snapshot: Any) -> list[dict[str, float]]:
    raw = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    out = []
    for b in raw:
        try:
            x = {k: float(b[k]) for k in ("open", "high", "low", "close")}
            if not all(isfinite(v) for v in x.values()) or x["high"] < max(x["open"], x["close"]) or x["low"] > min(x["open"], x["close"]) or x["high"] < x["low"]:
                continue
            out.append(x)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _atr(bars, period=14):
    if len(bars) < 2: return 0.0
    tr=[]
    for i in range(1, len(bars)):
        b,p=bars[i],bars[i-1]
        tr.append(max(b["high"]-b["low"], abs(b["high"]-p["close"]), abs(b["low"]-p["close"])))
    return mean(tr[-period:])


def _pivots_before(bars, end, wing=2):
    highs=[]; lows=[]
    for i in range(wing, max(wing, end-wing)):
        w=bars[i-wing:i+wing+1]
        if len(w)==2*wing+1:
            if bars[i]["high"] >= max(x["high"] for x in w): highs.append((i,bars[i]["high"]))
            if bars[i]["low"] <= min(x["low"] for x in w): lows.append((i,bars[i]["low"]))
    return highs,lows


def _nearest(levels, price, atr, side):
    candidates=[x for x in levels if (x[1] >= price if side=="HIGH" else x[1] <= price)]
    if not candidates: return None
    return min(candidates, key=lambda x: abs(x[1]-price))


def _event(bars, atr, highs, lows):
    i=len(bars)-1; b=bars[i]; rng=max(b["high"]-b["low"],1e-9)
    body=abs(b["close"]-b["open"])/rng
    upper=(b["high"]-max(b["open"],b["close"])) / rng
    lower=(min(b["open"],b["close"])-b["low"]) / rng
    candidates=[]
    for side, levels in (("HIGH",highs),("LOW",lows)):
        level=_nearest(levels,b["close"],atr,side)
        if not level: continue
        p=level[1]
        if side=="HIGH":
            sweep=b["high"]>p+0.05*atr
            rejection=sweep and b["close"]<=p+0.10*atr and upper>=0.25
            acceptance=b["close"]>p+0.15*atr and body>=0.50
            if rejection: candidates.append(("HIGH_SWEEP_REJECTION","DOWN","BUYERS",p,.90,"REJECTION"))
            elif acceptance: candidates.append(("HIGH_ACCEPTANCE_CANDIDATE","UP","BUYERS",p,.82,"ACCEPTANCE"))
        else:
            sweep=b["low"]<p-0.05*atr
            rejection=sweep and b["close"]>=p-0.10*atr and lower>=0.25
            acceptance=b["close"]<p-0.15*atr and body>=0.50
            if rejection: candidates.append(("LOW_SWEEP_REJECTION","UP","SELLERS",p,.90,"REJECTION"))
            elif acceptance: candidates.append(("LOW_ACCEPTANCE_CANDIDATE","DOWN","SELLERS",p,.82,"ACCEPTANCE"))
    if not candidates:
        return {"type":"NO_CONFIRMED_LIQUIDITY_EVENT","direction":"NEUTRAL","taker":"UNCLEAR","level":None,"strength":.20,"auction":"UNRESOLVED"}
    kind,direction,taker,level,strength,auction=max(candidates,key=lambda x:x[4])
    return {"type":kind,"direction":direction,"taker":taker,"level":level,"strength":strength,"auction":auction}


def analyze_e4(snapshot=None, evidence_bus=None):
    bars=_valid_bars(snapshot); atr=_atr(bars)
    base={"architecture":ARCHITECTURE,"role":"LIQUIDITY_ANALYST","question":QUESTION,"trade_decision_authority":False,"decision_authority":"E9_ONLY","decision":None}
    if len(bars)<MIN_BARS or atr<=0:
        return {**base,"analysis_status":"INCOMPLETE","finding":"LIQUIDITY_DATA_INSUFFICIENT","direction":"NEUTRAL","confidence":0.0,"evidence":[],"counter_evidence":["INSUFFICIENT_DATA"],"invalidation":["NEW_CLOSED_CANDLE_DATA"],"reasons":["INSUFFICIENT_CLOSED_CANDLE_DATA"],"missing_evidence":["CONFIRMED_PIVOTS"]}
    highs,lows=_pivots_before(bars,len(bars)-1)
    event=_event(bars,atr,highs,lows)
    evidence=[f"confirmed_high_pivots={len(highs)}",f"confirmed_low_pivots={len(lows)}",f"atr14={atr:.6f}",f"event={event['type']}"]
    counter=[]
    if event["direction"]=="NEUTRAL": counter.append("NO_DIRECTIONAL_LIQUIDITY_PROOF")
    elif event["auction"]=="REJECTION": counter.append("AUCTION_REJECTION_REQUIRES_FOLLOW_THROUGH")
    elif event["auction"]=="ACCEPTANCE": counter.append("ACCEPTANCE_IS_CANDIDATE_NOT_EXECUTION_CONFIRMATION")
    return {**base,"analysis_status":"COMPLETE","finding":event["type"],"direction":event["direction"],"confidence":event["strength"],"evidence":evidence,"counter_evidence":counter,"invalidation":["price closes materially through the identified liquidity level","newer confirmed liquidity event supersedes the current event"],"event":event,"liquidity_map":{"high_pivots":highs[-20:],"low_pivots":lows[-20:]},"auction_state":event["auction"],"reasons":[] if event["direction"]!="NEUTRAL" else ["NO_CONFIRMED_EVENT"]}


__all__=["analyze_e4"]
