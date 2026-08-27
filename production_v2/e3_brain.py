from __future__ import annotations

"""E3 — Professional Market Structure Brain.

Single brain: price structure only. E3 never consumes upstream direction,
decision, gate or trade score. E9 remains the sole trade-decision authority.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V3"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 20
INTERNAL_RADIUS = 2
EXTERNAL_RADIUS = 5
PROMINENCE_ATR = 0.10
BOS_DISTANCE_ATR = 0.10
BOS_BODY_ATR = 0.20
FAILURE_CLOSE_ATR = 0.05
EQ_TOLERANCE_ATR = 0.10


def _num(v: Any):
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _clean_bars(bars):
    out, reasons = [], []
    for i, b in enumerate(bars or []):
        if not isinstance(b, dict):
            reasons.append(f"bar_{i}_not_mapping"); continue
        vals = [_num(b.get(k)) for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            reasons.append(f"bar_{i}_ohlc_invalid"); continue
        o, h, l, c = vals
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent"); continue
        out.append({"open": o, "high": h, "low": l, "close": c})
    return out, reasons


def _atr(bars, period=14):
    if len(bars) < 2: return 0.0
    prev, trs = bars[0]["close"], []
    for b in bars[1:]:
        trs.append(max(b["high"]-b["low"], abs(b["high"]-prev), abs(b["low"]-prev)))
        prev = b["close"]
    return mean(trs[-period:]) if trs else 0.0


def _atr_at(bars, i, period=14):
    if i < 1: return 0.0
    trs = []
    for j in range(max(1, i-period+1), i+1):
        b, p = bars[j], bars[j-1]["close"]
        trs.append(max(b["high"]-b["low"], abs(b["high"]-p), abs(b["low"]-p)))
    return mean(trs) if trs else 0.0


def _pivots(bars, side, radius=2):
    pts = []
    if len(bars) < 2*radius+1: return pts
    for i in range(radius, len(bars)-radius):
        x = bars[i][side]
        left = [bars[j][side] for j in range(i-radius, i)]
        right = [bars[j][side] for j in range(i+1, i+radius+1)]
        a = max(_atr_at(bars, i), 1e-12)
        if side == "high" and x >= max(left) and x > max(right) and min(x-max(left), x-max(right)) >= PROMINENCE_ATR*a:
            pts.append((i, x))
        elif side == "low" and x <= min(left) and x < min(right) and min(min(left)-x, min(right)-x) >= PROMINENCE_ATR*a:
            pts.append((i, x))
    return pts


def _compress(points, atr, side="high", spacing=2):
    out, tol = [], max(atr*EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0]-out[-1][0] >= spacing:
            out.append(p); continue
        if abs(p[1]-out[-1][1]) <= tol: continue
        if side == "high" and p[1] > out[-1][1]: out[-1] = p
        elif side == "low" and p[1] < out[-1][1]: out[-1] = p
    return out


def _label(points, kind, atr):
    out, tol = [], max(atr*EQ_TOLERANCE_ATR, 1e-12)
    for i, (idx, price) in enumerate(points):
        if i == 0: label = "SWING_HIGH" if kind == "HIGH" else "SWING_LOW"
        else:
            d = price-points[i-1][1]
            if abs(d) <= tol: label = "EQH" if kind == "HIGH" else "EQL"
            elif kind == "HIGH": label = "HH" if d > 0 else "LH"
            else: label = "HL" if d > 0 else "LL"
        out.append({"index": idx, "price": round(price, 8), "label": label})
    return out


def _structure_direction(highs, lows):
    h = next((x["label"] for x in reversed(highs) if x["label"] in {"HH","LH"}), None)
    l = next((x["label"] for x in reversed(lows) if x["label"] in {"HL","LL"}), None)
    if h == "HH" and l == "HL": return UP
    if h == "LH" and l == "LL": return DOWN
    return MIXED if h and l else NEUTRAL


def _structure_counts(highs, lows):
    c = {"HH":0,"HL":0,"LH":0,"LL":0}
    for x in highs[-6:]+lows[-6:]:
        if x["label"] in c: c[x["label"]] += 1
    bull, bear = c["HH"]+c["HL"], c["LH"]+c["LL"]
    state = UP if bull >= 2 and bull > bear+1 else DOWN if bear >= 2 and bear > bull+1 else MIXED if bull or bear else NEUTRAL
    return state, c


def _latest_break_candidates(highs, lows, latest_index):
    # Only historical pivots can be break levels; the pivot detector itself
    # excludes the live edge by its radius. latest_index is retained for API
    # compatibility and fixture compatibility.
    out = []
    if highs: out.append((float(highs[-1]["price"]), int(highs[-1]["index"]), UP))
    if lows: out.append((float(lows[-1]["price"]), int(lows[-1]["index"]), DOWN))
    return out


def _candle_break_quality(bar, level, direction, atr):
    if atr <= 0: return {"valid":False,"distance_atr":0.0,"body_atr":0.0,"close_location":0.5}
    rng = max(bar["high"]-bar["low"], 1e-12)
    body = abs(bar["close"]-bar["open"])
    loc = (bar["close"]-bar["low"])/rng
    distance = (bar["close"]-level) if direction == UP else (level-bar["close"])
    body_atr = body/atr
    close_ok = distance >= BOS_DISTANCE_ATR*atr
    directional_close = loc >= 0.55 if direction == UP else loc <= 0.45
    displacement_ok = body_atr >= BOS_BODY_ATR or directional_close
    return {"valid":bool(close_ok and displacement_ok),"distance_atr":round(max(0,distance/atr),4),"body_atr":round(body_atr,4),"close_location":round(loc,4),"close_beyond_level":bool(close_ok),"displacement_ok":bool(displacement_ok)}


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    if atr <= 0 or not bars: return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}
    candidates=[]
    for level, idx, direction in _latest_break_candidates(highs,lows,len(bars)-1):
        q=_candle_break_quality(bars[-1],level,direction,atr)
        if not q["valid"]: continue
        event="CONFIRMED_CHOCH" if prior_structure in {UP,DOWN} and direction != prior_structure else "CONFIRMED_BOS"
        candidates.append({"event":event,"direction":direction,"confirmed":True,"scope":scope,"level":round(level,8),"swing_index":idx,"break_candle_index":len(bars)-1,**{k:q[k] for k in ("distance_atr","body_atr","close_location","displacement_ok")}})
    if len(candidates)==1:
        x=candidates[0]; x["break_distance_atr"]=x.pop("distance_atr"); x["break_body_atr"]=x.pop("body_atr"); x["close_beyond_level"]=True; return x
    if len(candidates)>1: return {"event":"CONFLICTING_BREAKS","direction":MIXED,"confirmed":False,"scope":scope,"candidates":candidates}
    return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}


def _sweep_failure(bars, highs, lows):
    if not bars: return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}
    b=bars[-1]; f=[]
    for level,idx,d in _latest_break_candidates(highs,lows,len(bars)-1):
        if d==UP and b["high"]>level and b["close"]<level: f.append({"event":"FAILED_BREAK","direction":DOWN,"confirmed":True,"level":round(level,8),"swing_index":idx,"failure_candle_index":len(bars)-1,"scope":"EXTERNAL"})
        elif d==DOWN and b["low"]<level and b["close"]>level: f.append({"event":"FAILED_BREAK","direction":UP,"confirmed":True,"level":round(level,8),"swing_index":idx,"failure_candle_index":len(bars)-1,"scope":"EXTERNAL"})
    return f[0] if len(f)==1 else {"event":"CONFLICTING_FAILURES","direction":MIXED,"confirmed":False} if f else {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}


def _slope_direction(bars, lookback=20):
    c=[b["close"] for b in bars[-lookback:]]
    if len(c)<5: return NEUTRAL,0.0
    n=(c[-1]-c[0])/(max(_atr(bars),1e-12)*max(len(c)-1,1)); q=min(1,abs(n)*8)
    return (UP if n>0.035 else DOWN if n<-0.035 else NEUTRAL),q


def _strength(external, internal, bos, failure, swings, conflicts):
    # Confidence is based on structural agreement/events, not on the raw
    # number of detected pivots. A noisy chart must not score higher merely
    # because it contains more micro-swings.
    s=.25 + (.25 if external in {UP,DOWN} else 0)
    if internal==external and internal in {UP,DOWN}: s += .22
    elif internal in {UP,DOWN} and external in {UP,DOWN}: s += .08
    elif internal==MIXED: s += .02
    if bos.get("confirmed"):
        s += min(.20,.08+float(bos.get("break_distance_atr",0))*.04)
        s += .05 if bos.get("displacement_ok") else 0
    if failure.get("confirmed"): s-=.18
    return round(max(0,min(1,s-min(.20,len(conflicts)*.07))),4)


def analyze_e3(bars):
    clean,data_reasons=_clean_bars(bars)
    base={"architecture":ARCHITECTURE,"reasoning_role":"MARKET_STRUCTURE_ANALYST","question":QUESTION,"decision":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"sub_engines_active":False,"sub_engines_status":"PAUSED","specialists_active":False,"specialists_status":"PAUSED","upstream_direction_used":False,"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False}
    if len(clean)<MIN_CANDLES:
        return {**base,"analysis_status":"INSUFFICIENT_DATA","finding":"STRUCTURE_INSUFFICIENT_DATA","structure":"UNKNOWN","structure_state":"INSUFFICIENT_DATA","direction":NEUTRAL,"directional_bias":NEUTRAL,"structural_bias":NEUTRAL,"swing_map":{"highs":[],"lows":[]},"internal_structure":{},"external_structure":{},"bos":{"event":"NO_BOS","direction":NEUTRAL,"confirmed":False},"failure":{"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False},"BOS":"NONE","BOS_type":"NONE","structural_failure":"NONE","failure_type":"NONE","strength":0.0,"structure_strength":0.0,"confidence":0.0,"evidence":[],"observations":[],"conflicts":[],"reason_codes":["E3_INSUFFICIENT_DATA",*data_reasons[:4]],"reasons":["E3_INSUFFICIENT_DATA",*data_reasons[:4]],"reasoning_trace":{"closed_candles":len(clean)}}
    atr=_atr(clean)
    ih=_label(_compress(_pivots(clean,"high",INTERNAL_RADIUS),atr,"high"),"HIGH",atr); il=_label(_compress(_pivots(clean,"low",INTERNAL_RADIUS),atr,"low"),"LOW",atr)
    eh=_label(_compress(_pivots(clean,"high",EXTERNAL_RADIUS),atr,"high"),"HIGH",atr); el=_label(_compress(_pivots(clean,"low",EXTERNAL_RADIUS),atr,"low"),"LOW",atr)
    idef=_structure_direction(ih,il); edef=_structure_direction(eh,el); ist,ic=_structure_counts(ih,il); est,ec=_structure_counts(eh,el)
    slope,slope_q=_slope_direction(clean); eb=_bos(clean,eh,el,atr,edef,"EXTERNAL"); ib=_bos(clean,ih,il,atr,idef,"INTERNAL"); failure=_sweep_failure(clean,eh,el)
    conflicts=[]
    if edef in {UP,DOWN} and idef in {UP,DOWN} and edef!=idef: conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if slope in {UP,DOWN} and edef not in {slope,NEUTRAL}: conflicts.append("SLOPE_NOT_STRUCTURAL_AUTHORITY")
    if failure.get("confirmed"): direction,state,finding=failure["direction"],"STRUCTURE_FAILURE","FAILED_BREAK"
    elif eb.get("confirmed"):
        direction=eb["direction"]; state="CHANGE_OF_CHARACTER" if eb["event"]=="CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"; finding=("BULLISH_CHOCH" if direction==UP else "BEARISH_CHOCH") if state=="CHANGE_OF_CHARACTER" else ("BULLISH_BOS" if direction==UP else "BEARISH_BOS")
    elif edef in {UP,DOWN}:
        direction=edef; state="CONTINUATION" if idef==edef else "INTERNAL_CONFLICT" if idef==MIXED else "INTERNAL_COUNTER_MOVE"; finding="BULLISH_STRUCTURE" if direction==UP and state=="CONTINUATION" else "BEARISH_STRUCTURE" if direction==DOWN and state=="CONTINUATION" else ("BULLISH_EXTERNAL_MIXED_INTERNAL" if direction==UP else "BEARISH_EXTERNAL_MIXED_INTERNAL") if state=="INTERNAL_CONFLICT" else ("BULLISH_EXTERNAL_COUNTERMOVE" if direction==UP else "BEARISH_EXTERNAL_COUNTERMOVE")
    elif idef in {UP,DOWN}: direction,state,finding=idef,"DEVELOPING_STRUCTURE",("BULLISH_DEVELOPING_STRUCTURE" if idef==UP else "BEARISH_DEVELOPING_STRUCTURE")
    elif idef==MIXED or edef==MIXED: direction,state,finding=MIXED,"TRANSITION","MIXED_STRUCTURE"
    else: direction,state,finding=(MIXED if slope in {UP,DOWN} else NEUTRAL),("DIRECTIONAL_CONTEXT_UNCONFIRMED" if slope in {UP,DOWN} else "RANGE_OR_UNCLEAR"),("DIRECTIONAL_CONTEXT_UNCONFIRMED" if slope in {UP,DOWN} else "NO_CONFIRMED_STRUCTURE_EVENT")
    if not eb.get("confirmed"): conflicts.append("NO_CONFIRMED_EXTERNAL_BOS")
    if ib.get("confirmed") and not eb.get("confirmed"): conflicts.append("INTERNAL_BREAK_ONLY")
    if failure.get("confirmed"): conflicts.append("FAILED_BREAK_DETECTED")
    if eb.get("event")=="CONFIRMED_CHOCH": conflicts.append("CHANGE_OF_CHARACTER_DETECTED")
    if edef==MIXED or idef==MIXED: conflicts.append("STRUCTURE_CONFLICT")
    if not eh or not el: conflicts.append("LIMITED_EXTERNAL_SWINGS")
    conflicts=list(dict.fromkeys(conflicts))
    strength=_strength(edef,idef,eb,failure,len(ih)+len(il)+len(eh)+len(el),conflicts); confidence=round(min(1,.28+strength*.58+(.06 if edef==idef and edef in {UP,DOWN} else 0)),4)
    bias=direction if direction in {UP,DOWN} else NEUTRAL
    obs=[f"closed_candles={len(clean)}",f"atr14={atr:.8f}",f"external_structure={edef}",f"internal_structure={idef}",f"external_count_state={est}",f"internal_count_state={ist}",f"slope_context={slope}",f"slope_quality={slope_q:.4f}",f"external_bos={eb['event']}",f"internal_bos={ib['event']}",f"failure={failure['event']}",f"internal_swing_count={len(ih)+len(il)}",f"external_swing_count={len(eh)+len(el)}",f"structure_strength={strength:.4f}"]
    if eb.get("confirmed"): obs += [f"bos_level={eb['level']}",f"bos_break_distance_atr={eb['break_distance_atr']}",f"bos_break_body_atr={eb['break_body_atr']}",f"bos_displacement_ok={eb['displacement_ok']}"]
    recent_high=max(x["high"] for x in clean[-30:]); recent_low=min(x["low"] for x in clean[-30:]); prior=clean[-60:-30] if len(clean)>=60 else clean[:-30]
    prior_high=max((x["high"] for x in prior),default=recent_high); prior_low=min((x["low"] for x in prior),default=recent_low)
    trace={"closed_candles":len(clean),"atr_period":14,"internal_pivot_window":INTERNAL_RADIUS,"external_pivot_window":EXTERNAL_RADIUS,"pivot_prominence_atr":PROMINENCE_ATR,"bos_close_distance_atr":BOS_DISTANCE_ATR,"bos_body_atr":BOS_BODY_ATR,"wick_only_break_is_bos":False,"external_structure_is_authority":True,"slope_is_structural_authority":False,"internal_structure":idef,"external_structure":edef,"internal_state":idef,"external_state":edef,"internal_count_state":ist,"external_count_state":est,"internal_bos":ib,"external_bos":eb,"failure":failure,"upstream_data_consumed":False,"decision_authority":"E9_ONLY"}
    return {**base,"analysis_status":"COMPLETE","finding":finding,"structure":direction if direction in {UP,DOWN} else MIXED if state=="TRANSITION" else NEUTRAL,"structure_state":state,"direction":direction,"directional_bias":bias,"structural_bias":bias,"internal_structure":{"state":idef,"count_state":ist,"counts":ic,"labels":ih[-8:]+il[-8:]},"external_structure":{"state":edef,"count_state":est,"counts":ec,"labels":eh[-8:]+el[-8:]},"swing_map":{"highs":eh[-8:],"lows":el[-8:]},"HH":ec["HH"],"HL":ec["HL"],"LH":ec["LH"],"LL":ec["LL"],"BOS":finding if eb.get("confirmed") else "NONE","bos":eb,"BOS_type":eb.get("event","NO_BOS"),"bos_type":eb.get("event","NO_BOS"),"BOS_level":eb.get("level"),"bos_level":eb.get("level"),"BOS_candle_index":eb.get("break_candle_index"),"structural_failure":failure.get("event","NO_FAILURE"),"failure_type":failure.get("event","NO_FAILURE"),"failure_level":failure.get("level"),"failure":failure,"strength":strength,"structure_strength":strength,"confidence":confidence,"recent_high":round(recent_high,8),"recent_low":round(recent_low,8),"prior_high":round(prior_high,8),"prior_low":round(prior_low,8),"atr":round(atr,8),"protected_high":eh[-1] if eh else None,"protected_low":el[-1] if el else None,"conflicts":conflicts,"evidence":obs,"observations":obs,"reason_codes":conflicts,"reasons":conflicts,"reasoning_trace":trace}
