from __future__ import annotations

"""E3 — Professional Market Structure Brain V4.

E3 is isolated from E1/E2 and E4-E9. It answers one question only:
"What is price structure communicating?"

Confirmed swing structure is authoritative. Slope is context only. HH/HL/LH/LL
counts are evidence, not a trade signal. BOS/CHOCH requires a closed candle
beyond a meaningful structural level; a wick alone is a liquidity event.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V4"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 40
INTERNAL_RADIUS, EXTERNAL_RADIUS = 2, 5
PROMINENCE_ATR = 0.10
EQ_TOLERANCE_ATR = 0.10
BOS_CLOSE_ATR = 0.08
BOS_BODY_ATR = 0.20
BOS_CLOSE_LOCATION = 0.55
FAILURE_SWEEP_ATR = 0.05
FAILURE_RECLAIM_ATR = 0.05


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
            reasons.append(f"bar_{i}_not_mapping")
            continue
        o, h, l, c = [_num(b.get(k)) for k in ("open", "high", "low", "close")]
        if any(v is None for v in (o, h, l, c)):
            reasons.append(f"bar_{i}_ohlc_invalid")
            continue
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent")
            continue
        out.append({"open": o, "high": h, "low": l, "close": c})
    return out, reasons


def _tr(b, i):
    if i <= 0 or i >= len(b):
        return 0.0
    x, p = b[i], b[i - 1]["close"]
    return max(x["high"] - x["low"], abs(x["high"] - p), abs(x["low"] - p))


def _atr(b, period=14):
    if len(b) < 2:
        return 0.0
    return mean(_tr(b, i) for i in range(max(1, len(b) - period), len(b)))


def _atr_at(b, i, period=14):
    if i <= 0 or not b:
        return 0.0
    return mean(_tr(b, j) for j in range(max(1, i - period + 1), i + 1))


def _pivot_points(b, side, radius):
    out = []
    if len(b) <= radius * 2:
        return out
    for i in range(radius, len(b) - radius):
        x = b[i][side]
        left = [b[j][side] for j in range(i - radius, i)]
        right = [b[j][side] for j in range(i + 1, i + radius + 1)]
        prominence = PROMINENCE_ATR * max(_atr_at(b, i), 1e-12)
        if side == "high":
            if x >= max(left) and x > max(right) and min(x - max(left), x - max(right)) >= prominence:
                out.append((i, x))
        else:
            if x <= min(left) and x < min(right) and min(min(left) - x, min(right) - x) >= prominence:
                out.append((i, x))
    return out


def _compress(points, atr, side=None, spacing=2):
    points = list(points or [])
    if side is None:
        side = "high" if len(points) < 2 or points[-1][1] >= points[0][1] else "low"
    out = []
    tol = max(float(atr) * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        old = out[-1]
        if abs(p[1] - old[1]) <= tol:
            if side == "high" and p[1] > old[1]: out[-1] = p
            elif side == "low" and p[1] < old[1]: out[-1] = p
        elif side == "high" and p[1] > old[1]: out[-1] = p
        elif side == "low" and p[1] < old[1]: out[-1] = p
    return out


def _label(hp, lp, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    highs, prev = [], None
    for i, p in hp:
        d = 0.0 if prev is None else p - prev[1]
        label = "SWING_HIGH" if prev is None else ("EQH" if abs(d) <= tol else ("HH" if d > 0 else "LH"))
        highs.append({"index": int(i), "price": round(float(p), 8), "label": label})
        prev = (i, p)
    lows, prev = [], None
    for i, p in lp:
        d = 0.0 if prev is None else p - prev[1]
        label = "SWING_LOW" if prev is None else ("EQL" if abs(d) <= tol else ("HL" if d > 0 else "LL"))
        lows.append({"index": int(i), "price": round(float(p), 8), "label": label})
        prev = (i, p)
    return highs, lows


def _latest(xs, labels):
    return next((x for x in reversed(xs) if x["label"] in labels), None)


def _recent(xs, labels, n=2):
    return [x for x in reversed(xs) if x["label"] in labels][:n]


def _classify(highs, lows):
    hh, lh = _recent(highs, {"HH"}, 2), _recent(highs, {"LH"}, 2)
    hl, ll = _recent(lows, {"HL"}, 2), _recent(lows, {"LL"}, 2)
    bull = int(bool(hh)) + int(bool(hl))
    bear = int(bool(lh)) + int(bool(ll))
    if bull == 2 and bear == 0: return UP
    if bear == 2 and bull == 0: return DOWN
    return MIXED if bull or bear else NEUTRAL


def _count_state(highs, lows, n=8):
    items = highs[-n:] + lows[-n:]
    bull = sum(x["label"] in {"HH", "HL"} for x in items)
    bear = sum(x["label"] in {"LH", "LL"} for x in items)
    if bull == bear == 0: return NEUTRAL
    if bull >= bear + 2: return UP
    if bear >= bull + 2: return DOWN
    return MIXED


def _counts(highs, lows, n=8):
    c = {k: 0 for k in ("HH", "HL", "LH", "LL", "EQH", "EQL")}
    for x in highs[-n:] + lows[-n:]:
        if x["label"] in c: c[x["label"]] += 1
    return c


def _sequence(highs, lows, n=12):
    return sorted(highs + lows, key=lambda x: x["index"])[-n:]


def _protected(structure, highs, lows):
    if structure == UP:
        return {"protected_low": _latest(lows, {"HL"}), "protected_high": _latest(highs, {"HH", "EQH"})}
    if structure == DOWN:
        return {"protected_low": _latest(lows, {"LL", "EQL"}), "protected_high": _latest(highs, {"LH", "EQH"})}
    return {"protected_low": _latest(lows, {"HL", "LL", "EQL"}), "protected_high": _latest(highs, {"HH", "LH", "EQH"})}


def _quality(bar, level, direction, atr):
    if atr <= 0 or level is None:
        return {"confirmed": False, "reason": "NO_LEVEL_OR_ATR"}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body_atr = abs(bar["close"] - bar["open"]) / atr
    loc = (bar["close"] - bar["low"]) / rng
    distance = ((bar["close"] - level) if direction == UP else (level - bar["close"])) / atr
    close_beyond = distance >= BOS_CLOSE_ATR
    location_ok = loc >= BOS_CLOSE_LOCATION if direction == UP else loc <= 1.0 - BOS_CLOSE_LOCATION
    displacement_ok = body_atr >= BOS_BODY_ATR
    return {"confirmed": bool(close_beyond and (displacement_ok or location_ok)), "distance_atr": round(max(0.0, distance), 4), "body_atr": round(body_atr, 4), "close_location": round(loc, 4), "displacement_ok": displacement_ok, "close_beyond_level": close_beyond}


def _event(bar, point, direction, atr, event, scope="EXTERNAL", idx=0):
    q = _quality(bar, point["price"] if point else None, direction, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return {"event": event, "direction": direction, "confirmed": True, "scope": scope, "level": point["price"], "swing_index": point["index"], "swing_label": point["label"], "break_candle_index": idx, "break_distance_atr": q["distance_atr"], "break_body_atr": q["body_atr"], "close_location": q["close_location"], "displacement_ok": q["displacement_ok"], "close_beyond_level": q["close_beyond_level"]}


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    if not bars or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    last, candidates = bars[-1], []
    high, low = _latest(highs, {"HH", "LH", "EQH"}), _latest(lows, {"HL", "LL", "EQL"})
    if high:
        q = _quality(last, high["price"], UP, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if prior_structure == DOWN else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _event(last, high, UP, atr, event, scope, len(bars)-1)))
    if low:
        q = _quality(last, low["price"], DOWN, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if prior_structure == UP else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _event(last, low, DOWN, atr, event, scope, len(bars)-1)))
    return max(candidates, key=lambda x: x[0])[1] if candidates else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _sweep_failure(bars, highs, lows, atr=None, prior_structure="UP"):
    if not bars: return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    if atr is None or atr <= 0:
        atr = _atr(bars)
        if atr <= 0: atr = max(bars[-1]["high"] - bars[-1]["low"], 1e-12)
    b = bars[-1]
    p = _protected(prior_structure, highs, lows)
    candidates = []
    high, low = p.get("protected_high"), p.get("protected_low")
    if high:
        sweep = (b["high"] - high["price"]) / atr; reclaim = (high["price"] - b["close"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append({"event":"FAILED_BREAK","direction":DOWN,"confirmed":True,"level":high["price"],"swing_index":high["index"],"swing_label":high["label"],"failure_candle_index":len(bars)-1,"scope":"EXTERNAL","sweep_distance_atr":round(sweep,4),"reclaim_distance_atr":round(reclaim,4)})
    if low:
        sweep = (low["price"] - b["low"]) / atr; reclaim = (b["close"] - low["price"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append({"event":"FAILED_BREAK","direction":UP,"confirmed":True,"level":low["price"],"swing_index":low["index"],"swing_label":low["label"],"failure_candle_index":len(bars)-1,"scope":"EXTERNAL","sweep_distance_atr":round(sweep,4),"reclaim_distance_atr":round(reclaim,4)})
    return max(candidates,key=lambda x:x["sweep_distance_atr"]+x["reclaim_distance_atr"]) if candidates else {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}


def _failure(bars, highs, lows, structure, atr): return _sweep_failure(bars, highs, lows, atr, structure)


def _choch(bars, highs, lows, structure, atr):
    if structure not in {UP, DOWN} or not bars: return {"event":"NO_CHOCH","direction":NEUTRAL,"confirmed":False}
    p = _protected(structure, highs, lows)
    point = p.get("protected_low") if structure == UP else p.get("protected_high")
    direction = DOWN if structure == UP else UP
    if not point: return {"event":"NO_CHOCH","direction":NEUTRAL,"confirmed":False}
    return _event(bars[-1], point, direction, atr, "CONFIRMED_CHOCH", "EXTERNAL", len(bars)-1)


def _slope(bars, n=20):
    if len(bars) < 5: return NEUTRAL, 0.0
    closes = [x["close"] for x in bars[-n:]]
    z = (closes[-1]-closes[0])/(max(_atr(bars),1e-12)*max(1,len(closes)-1))
    return (UP if z > .035 else DOWN if z < -.035 else NEUTRAL), round(min(1.0,abs(z)*8.0),4)


def _authority(external, internal, ext_bos, int_bos, failure):
    reasons=[]
    if external in {UP,DOWN} and internal == external: authority=1.0
    elif external in {UP,DOWN} and internal == MIXED: authority=.68; reasons.append("INTERNAL_STRUCTURE_NOT_ALIGNED")
    elif external == MIXED and internal in {UP,DOWN}: authority=.48; reasons.append("EXTERNAL_STRUCTURE_NOT_CONFIRMED")
    else: authority=.25 if external == MIXED or internal == MIXED else .10; reasons.append("STRUCTURE_UNRESOLVED")
    if ext_bos.get("confirmed"): authority=min(1.0,authority+.18)
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        authority=min(.72,authority+.04); reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if failure.get("confirmed"): authority=min(authority,.60); reasons.append("LIQUIDITY_FAILURE_REQUIRES_REASSESSMENT")
    if external != internal: reasons.append("EXTERNAL_INTERNAL_DIVERGENCE")
    return round(authority,4), list(dict.fromkeys(reasons))


def _finding(external, internal, ext_bos, int_bos, failure):
    if failure.get("confirmed"): return "FAILED_BREAK_REQUIRES_REASSESSMENT"
    if ext_bos.get("confirmed"): return "BULLISH_EXTERNAL_BOS" if ext_bos["direction"] == UP else "BEARISH_EXTERNAL_BOS"
    if external == UP and internal == UP: return "BULLISH_CONFIRMED_STRUCTURE"
    if external == DOWN and internal == DOWN: return "BEARISH_CONFIRMED_STRUCTURE"
    if external in {UP,DOWN} and internal == MIXED: return f"{external}_EXTERNAL_MIXED_INTERNAL"
    if external == MIXED and internal in {UP,DOWN}: return f"{internal}_INTERNAL_NOT_EXTERNAL_AUTHORITY"
    return "MIXED_STRUCTURE"


def analyze_e3(bars):
    clean, data_errors = _clean_bars(bars)
    base={"architecture":ARCHITECTURE,"question":QUESTION,"reasoning_role":"MARKET_STRUCTURE_ANALYST","decision":None,"gate":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False,"data_errors":data_errors}
    if len(clean) < MIN_CANDLES:
        return {**base,"finding":"INSUFFICIENT_STRUCTURE_DATA","external_structure":NEUTRAL,"internal_structure":NEUTRAL,"external_count_state":NEUTRAL,"internal_count_state":NEUTRAL,"external_counts":{},"internal_counts":{},"external_sequence":[],"internal_sequence":[],"external_bos":{"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":"EXTERNAL"},"internal_bos":{"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":"INTERNAL"},"failure":{"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False},"choch":{"event":"NO_CHOCH","direction":NEUTRAL,"confirmed":False},"protected_levels":{"protected_low":None,"protected_high":None},"slope_context":NEUTRAL,"slope_quality":0.0,"structure_authority":0.0,"confidence":0.0,"reasons":["INSUFFICIENT_CANDLES"]}
    atr=_atr(clean)
    ihp=_compress(_pivot_points(clean,"high",INTERNAL_RADIUS),atr,"high"); ilp=_compress(_pivot_points(clean,"low",INTERNAL_RADIUS),atr,"low")
    ehp=_compress(_pivot_points(clean,"high",EXTERNAL_RADIUS),atr,"high"); elp=_compress(_pivot_points(clean,"low",EXTERNAL_RADIUS),atr,"low")
    ih,il=_label(ihp,ilp,atr); eh,el=_label(ehp,elp,atr)
    external,internal=_classify(eh,el),_classify(ih,il)
    external_count,internal_count=_count_state(eh,el),_count_state(ih,il)
    ext_counts,int_counts=_counts(eh,el),_counts(ih,il)
    ext_seq,int_seq=_sequence(eh,el),_sequence(ih,il)
    ext_bos=_bos(clean,eh,el,atr,external,"EXTERNAL"); int_bos=_bos(clean,ih,il,atr,internal,"INTERNAL")
    failure=_failure(clean,eh,el,external,atr); choch=_choch(clean,eh,el,external,atr)
    slope_context,slope_quality=_slope(clean)
    authority,reason_codes=_authority(external,internal,ext_bos,int_bos,failure)
    finding=_finding(external,internal,ext_bos,int_bos,failure)
    reasons=list(reason_codes)
    if external_count != external: reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if internal_count != internal: reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if not ext_bos.get("confirmed"): reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if external in {UP,DOWN} and choch.get("confirmed") and choch.get("direction") != external: reasons.append("STRUCTURAL_REVERSAL_EVIDENCE")
    if slope_context != external and external in {UP,DOWN}: reasons.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    if failure.get("confirmed"): reasons.append("LIQUIDITY_SWEEP_FAILURE_PRESENT")
    confidence=authority
    if ext_bos.get("confirmed"): confidence=min(1.0,confidence+.10)
    if external == internal and external in {UP,DOWN}: confidence=min(1.0,confidence+.05)
    if external == MIXED: confidence=min(confidence,.55)
    confidence=round(confidence,4)
    protected=_protected(external,eh,el)
    observations=[f"closed_candles={len(clean)}",f"atr14={round(atr,8)}",f"external_structure={external}",f"internal_structure={internal}",f"external_count_state={external_count}",f"internal_count_state={internal_count}",f"external_counts={ext_counts}",f"internal_counts={int_counts}",f"external_bos={ext_bos.get('event')}",f"internal_bos={int_bos.get('event')}",f"protected_high={protected.get('protected_high',{}).get('price') if protected.get('protected_high') else None}",f"protected_low={protected.get('protected_low',{}).get('price') if protected.get('protected_low') else None}"]
    return {**base,"finding":finding,"external_structure":external,"internal_structure":internal,"external_count_state":external_count,"internal_count_state":internal_count,"external_counts":ext_counts,"internal_counts":int_counts,"external_sequence":[x["label"] for x in ext_seq],"internal_sequence":[x["label"] for x in int_seq],"external_sequence_detail":ext_seq,"internal_sequence_detail":int_seq,"external_bos":ext_bos,"internal_bos":int_bos,"failure":failure,"choch":choch,"protected_levels":protected,"slope_context":slope_context,"slope_quality":slope_quality,"structure_authority":authority,"confidence":confidence,"observations":observations,"reasons":list(dict.fromkeys(reasons))}


class SubEngine:
    """Compatibility wrapper for the production dispatcher."""
    sub_engine_id="E3"
    def run(self,snapshot): return analyze_e3(list(snapshot.get("bars") or []))
