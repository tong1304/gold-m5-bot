from __future__ import annotations

"""E3 single professional market-structure brain.

The former 3A-3F runtime modules are parked. This brain independently reads
closed OHLC candles and produces structural evidence only; it never executes
or approves a trade.
"""
from typing import Any


def _atr(bars: list[dict[str,float]], period: int = 14) -> float:
    if len(bars) < 2: return 0.0
    trs=[max(bars[i]["high"]-bars[i]["low"],abs(bars[i]["high"]-bars[i-1]["close"]),abs(bars[i]["low"]-bars[i-1]["close"])) for i in range(1,len(bars))]
    w=trs[-period:]
    return sum(w)/len(w) if w else 0.0


def _pivots(bars: list[dict[str,float]], side: str, radius: int = 2) -> list[tuple[int,float]]:
    out=[]
    for i in range(radius,len(bars)-radius):
        v=bars[i][side]; left=[bars[j][side] for j in range(i-radius,i)]; right=[bars[j][side] for j in range(i+1,i+radius+1)]
        ok=(v>max(left) and v>=max(right)) if side=="high" else (v<min(left) and v<=min(right))
        if ok: out.append((i,v))
    return out


def _compress(points, atr: float, min_spacing: int = 2):
    result=[]
    for p in points:
        if not result or p[0]-result[-1][0]>=min_spacing: result.append(p); continue
        if (p[1]-result[-1][1])*(1 if len(result)%2 else 1):
            # Replace clustered pivots with the later extreme; the side-specific
            # extreme is recovered by comparing absolute displacement from the prior pivot.
            if abs(p[1]-result[-1][1]) >= max(atr*0.10,1e-12): result[-1]=p
    return result


def _labels(points, kind: str, atr: float):
    out=[]; threshold=max(atr*0.10,1e-12)
    for i,(idx,val) in enumerate(points):
        label="UNCLASSIFIED"
        if i:
            delta=val-points[i-1][1]
            if abs(delta)<=threshold: label="EQH" if kind=="HIGH" else "EQL"
            elif kind=="HIGH": label="HH" if delta>0 else "LH"
            else: label="HL" if delta>0 else "LL"
        out.append({"index":idx,"price":val,"label":label})
    return out


def _structure(highs,lows):
    labels=[x["label"] for x in highs[-4:]+lows[-4:]]
    bull=sum(x in {"HH","HL"} for x in labels); bear=sum(x in {"LH","LL"} for x in labels)
    if bull>=3 and bull>bear: return "BULLISH","CONTINUATION",min(1.0,0.55+0.08*bull)
    if bear>=3 and bear>bull: return "BEARISH","CONTINUATION",min(1.0,0.55+0.08*bear)
    if bull and bear: return "MIXED","TRANSITION",0.50
    return "NEUTRAL","RANGE_OR_INSUFFICIENT",0.40


def _confirmed_bos(bars, highs, lows, atr):
    """Find the latest closed-candle structural break, not a wick-only break."""
    candidates=[(x["index"],x["price"],"UP") for x in highs]+[(x["index"],x["price"],"DOWN") for x in lows]
    candidates.sort(key=lambda x:x[0])
    latest=None
    for idx,level,direction in candidates:
        for j in range(idx+1,len(bars)):
            close=bars[j]["close"]
            if direction=="UP" and close>level and close-level>=atr*0.05:
                latest={"event":"CONFIRMED_BOS","direction":"UP","confirmed":True,"level":level,"swing_index":idx,"break_candle_index":j,"break_distance_atr":round((close-level)/atr,4)}
            elif direction=="DOWN" and close<level and level-close>=atr*0.05:
                latest={"event":"CONFIRMED_BOS","direction":"DOWN","confirmed":True,"level":level,"swing_index":idx,"break_candle_index":j,"break_distance_atr":round((level-close)/atr,4)}
    return latest or {"event":"NO_BOS","direction":"NEUTRAL","confirmed":False}


