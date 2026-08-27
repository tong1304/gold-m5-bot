from __future__ import annotations
"""E3 — Professional Market Structure Brain.

E3 describes price structure only. It never consumes upstream decisions/gates/scores
and never makes a trade decision. E9 remains the sole trade-decision authority.
"""
from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V4"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 30
INTERNAL_RADIUS, EXTERNAL_RADIUS = 2, 5
PROMINENCE_ATR = 0.12
BOS_DISTANCE_ATR, BOS_BODY_ATR = 0.10, 0.20
FAILURE_CLOSE_ATR, FAILURE_SWEEP_ATR = 0.05, 0.10
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


def _pivots(bars, side, radius):
    pts = []
    for i in range(radius, len(bars)-radius):
        x = bars[i][side]
        left = [bars[j][side] for j in range(i-radius, i)]
        right = [bars[j][side] for j in range(i+1, i+radius+1)]
        prominence = PROMINENCE_ATR * max(_atr_at(bars, i), 1e-12)
        if side == "high" and x >= max(left) and x > max(right) and min(x-max(left), x-max(right)) >= prominence:
            pts.append((i, x))
        elif side == "low" and x <= min(left) and x < min(right) and min(min(left)-x, min(right)-x) >= prominence:
            pts.append((i, x))
    return pts


def _compress(points, atr, side, spacing=2):
    out, tol = [], max(atr*EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0]-out[-1][0] >= spacing:
            out.append(p); continue
        if abs(p[1]-out[-1][1]) <= tol:
            if side == "high" and p[1] > out[-1][1]: out[-1] = p
            elif side == "low" and p[1] < out[-1][1]: out[-1] = p
            continue
        if side == "high" and p[1] > out[-1][1]: out[-1] = p
        elif side == "low" and p[1] < out[-1][1]: out[-1] = p
    return out


def _label(points, kind, atr):
    out, tol = [], max(atr*EQ_TOLERANCE_ATR, 1e-12)
    previous = None
    for idx, price in points:
        if previous is None:
            label = "SWING_HIGH" if kind == "HIGH" else "SWING_LOW"
        else:
            d = price - previous[1]
            if abs(d) <= tol: label = "EQH" if kind == "HIGH" else "EQL"
            elif kind == "HIGH": label = "HH" if d > 0 else "LH"
            else: label = "HL" if d > 0 else "LL"
        item = {"index": int(idx), "price": round(float(price), 8), "label": label}
        out.append(item); previous = (idx, price)
    return out


def _state_from_latest(highs, lows):
    """Structure state from the latest meaningful high and low labels.
    Counts are deliberately not used as directional authority; they are evidence only.
    """
    h = next((x["label"] for x in reversed(highs) if x["label"] in {"HH", "LH"}), None)
    l = next((x["label"] for x in reversed(lows) if x["label"] in {"HL", "LL"}), None)
    if h == "HH" and l == "HL": return UP
    if h == "LH" and l == "LL": return DOWN
    return MIXED if h or l else NEUTRAL


def _counts(highs, lows):
    c = {"HH": 0, "HL": 0, "LH": 0, "LL": 0, "EQH": 0, "EQL": 0}
    for x in highs[-8:] + lows[-8:]:
        if x["label"] in c: c[x["label"]] += 1
    return c


def _count_state(c):
    bull = c["HH"] + c["HL"]
    bear = c["LH"] + c["LL"]
    if bull == 0 and bear == 0: return NEUTRAL
    if bull >= bear + 2: return UP
    if bear >= bull + 2: return DOWN
    return MIXED


def _sequence(highs, lows, limit=12):
    return sorted(highs + lows, key=lambda x: x["index"])[-limit:]


def _protected_levels(direction, highs, lows):
    if direction == UP:
        # The latest HL/EQL is the candidate protected low for bullish structure.
        low = next((x for x in reversed(lows) if x["label"] in {"HL", "EQL"}), None)
        high = next((x for x in reversed(highs) if x["label"] in {"HH", "EQH"}), None)
        return {"bullish_protected_low": low, "bearish_protected_high": high}
    if direction == DOWN:
        high = next((x for x in reversed(highs) if x["label"] in {"LH", "EQH"}), None)
        low = next((x for x in reversed(lows) if x["label"] in {"LL", "EQL"}), None)
        return {"bullish_protected_low": low, "bearish_protected_high": high}
    return {"bullish_protected_low": None, "bearish_protected_high": None}


