from __future__ import annotations

"""E3 — Professional Market Structure Brain V3.

Price-only structural analyst. It uses closed OHLC, confirmed pivots,
internal/external structure, BOS/CHOCH and failed breaks. It never consumes
upstream direction, decisions, gates or scores and never authorizes trades.
"""
from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V3"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _clean_bars(bars: list[dict[str, Any]] | None):
    out, reasons = [], []
    for i, b in enumerate(bars or []):
        if not isinstance(b, dict):
            reasons.append(f"bar_{i}_not_mapping"); continue
        v = {k: _num(b.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            reasons.append(f"bar_{i}_ohlc_invalid"); continue
        o, h, l, c = (float(v[k]) for k in ("open", "high", "low", "close"))
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


def _pivots(bars, side, radius=2):
    if len(bars) < 2 * radius + 1: return []
    pts = []
    for i in range(radius, len(bars)-radius):
        x = bars[i][side]
        left = [bars[j][side] for j in range(i-radius, i)]
        right = [bars[j][side] for j in range(i+1, i+radius+1)]
        if side == "high" and x >= max(left) and x > max(right): pts.append((i, x))
        if side == "low" and x <= min(left) and x < min(right): pts.append((i, x))
    return pts


def _compress(points, atr, side, spacing=2):
    out, tol = [], max(atr * 0.10, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p); continue
        if abs(p[1] - out[-1][1]) <= tol: continue
        if side == "high" and p[1] > out[-1][1]: out[-1] = p
        if side == "low" and p[1] < out[-1][1]: out[-1] = p
    return out


def _label(points, kind, atr):
    out, tol = [], max(atr * 0.10, 1e-12)
    for i, (idx, price) in enumerate(points):
        if i == 0: label = "SWING_HIGH" if kind == "HIGH" else "SWING_LOW"
        else:
            d = price - points[i-1][1]
            if abs(d) <= tol: label = "EQH" if kind == "HIGH" else "EQL"
            elif kind == "HIGH": label = "HH" if d > 0 else "LH"
            else: label = "HL" if d > 0 else "LL"
        out.append({"index": idx, "price": round(price, 8), "label": label})
    return out


def _structure_direction(highs, lows):
    hd = next((x["label"] for x in reversed(highs) if x["label"] in {"HH", "LH"}), None)
    ld = next((x["label"] for x in reversed(lows) if x["label"] in {"HL", "LL"}), None)
    if hd == "HH" and ld == "HL": return UP
    if hd == "LH" and ld == "LL": return DOWN
    return MIXED if hd and ld else NEUTRAL


def _latest_break_candidates(highs, lows, latest_index):
    h = next((x for x in reversed(highs) if x["index"] < latest_index), None)
    l = next((x for x in reversed(lows) if x["index"] < latest_index), None)
    out = []
    if h: out.append((float(h["price"]), int(h["index"]), UP))
    if l: out.append((float(l["price"]), int(l["index"]), DOWN))
    return out


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    if atr <= 0 or len(bars) < 2:
        return {"event":"NO_BOS", "direction":NEUTRAL, "confirmed":False, "scope":scope}
    latest, candidates = bars[-1], []
    for level, idx, direction in _latest_break_candidates(highs, lows, len(bars)-1):
        distance = latest["close"] - level if direction == UP else level - latest["close"]
        if distance >= atr * 0.10:
            body_atr = abs(latest["close"]-latest["open"]) / atr
            event = "CONFIRMED_CHOCH" if prior_structure in {UP, DOWN} and direction != prior_structure else "CONFIRMED_BOS"
            candidates.append({"event":event,"direction":direction,"confirmed":True,"scope":scope,"level":round(level,8),"swing_index":idx,"break_candle_index":len(bars)-1,"break_distance_atr":round(distance/atr,4),"break_body_atr":round(body_atr,4),"close_beyond_level":True})
    if len(candidates) == 1: return candidates[0]
    if len(candidates) > 1: return {"event":"CONFLICTING_BREAKS","direction":MIXED,"confirmed":False,"scope":scope,"candidates":candidates}
    return {"event":"NO_BOS","direction":NEUTRAL,"confirmed":False,"scope":scope}


def _sweep_failure(bars, highs, lows):
    if not bars: return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}
    b = bars[-1]; failures = []
    for level, idx, direction in _latest_break_candidates(highs, lows, len(bars)-1):
        if direction == UP and b["high"] > level and b["close"] < level:
            failures.append({"event":"FAILED_BREAK","direction":DOWN,"confirmed":True,"level":round(level,8),"swing_index":idx,"failure_candle_index":len(bars)-1,"scope":"EXTERNAL"})
        elif direction == DOWN and b["low"] < level and b["close"] > level:
            failures.append({"event":"FAILED_BREAK","direction":UP,"confirmed":True,"level":round(level,8),"swing_index":idx,"failure_candle_index":len(bars)-1,"scope":"EXTERNAL"})
    return failures[0] if len(failures) == 1 else ({"event":"CONFLICTING_FAILURES","direction":MIXED,"confirmed":False} if failures else {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False})


def _failure(bars, bos, atr):
    # Kept as a public-test-compatible helper. A confirmed break can be
    # invalidated only when a later/current candle closes back through it.
    if not bos.get("confirmed") or atr <= 0: return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}
    level, direction, b = float(bos["level"]), bos["direction"], bars[-1]
    if direction == UP and b["high"] > level and b["close"] < level - atr*0.05:
        return {"event":"FAILED_BOS","direction":DOWN,"confirmed":True,"level":level,"failure_candle_index":len(bars)-1}
    if direction == DOWN and b["low"] < level and b["close"] > level + atr*0.05:
        return {"event":"FAILED_BOS","direction":UP,"confirmed":True,"level":level,"failure_candle_index":len(bars)-1}
    return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}