def _failure(bars,bos,atr):
    if not bos.get("confirmed"): return {"event":"NO_FAILURE","confirmed":False}
    level=float(bos["level"]); start=int(bos["break_candle_index"])
    for j in range(start+1,len(bars)):
        close=bars[j]["close"]
        if bos["direction"]=="UP" and close<level:
            return {"event":"FAILED_BOS","direction":"DOWN","confirmed":True,"level":level,"failure_candle_index":j}
        if bos["direction"]=="DOWN" and close>level:
            return {"event":"FAILED_BOS","direction":"UP","confirmed":True,"level":level,"failure_candle_index":j}
    return {"event":"NO_FAILURE","confirmed":False}


def analyze_e3(bars: list[dict[str,float]]) -> dict[str,Any]:
    clean=list(bars[-200:]); atr=_atr(clean)
    base={"architecture":"E3_SINGLE_PROFESSIONAL_BRAIN_V1","decision_authority":"E9_ONLY","trade_decision_authority":False,"gate":None,"sub_engines_active":False,"sub_engines_status":"PAUSED","upstream_direction_used":False}
    if len(clean)<20 or atr<=0:
        return {**base,"analysis_status":"INSUFFICIENT_DATA","structure_state":"INSUFFICIENT_DATA","direction":"NEUTRAL","internal_structure":{},"external_structure":{},"swing_map":{"highs":[],"lows":[]},"bos":{"event":"NO_BOS","confirmed":False},"failure":{"event":"NO_FAILURE","confirmed":False},"structure_strength":0.0,"confidence":0.0,"evidence":[f"closed_candles={len(clean)}"],"reason_codes":["E3_INSUFFICIENT_DATA"]}
    highs=_compress(_pivots(clean,"high"),atr); lows=_compress(_pivots(clean,"low"),atr)
    high_labels=_labels(highs,"HIGH",atr); low_labels=_labels(lows,"LOW",atr)
    direction,state,base_conf=_structure(high_labels,low_labels)
    bos=_confirmed_bos(clean,high_labels,low_labels,atr); failure=_failure(clean,bos,atr)
    if failure["confirmed"]: direction=failure["direction"]; state="STRUCTURE_FAILURE"
    elif bos["confirmed"]: direction=bos["direction"]; state="BREAKOUT_CONFIRMED"
    recent_high=high_labels[-4:]; recent_low=low_labels[-4:]
    external_high=high_labels[-2:]; external_low=low_labels[-2:]
    event_count=sum(x["label"] in {"HH","HL","LH","LL"} for x in recent_high+recent_low)
    strength=min(1.0,0.35+0.08*event_count+(0.20 if bos["confirmed"] else 0.0)-(0.15 if failure["confirmed"] else 0.0))
    confidence=max(0.0,min(1.0,0.65*base_conf+0.35*strength))
    evidence=[f"closed_candles={len(clean)}",f"atr14={atr:.6f}",f"structure_state={state}",f"structure_direction={direction}",f"bos={bos['event']}",f"bos_direction={bos.get('direction','NEUTRAL')}",f"failure={failure['event']}",f"internal_swing_count={len(recent_high)+len(recent_low)}",f"external_swing_count={len(external_high)+len(external_low)}"]
    if bos.get("confirmed"): evidence += [f"bos_level={bos['level']:.6f}",f"bos_break_candle={bos['break_candle_index']}"]
    reasons=[]
    if not bos["confirmed"]: reasons.append("NO_CONFIRMED_BOS")
    if failure["confirmed"]: reasons.append("STRUCTURE_FAILURE_DETECTED")
    if direction=="MIXED": reasons.append("STRUCTURE_CONFLICT")
    return {**base,"analysis_status":"COMPLETE","question":"What is price structure communicating?","structure_state":state,"direction":direction,"internal_structure":{"highs":recent_high,"lows":recent_low},"external_structure":{"highs":external_high,"lows":external_low},"swing_map":{"highs":high_labels,"lows":low_labels},"bos":bos,"failure":failure,"structure_strength":round(strength,4),"confidence":round(confidence,4),"evidence":evidence,"reason_codes":reasons}