def _break_quality(bar, level, direction, atr):
    if atr <= 0: return {"valid": False}
    rng = max(bar["high"]-bar["low"], 1e-12)
    body_atr = abs(bar["close"]-bar["open"])/atr
    loc = (bar["close"]-bar["low"])/rng
    distance = (bar["close"]-level) if direction == UP else (level-bar["close"])
    close_beyond = distance >= BOS_DISTANCE_ATR*atr
    directional_close = loc >= .55 if direction == UP else loc <= .45
    displacement = body_atr >= BOS_BODY_ATR or directional_close
    return {"valid": bool(close_beyond and displacement), "distance_atr": round(max(0,distance/atr),4), "body_atr": round(body_atr,4), "close_location": round(loc,4), "displacement_ok": bool(displacement)}


def _bos(bars, highs, lows, atr, prior_state, scope):
    if not bars or atr <= 0: return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}
    candidates = []
    # Only structurally protected levels can generate a BOS. This prevents arbitrary
    # recent pivots from turning every price extension into a structural event.
    protected = _protected_levels(prior_state, highs, lows)
    levels = []
    if prior_state == UP and protected.get("bearish_protected_high"):
        levels.append((protected["bearish_protected_high"], UP))
    elif prior_state == DOWN and protected.get("bullish_protected_low"):
        levels.append((protected["bullish_protected_low"], DOWN))
    else:
        if highs: levels.append((highs[-1], UP))
        if lows: levels.append((lows[-1], DOWN))
    for swing, direction in levels:
        q = _break_quality(bars[-1], swing["price"], direction, atr)
        if not q["valid"]: continue
        event = "CONFIRMED_CHOCH" if prior_state in {UP,DOWN} and direction != prior_state else "CONFIRMED_BOS"
        candidates.append({"event":event,"direction":direction,"confirmed":True,"scope":scope,"level":swing["price"],"swing_index":swing["index"],"swing_label":swing["label"],"break_candle_index":len(bars)-1,"break_distance_atr":q["distance_atr"],"break_body_atr":q["body_atr"],"close_location":q["close_location"],"displacement_ok":q["displacement_ok"],"close_beyond_level":True})
    if not candidates: return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}
    return candidates[0]


def _failure(bars, highs, lows, atr, prior_state):
    if not bars or atr <= 0: return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}
    b = bars[-1]; candidates=[]
    protected = _protected_levels(prior_state, highs, lows)
    levels=[]
    if protected.get("bearish_protected_high"): levels.append((protected["bearish_protected_high"], UP))
    if protected.get("bullish_protected_low"): levels.append((protected["bullish_protected_low"], DOWN))
    for swing, direction in levels:
        level=swing["price"]
        if direction==UP and b["high"]>level and b["close"]<level:
            sweep=(b["high"]-level)/atr; reclaim=(level-b["close"])/atr
            if sweep>=FAILURE_SWEEP_ATR and reclaim>=FAILURE_CLOSE_ATR:
                candidates.append({"event":"FAILED_BREAK","direction":DOWN,"confirmed":True,"level":level,"swing_index":swing["index"],"swing_label":swing["label"],"failure_candle_index":len(bars)-1,"scope":"EXTERNAL","sweep_distance_atr":round(sweep,4),"reclaim_distance_atr":round(reclaim,4)})
        elif direction==DOWN and b["low"]<level and b["close"]>level:
            sweep=(level-b["low"])/atr; reclaim=(b["close"]-level)/atr
            if sweep>=FAILURE_SWEEP_ATR and reclaim>=FAILURE_CLOSE_ATR:
                candidates.append({"event":"FAILED_BREAK","direction":UP,"confirmed":True,"level":level,"swing_index":swing["index"],"swing_label":swing["label"],"failure_candle_index":len(bars)-1,"scope":"EXTERNAL","sweep_distance_atr":round(sweep,4),"reclaim_distance_atr":round(reclaim,4)})
    if len(candidates)==1: return candidates[0]
    if candidates: return {"event":"CONFLICTING_FAILURES","direction":MIXED,"confirmed":False,"candidates":candidates}
    return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}


def _slope_direction(bars, lookback=20):
    c=[b["close"] for b in bars[-lookback:]]
    if len(c)<5: return NEUTRAL,0.0
    n=(c[-1]-c[0])/(max(_atr(bars),1e-12)*max(len(c)-1,1)); q=min(1,abs(n)*8)
    return UP if n>.035 else DOWN if n<-.035 else NEUTRAL,q


def _strength(ext, inte, bos, failure, conflicts):
    s=.25+(.25 if ext in {UP,DOWN} else 0)
    if ext==inte and ext in {UP,DOWN}: s+=.22
    elif inte in {UP,DOWN} and ext in {UP,DOWN}: s+=.08
    if bos.get("confirmed"): s+=min(.20,.08+float(bos.get("break_distance_atr",0))*.04); s+=.05 if bos.get("displacement_ok") else 0
    if failure.get("confirmed"): s-=.18
    s-=min(.28,len(conflicts)*.07)
    return round(max(0,min(1,s)),4)