def _slope_direction(bars, lookback=20):
    closes = [b["close"] for b in bars[-lookback:]]
    if len(closes) < 5: return NEUTRAL, 0.0
    n = (closes[-1]-closes[0]) / (max(_atr(bars),1e-12) * max(len(closes)-1,1))
    q = min(1.0, abs(n)*8.0)
    return (UP if n > 0.035 else DOWN if n < -0.035 else NEUTRAL), q


def _strength(external, internal, bos, failure, swing_count, slope_quality):
    s = 0.20 + (0.22 if external in {UP,DOWN} else 0) + (0.18 if internal == external and internal in {UP,DOWN} else 0.02 if internal == MIXED else 0)
    if bos.get("confirmed"): s += min(0.28, 0.12 + float(bos.get("break_distance_atr",0))*0.05)
    if failure.get("confirmed"): s += 0.04
    return round(min(1.0, s + min(0.08,slope_quality*0.08) + min(0.06,swing_count*0.005)),4)


def analyze_e3(bars):
    clean, data_reasons = _clean_bars(bars)
    base = {"architecture":ARCHITECTURE,"reasoning_role":"MARKET_STRUCTURE_ANALYST","question":QUESTION,"decision":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","gate":None,"sub_engines_active":False,"sub_engines_status":"PAUSED","specialists_active":False,"specialists_status":"PAUSED","upstream_direction_used":False,"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False}
    if len(clean) < 20:
        return {**base,"analysis_status":"INSUFFICIENT_DATA","finding":"STRUCTURE_INSUFFICIENT_DATA","structure_state":"INSUFFICIENT_DATA","direction":NEUTRAL,"swing_map":{"highs":[],"lows":[]},"internal_structure":{},"external_structure":{},"bos":{"event":"NO_BOS","direction":NEUTRAL,"confirmed":False},"failure":{"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False},"structure_strength":0.0,"confidence":0.0,"evidence":[f"closed_candles={len(clean)}"],"observations":[f"closed_candles={len(clean)}"],"reason_codes":["E3_INSUFFICIENT_DATA",*data_reasons[:4]],"reasons":["E3_INSUFFICIENT_DATA",*data_reasons[:4]]}
    atr = _atr(clean)
    ih, il = _label(_compress(_pivots(clean,"high",2),atr,"high"),"HIGH",atr), _label(_compress(_pivots(clean,"low",2),atr,"low"),"LOW",atr)
    eh, el = _label(_compress(_pivots(clean,"high",5),atr,"high"),"HIGH",atr), _label(_compress(_pivots(clean,"low",5),atr,"low"),"LOW",atr)
    idef, edef = _structure_direction(ih,il), _structure_direction(eh,el)
    slope, slope_q = _slope_direction(clean)
    bos = _bos(clean,eh,el,atr,edef,"EXTERNAL")
    internal_bos = _bos(clean,ih,il,atr,idef,"INTERNAL")
    failure = _sweep_failure(clean,eh,el)
    if failure["confirmed"]: direction,state,finding=failure["direction"],"STRUCTURE_FAILURE","FAILED_BREAK"
    elif bos.get("confirmed"):
        direction=bos["direction"]; state="CHANGE_OF_CHARACTER" if bos["event"]=="CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"; finding=("BULLISH_CHOCH" if direction==UP else "BEARISH_CHOCH") if bos["event"]=="CONFIRMED_CHOCH" else ("BULLISH_BOS" if direction==UP else "BEARISH_BOS")
    elif edef in {UP,DOWN}:
        direction=edef
        if idef==edef: state,finding="CONTINUATION",("BULLISH_STRUCTURE" if direction==UP else "BEARISH_STRUCTURE")
        elif idef==MIXED: state,finding="INTERNAL_CONFLICT",("BULLISH_EXTERNAL_MIXED_INTERNAL" if direction==UP else "BEARISH_EXTERNAL_MIXED_INTERNAL")
        else: state,finding="INTERNAL_COUNTER_MOVE",("BULLISH_EXTERNAL_COUNTERMOVE" if direction==UP else "BEARISH_EXTERNAL_COUNTERMOVE")
    elif idef in {UP,DOWN}: direction,state,finding=idef,"DEVELOPING_STRUCTURE",("BULLISH_DEVELOPING_STRUCTURE" if idef==UP else "BEARISH_DEVELOPING_STRUCTURE")
    elif idef==MIXED or edef==MIXED: direction,state,finding=MIXED,"TRANSITION","MIXED_STRUCTURE"
    elif slope in {UP,DOWN}: direction,state,finding=MIXED,"DIRECTIONAL_CONTEXT_UNCONFIRMED","DIRECTIONAL_CONTEXT_UNCONFIRMED"
    else: direction,state,finding=NEUTRAL,"RANGE_OR_UNCLEAR","NO_CONFIRMED_STRUCTURE_EVENT"
    reasons=[]
    if not bos.get("confirmed"): reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if internal_bos.get("confirmed") and not bos.get("confirmed"): reasons.append("INTERNAL_BREAK_ONLY")
    if failure.get("confirmed"): reasons.append("FAILED_BREAK_DETECTED")
    if bos.get("event")=="CONFIRMED_CHOCH": reasons.append("CHANGE_OF_CHARACTER_DETECTED")
    if bos.get("event")=="CONFLICTING_BREAKS": reasons.append("CONFLICTING_EXTERNAL_BREAKS")
    if edef==MIXED or idef==MIXED: reasons.append("STRUCTURE_CONFLICT")
    if edef in {UP,DOWN} and idef not in {edef,NEUTRAL}: reasons.append("INTERNAL_EXTERNAL_DISAGREEMENT")
    if not eh or not el: reasons.append("LIMITED_EXTERNAL_SWINGS")
    if not ih or not il: reasons.append("LIMITED_INTERNAL_SWINGS")
    if slope in {UP,DOWN} and edef not in {slope,NEUTRAL}: reasons.append("SLOPE_NOT_STRUCTURAL_AUTHORITY")
    reasons=list(dict.fromkeys(reasons+data_reasons[:2]))
    evidence=[f"closed_candles={len(clean)}",f"atr14={atr:.8f}",f"external_structure={edef}",f"internal_structure={idef}",f"slope_context={slope}",f"slope_quality={slope_q:.4f}",f"external_bos={bos['event']}",f"internal_bos={internal_bos['event']}",f"failure={failure['event']}",f"internal_swing_count={len(ih)+len(il)}",f"external_swing_count={len(eh)+len(el)}"]
    if bos.get("confirmed"): evidence += [f"bos_scope={bos['scope']}",f"bos_level={bos['level']}",f"bos_break_distance_atr={bos['break_distance_atr']}",f"bos_break_body_atr={bos['break_body_atr']}"]
    strength=_strength(edef,idef,bos,failure,len(ih)+len(il)+len(eh)+len(el),slope_q)
    confidence=round(min(1.0,0.30+strength*0.42+slope_q*0.10),4)
    return {**base,"analysis_status":"COMPLETE","finding":finding,"structure_state":state,"direction":direction,"internal_structure":{"highs":ih[-6:],"lows":il[-6:],"direction":idef},"external_structure":{"highs":eh[-4:],"lows":el[-4:],"direction":edef},"swing_map":{"highs":eh,"lows":el},"bos":bos,"internal_bos":internal_bos,"failure":failure,"structure_strength":strength,"confidence":confidence,"evidence":evidence,"observations":evidence,"reason_codes":reasons,"reasons":reasons}
