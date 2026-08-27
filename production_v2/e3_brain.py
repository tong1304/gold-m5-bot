from __future__ import annotations

"""E3 — single professional market-structure brain.

No runtime 3A-3F sub-engines.  The brain independently reconstructs price
structure from closed OHLC candles, then exposes evidence for downstream
engines.  It never makes an execution decision.
"""
from typing import Any


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs=[]
    for i in range(1, len(bars)):
        h,l,pc=bars[i]["high"],bars[i]["low"],bars[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    window=trs[-period:]
    return sum(window)/len(window) if window else 0.0


def _pivots(bars: list[dict[str, float]], side: str, radius: int = 2) -> list[tuple[int,float]]:
    out=[]
    if len(bars) < radius*2+1:
        return out
    for i in range(radius, len(bars)-radius):
        v=bars[i][side]
        left=[bars[j][side] for j in range(i-radius,i)]
        right=[bars[j][side] for j in range(i+1,i+radius+1)]
        if (v > max(left) and v >= max(right)) if side == "high" else (v < min(left) and v <= min(right)):
            out.append((i,v))
    return out


def _compress(points: list[tuple[int,float]], atr: float, min_spacing: int = 2) -> list[tuple[int,float]]:
    if not points:
        return []
    result=[points[0]]
    for p in points[1:]:
        prev=result[-1]
        if p[0]-prev[0] < min_spacing:
            # Keep the more meaningful extreme when pivots cluster.
            if abs(p[1]-prev[1]) >= max(atr*0.15, 1e-12):
                result[-1]=p
        else:
            result.append(p)
    return result


def _labels(points: list[tuple[int,float]], kind: str, atr: float) -> list[dict[str, Any]]:
    out=[]
    for i,(idx,val) in enumerate(points):
        label="UNCLASSIFIED"
        if i:
            delta=val-points[i-1][1]
            if kind == "HIGH": label="HH" if delta > max(atr*0.10,0.0) else "EQH"
            else: label="HL" if delta > max(atr*0.10,0.0) else "EQL" if abs(delta) <= max(atr*0.10,0.0) else "LL"
        out.append({"index":idx,"price":val,"label":label})
    return out


def _structure(highs: list[dict[str,Any]], lows: list[dict[str,Any]]) -> tuple[str,str,float]:
    hl=[x["label"] for x in highs[-4:]]; ll=[x["label"] for x in lows[-4:]]
    bull=sum(x in {"HH"} for x in hl)+sum(x in {"HL"} for x in ll)
    bear=sum(x in {"LH"} for x in hl)+sum(x in {"LL"} for x in ll)
    if bull >= 2 and bull > bear: return "BULLISH","CONTINUATION",min(1.0,0.55+0.10*bull)
    if bear >= 2 and bear > bull: return "BEARISH","CONTINUATION",min(1.0,0.55+0.10*bear)
    if bull and bear: return "MIXED","TRANSITION",0.50
    return "NEUTRAL","RANGE_OR_INSUFFICIENT",0.40


def _bos(bars: list[dict[str,float]], highs: list[dict[str,Any]], lows: list[dict[str,Any]], atr: float) -> dict[str,Any]:
    if not bars or atr <= 0: return {"event":"NO_BOS","direction":"NEUTRAL","confirmed":False}
    last=len(bars)-1; close=bars[-1]["close"]
    candidates=[]
    for h in highs:
        if h["index"] < last and h["label"] in {"HH","EQH","UNCLASSIFIED"}:
            candidates.append((h["index"],h["price"],"UP"))
    for l in lows:
        if l["index"] < last and l["label"] in {"LL","EQL","UNCLASSIFIED"}:
            candidates.append((l["index"],l["price"],"DOWN"))
    if not candidates: return {"event":"NO_BOS","direction":"NEUTRAL","confirmed":False}
    candidates.sort(key=lambda x:x[0], reverse=True)
    for idx,level,direction in candidates:
        if direction=="UP" and close > level and close-level >= atr*0.05:
            return {"event":"CONFIRMED_BOS","direction":"UP","confirmed":True,"level":level,"swing_index":idx,"break_distance_atr":(close-level)/atr}
        if direction=="DOWN" and close < level and level-close >= atr*0.05:
            return {"event":"CONFIRMED_BOS","direction":"DOWN","confirmed":True,"level":level,"swing_index":idx,"break_distance_atr":(level-close)/atr}
    return {"event":"NO_BOS","direction":"NEUTRAL","confirmed":False}


def _failure(bars: list[dict[str,float]], bos: dict[str,Any], atr: float) -> dict[str,Any]:
    if not bos.get("confirmed") or len(bars)<2: return {"event":"NO_FAILURE","confirmed":False}
    level=float(bos["level"]); last=bars[-1]
    # A confirmed close beyond structure that immediately closes back through it
    # is treated as failure only when the same closed candle rejects the level.
    if bos["direction"]=="UP" and last["close"] <= level and last["high"] > level:
        return {"event":"FAILED_BOS","direction":"DOWN","confirmed":True,"level":level}
    if bos["direction"]=="DOWN" and last["close"] >= level and last["low"] < level:
        return {"event":"FAILED_BOS","direction":"UP","confirmed":True,"level":level}
    return {"event":"NO_FAILURE","confirmed":False}


def analyze_e3(bars: list[dict[str,float]]) -> dict[str,Any]:
    clean=bars[-200:]
    atr=_atr(clean)
    if len(clean)<9 or atr<=0:
        return {"architecture":"E3_SINGLE_PROFESSIONAL_BRAIN_V1","analysis_status":"INSUFFICIENT_DATA","structure_state":"INSUFFICIENT_DATA","direction":"NEUTRAL","bos":{"event":"NO_BOS","confirmed":False},"failure":{"event":"NO_FAILURE","confirmed":False},"confidence":0.0,"evidence":[],"reason_codes":["E3_INSUFFICIENT_DATA"]}
    highs=_compress(_pivots(clean,"high"),atr); lows=_compress(_pivots(clean,"low"),atr)
    high_labels=_labels(highs,"HIGH",atr); low_labels=_labels(lows,"LOW",atr)
    direction,state,base_conf=_structure(high_labels,low_labels)
    bos=_bos(clean,high_labels,low_labels,atr)
    failure=_failure(clean,bos,atr)
    if bos["confirmed"]: direction=bos["direction"]; state="BREAKOUT_CONFIRMED"
    if failure["confirmed"]: direction=failure["direction"]; state="STRUCTURE_FAILURE"
    # External structure uses the widest meaningful pivots; internal uses the
    # most recent pivots. This is descriptive, not a second runtime engine.
    ext_high=high_labels[-2:]; ext_low=low_labels[-2:]
    int_high=high_labels[-4:]; int_low=low_labels[-4:]
    structural_events=sum(x in {"HH","HL","LH","LL"} for x in [*(h["label"] for h in high_labels[-4:]),*(l["label"] for l in low_labels[-4:])])
    strength=min(1.0,0.35+0.08*structural_events+(0.20 if bos["confirmed"] else 0.0)-(0.15 if failure["confirmed"] else 0.0))
    confidence=max(0.0,min(1.0,0.65*base_conf+0.35*strength))
    evidence=[
        f"closed_candles={len(clean)}",f"atr14={atr:.6f}",
        f"structure_state={state}",f"structure_direction={direction}",
        f"confirmed_swing_high={high_labels[-1]['price']:.6f}" if high_labels else "confirmed_swing_high=None",
        f"confirmed_swing_low={low_labels[-1]['price']:.6f}" if low_labels else "confirmed_swing_low=None",
        f"bos={bos['event']}",f"bos_direction={bos.get('direction','NEUTRAL')}",
        f"failure={failure['event']}",f"internal_swings={len(int_high)+len(int_low)}",f"external_swings={len(ext_high)+len(ext_low)}",
    ]
    reasons=[]
    if not bos["confirmed"]: reasons.append("NO_CONFIRMED_BOS")
    if failure["confirmed"]: reasons.append("STRUCTURE_FAILURE_DETECTED")
    if direction=="MIXED": reasons.append("STRUCTURE_CONFLICT")
    return {
        "architecture":"E3_SINGLE_PROFESSIONAL_BRAIN_V1","analysis_status":"COMPLETE",
        "question":"What is price structure communicating?","structure_state":state,
        "direction":direction,"internal_structure":{"highs":int_high,"lows":int_low},
        "external_structure":{"highs":ext_high,"lows":ext_low},
        "swing_map":{"highs":high_labels,"lows":low_labels},"bos":bos,"failure":failure,
        "structure_strength":round(strength,4),"confidence":round(confidence,4),
        "evidence":evidence,"reason_codes":reasons,"decision_authority":"E9_ONLY",
        "trade_decision_authority":False,"gate":None,"sub_engines_active":False,
        "sub_engines_status":"PAUSED","upstream_direction_used":False,
    }