def analyze_e3(bars):
    clean,data_reasons=_clean_bars(bars)
    base={"architecture":ARCHITECTURE,"reasoning_role":"MARKET_STRUCTURE_ANALYST","question":QUESTION,"decision":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"sub_engines_active":False,"sub_engines_status":"PAUSED","specialists_active":False,"specialists_status":"PAUSED","upstream_direction_used":False,"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False}
    if len(clean)<MIN_CANDLES:
        return {**base,"analysis_status":"INSUFFICIENT_DATA","finding":"STRUCTURE_INSUFFICIENT_DATA","structure":"UNKNOWN","structure_state":"INSUFFICIENT_DATA","direction":NEUTRAL,"directional_bias":NEUTRAL,"structural_bias":NEUTRAL,"swing_map":{"highs":[],"lows":[]},"internal_structure":{},"external_structure":{},"BOS":"NONE","BOS_type":"NONE","structural_failure":"NONE","failure_type":"NONE","strength":0.0,"structure_strength":0.0,"confidence":0.0,"evidence":[],"observations":[],"conflicts":[],"reason_codes":["E3_INSUFFICIENT_DATA",*data_reasons[:4]],"reasons":["E3_INSUFFICIENT_DATA",*data_reasons[:4]],"reasoning_trace":{"closed_candles":len(clean)}}
    atr=_atr(clean)
    ih=_label(_compress(_pivots(clean,"high",INTERNAL_RADIUS),atr,"high"),"HIGH",atr)
    il=_label(_compress(_pivots(clean,"low",INTERNAL_RADIUS),atr,"low"),"LOW",atr)
    eh=_label(_compress(_pivots(clean,"high",EXTERNAL_RADIUS),atr,"high"),"HIGH",atr)
    el=_label(_compress(_pivots(clean,"low",EXTERNAL_RADIUS),atr,"low"),"LOW",atr)
    istate=_state_from_latest(ih,il); estate=_state_from_latest(eh,el)
    ic=_counts(ih,il); ec=_counts(eh,el)
    icount=_count_state(ic); ecount=_count_state(ec)
    # Count state is evidence, never authority. Explicitly expose disagreements.
    slope,slope_q=_slope_direction(clean)
    eb=_bos(clean,eh,el,atr,estate,"EXTERNAL")
    ib=_bos(clean,ih,il,atr,istate,"INTERNAL")
    failure=_failure(clean,eh,el,atr,estate)
    conflicts=[]
    if estate in {UP,DOWN} and istate in {UP,DOWN} and estate!=istate: conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if icount!=NEUTRAL and icount!=istate: conflicts.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if ecount!=NEUTRAL and ecount!=estate: conflicts.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if slope in {UP,DOWN} and estate not in {slope,NEUTRAL}: conflicts.append("SLOPE_NOT_STRUCTURAL_AUTHORITY")
    if not eb.get("confirmed"): conflicts.append("NO_CONFIRMED_EXTERNAL_BOS")
    if ib.get("confirmed") and not eb.get("confirmed"): conflicts.append("INTERNAL_BREAK_ONLY")
    if failure.get("confirmed"): conflicts.append("FAILED_BREAK_DETECTED")
    if eb.get("event")=="CONFIRMED_CHOCH": conflicts.append("CHANGE_OF_CHARACTER_DETECTED")
    if estate==MIXED or istate==MIXED: conflicts.append("STRUCTURE_CONFLICT")
    if not eh or not el: conflicts.append("LIMITED_EXTERNAL_SWINGS")
    conflicts=list(dict.fromkeys(conflicts))
    if failure.get("confirmed"):
        direction,state,finding=failure["direction"],"STRUCTURE_FAILURE","FAILED_BREAK"
    elif eb.get("confirmed"):
        direction=eb["direction"]; state="CHANGE_OF_CHARACTER" if eb["event"]=="CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"; finding=("BULLISH_CHOCH" if direction==UP else "BEARISH_CHOCH") if state=="CHANGE_OF_CHARACTER" else ("BULLISH_BOS" if direction==UP else "BEARISH_BOS")
    elif estate in {UP,DOWN}:
        direction=estate; state="CONTINUATION" if istate==estate else "INTERNAL_CONFLICT" if istate==MIXED else "INTERNAL_COUNTER_MOVE"; finding="BULLISH_STRUCTURE" if direction==UP and state=="CONTINUATION" else "BEARISH_STRUCTURE" if direction==DOWN and state=="CONTINUATION" else ("BULLISH_EXTERNAL_MIXED_INTERNAL" if direction==UP and state=="INTERNAL_CONFLICT" else "BEARISH_EXTERNAL_MIXED_INTERNAL" if direction==DOWN and state=="INTERNAL_CONFLICT" else ("BULLISH_EXTERNAL_COUNTERMOVE" if direction==UP else "BEARISH_EXTERNAL_COUNTERMOVE"))
    elif istate in {UP,DOWN}:
        direction,state=istate,"DEVELOPING_STRUCTURE"; finding="BULLISH_DEVELOPING_STRUCTURE" if istate==UP else "BEARISH_DEVELOPING_STRUCTURE"
    elif istate==MIXED or estate==MIXED:
        direction,state,finding=MIXED,"TRANSITION","MIXED_STRUCTURE"
    else:
        direction,state,finding=MIXED,"RANGE_OR_UNCLEAR","NO_CONFIRMED_STRUCTURE_EVENT"
    protected=_protected_levels(direction if direction in {UP,DOWN} else estate,eh,el)
    strength=_strength(estate,istate,eb,failure,conflicts)
    confidence=round(min(1,.25+strength*.60+(.05 if estate==istate and estate in {UP,DOWN} else 0)),4)
    bias=direction if direction in {UP,DOWN} else NEUTRAL
    recent=clean[-30:]; prior=clean[-60:-30] if len(clean)>=60 else clean[:-30]
    rh=max(x["high"] for x in recent); rl=min(x["low"] for x in recent); ph=max((x["high"] for x in prior),default=rh); pl=min((x["low"] for x in prior),default=rl)
    iseq=_sequence(ih,il); eseq=_sequence(eh,el)
    obs=[f"closed_candles={len(clean)}",f"atr14={atr:.8f}",f"external_structure={estate}",f"internal_structure={istate}",f"external_count_state={ecount}",f"internal_count_state={icount}",f"external_counts={ec}",f"internal_counts={ic}",f"external_sequence={'→'.join(x['label'] for x in eseq) or 'NONE'}",f"internal_sequence={'→'.join(x['label'] for x in iseq) or 'NONE'}",f"slope_context={slope}",f"slope_quality={slope_q:.4f}",f"external_bos={eb['event']}",f"internal_bos={ib['event']}",f"failure={failure['event']}",f"structure_strength={strength:.4f}"]
    trace={"closed_candles":len(clean),"atr_period":14,"internal_pivot_window":INTERNAL_RADIUS,"external_pivot_window":EXTERNAL_RADIUS,"pivot_prominence_atr":PROMINENCE_ATR,"bos_close_distance_atr":BOS_DISTANCE_ATR,"bos_body_atr":BOS_BODY_ATR,"failure_close_distance_atr":FAILURE_CLOSE_ATR,"failure_sweep_distance_atr":FAILURE_SWEEP_ATR,"wick_only_break_is_bos":False,"external_structure_is_authority":True,"count_state_is_authority":False,"slope_is_structural_authority":False,"internal_structure":istate,"external_structure":estate,"internal_state":istate,"external_state":estate,"internal_count_state":icount,"external_count_state":ecount,"internal_sequence":iseq,"external_sequence":eseq,"protected_levels":protected,"internal_bos":ib,"external_bos":eb,"failure":failure,"consistency":{"internal_state_matches_count_state":icount in {NEUTRAL,istate},"external_state_matches_count_state":ecount in {NEUTRAL,estate}},"upstream_data_consumed":False,"decision_authority":"E9_ONLY"}
    return {**base,"analysis_status":"COMPLETE","finding":finding,"structure":direction if direction in {UP,DOWN} else MIXED,"structure_state":state,"direction":direction,"directional_bias":bias,"structural_bias":bias,"internal_structure":{"state":istate,"count_state":icount,"counts":ic,"labels":iseq,"sequence":iseq},"external_structure":{"state":estate,"count_state":ecount,"counts":ec,"labels":eseq,"sequence":eseq},"swing_map":{"highs":eh[-8:],"lows":el[-8:]},"HH":ec["HH"],"HL":ec["HL"],"LH":ec["LH"],"LL":ec["LL"],"BOS":finding if eb.get("confirmed") else "NONE","bos":eb,"BOS_type":eb.get("event","NO_BOS"),"bos_type":eb.get("event","NO_BOS"),"BOS_level":eb.get("level"),"bos_level":eb.get("level"),"BOS_candle_index":eb.get("break_candle_index"),"structural_failure":failure.get("event","NO_FAILURE"),"failure_type":failure.get("event","NO_FAILURE"),"failure_level":failure.get("level"),"failure":failure,"protected_levels":protected,"strength":strength,"structure_strength":strength,"confidence":confidence,"recent_high":round(rh,8),"recent_low":round(rl,8),"prior_high":round(ph,8),"prior_low":round(pl,8),"atr":round(atr,8),"protected_high":protected.get("bearish_protected_high"),"protected_low":protected.get("bullish_protected_low"),"conflicts":conflicts,"evidence":obs,"observations":obs,"reason_codes":conflicts,"reasons":conflicts,"reasoning_trace":trace}
