from __future__ import annotations
from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V18"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 40
IR, ER = 2, 5
PROMINENCE_ATR = 0.10
EQ_TOLERANCE_ATR = 0.10
BOS_CLOSE_ATR = 0.08
BOS_BODY_ATR = 0.20
BOS_CLOSE_LOCATION = 0.55
FOLLOW_THROUGH_BARS = 2
SWEEP_MIN_ATR = 0.05
RECLAIM_MIN_ATR = 0.05


def _num(v: Any):
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _clean(bars):
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


def _tr(b, i):
    if i <= 0: return 0.0
    x, p = b[i], b[i - 1]["close"]
    return max(x["high"] - x["low"], abs(x["high"] - p), abs(x["low"] - p))


def _atr(b, p=14):
    return mean(_tr(b, i) for i in range(max(1, len(b) - p), len(b))) if len(b) > 1 else 0.0


def _atr_at(b, i, p=14):
    return mean(_tr(b, j) for j in range(max(1, i - p + 1), i + 1)) if i > 0 else 0.0


def _pivots(b, side, radius):
    out = []
    for i in range(radius, len(b) - radius):
        x = b[i][side]
        left = [b[j][side] for j in range(i - radius, i)]
        right = [b[j][side] for j in range(i + 1, i + radius + 1)]
        prom = PROMINENCE_ATR * max(_atr_at(b, i), 1e-12)
        if side == "high":
            ok = x >= max(left) and x > max(right) and min(x - max(left), x - max(right)) >= prom
        else:
            ok = x <= min(left) and x < min(right) and min(min(left) - x, min(right) - x) >= prom
        if ok: out.append((i, x, i + radius))
    return out


def _compress(points, atr, side=None, spacing=2):
    out, tol = [], max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p); continue
        q = out[-1]
        if abs(p[1] - q[1]) <= tol or (side == "high" and p[1] > q[1]) or (side == "low" and p[1] < q[1]):
            out[-1] = p
    return out


def _label(hp, lp, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    hs, ls, prev = [], [], None
    for i, p, ci in hp:
        d = 0 if prev is None else p - prev[1]
        lab = "SWING_HIGH" if prev is None else "EQH" if abs(d) <= tol else "HH" if d > 0 else "LH"
        hs.append({"index": i, "price": round(p, 8), "label": lab, "confirmation_index": ci}); prev = (i, p)
    prev = None
    for i, p, ci in lp:
        d = 0 if prev is None else p - prev[1]
        lab = "SWING_LOW" if prev is None else "EQL" if abs(d) <= tol else "HL" if d > 0 else "LL"
        ls.append({"index": i, "price": round(p, 8), "label": lab, "confirmation_index": ci}); prev = (i, p)
    return hs, ls


def _latest(xs, labels, max_confirm=None):
    for x in reversed(xs):
        if x["label"] in labels and (max_confirm is None or x["confirmation_index"] <= max_confirm): return x
    return None


def _counts(h, l, n=8):
    c = {k: 0 for k in ("HH", "HL", "LH", "LL", "EQH", "EQL")}
    for x in h[-n:] + l[-n:]:
        if x["label"] in c: c[x["label"]] += 1
    return c


def _count(h, l, n=8):
    c = _counts(h, l, n)
    bull, bear = c["HH"] + c["HL"], c["LH"] + c["LL"]
    return UP if bull >= bear + 2 else DOWN if bear >= bull + 2 else NEUTRAL if bull == bear == 0 else MIXED


def _resolve_structure(h, l):
    d = [x for x in sorted(h + l, key=lambda x: (x["index"], x["confirmation_index"])) if x["label"] in {"HH", "HL", "LH", "LL"}]
    if not d: return NEUTRAL
    last = d[-1]["label"]
    return UP if last in {"HH", "HL"} else DOWN if last in {"LH", "LL"} else MIXED


def _resolve_external_state(h, l):
    return _resolve_structure(h, l)


def _classify(h, l):
    return _resolve_structure(h, l)


def _protected_structure(direction, h, l):
    highs = sorted(h, key=lambda x: x["index"]); lows = sorted(l, key=lambda x: x["index"])
    if direction == UP:
        impulse = _latest(highs, {"HH"})
        prior = [x for x in lows if impulse and x["index"] < impulse["index"]]
        anchor = prior[-1] if prior else None
        ideal = anchor if anchor and anchor["label"] == "HL" else None
        p = ideal or anchor
        return {
            "protected_high": impulse, "protected_low": p, "primary_direction": UP,
            "primary_level": p["price"] if p else None, "primary_label": p["label"] if p else None,
            "invalidation_level": p["price"] if p else None,
            "invalidation_type": "CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW",
            "anchor_quality": "IDEAL" if ideal else "NON_IDEAL" if p else "MISSING",
            "anchor_status": "ACTIVE" if p else "MISSING", "anchor_index": p["index"] if p else None,
            "anchor_price": p["price"] if p else None, "anchor_is_ideal": bool(ideal),
            "why_primary": "Latest HH defines the bullish impulse; the latest preceding confirmed external low is the defended anchor."
        }
    if direction == DOWN:
        impulse = _latest(lows, {"LL"})
        prior = [x for x in highs if impulse and x["index"] < impulse["index"]]
        anchor = prior[-1] if prior else None
        ideal = anchor if anchor and anchor["label"] == "LH" else None
        p = ideal or anchor
        return {
            "protected_high": p, "protected_low": impulse, "primary_direction": DOWN,
            "primary_level": p["price"] if p else None, "primary_label": p["label"] if p else None,
            "invalidation_level": p["price"] if p else None,
            "invalidation_type": "CLOSED_CANDLE_ACCEPTANCE_ABOVE_PROTECTED_HIGH",
            "anchor_quality": "IDEAL" if ideal else "NON_IDEAL" if p else "MISSING",
            "anchor_status": "ACTIVE" if p else "MISSING", "anchor_index": p["index"] if p else None,
            "anchor_price": p["price"] if p else None, "anchor_is_ideal": bool(ideal),
            "why_primary": "Latest LL defines the bearish impulse; the latest preceding confirmed external high is the defended anchor."
        }
    return {
        "protected_high": _latest(highs, {"HH", "LH"}), "protected_low": _latest(lows, {"HL", "LL"}),
        "primary_direction": NEUTRAL, "primary_level": None, "primary_label": None,
        "invalidation_level": None, "invalidation_type": "NO_DIRECTIONAL_INVALIDATION_LEVEL",
        "anchor_quality": "UNRESOLVED", "anchor_status": "MISSING", "anchor_index": None,
        "anchor_price": None, "anchor_is_ideal": False,
        "why_primary": "External structure is unresolved; no directional protected anchor has authority."
    }


def _quality(bar, level, direction, atr):
    if atr <= 0 or level is None: return {"confirmed": False}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body = abs(bar["close"] - bar["open"]) / atr
    loc = (bar["close"] - bar["low"]) / rng
    dist = ((bar["close"] - level) if direction == UP else (level - bar["close"])) / atr
    return {
        "confirmed": dist >= BOS_CLOSE_ATR and (body >= BOS_BODY_ATR or (loc >= BOS_CLOSE_LOCATION if direction == UP else loc <= 1 - BOS_CLOSE_LOCATION)),
        "distance_atr": round(max(0, dist), 4), "body_atr": round(body, 4), "close_location": round(loc, 4),
        "displacement_ok": body >= BOS_BODY_ATR, "close_beyond_level": dist >= BOS_CLOSE_ATR
    }


def _event(bar, pivot, direction, atr, event, scope, idx):
    q = _quality(bar, pivot["price"], direction, atr)
    if not q["confirmed"]: return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return {"event": event, "direction": direction, "confirmed": True, "scope": scope,
            "level": pivot["price"], "swing_index": pivot["index"], "swing_label": pivot["label"],
            "break_candle_index": idx, "closed_candle_confirmed": True, **q}


def _current_break(bars, highs, lows, atr, structure, scope="EXTERNAL", idx=None):
    idx = len(bars) - 1 if idx is None else idx
    if idx < 1 or atr <= 0: return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    checks = []
    hh = _latest(highs, {"HH"}, idx - 1); lh = _latest(highs, {"LH"}, idx - 1)
    hl = _latest(lows, {"HL"}, idx - 1); ll = _latest(lows, {"LL"}, idx - 1)
    c, pc = bars[idx]["close"], bars[idx - 1]["close"]
    if structure == UP:
        if hh and c > hh["price"] and pc <= hh["price"]: checks.append((hh, UP, "CONFIRMED_BOS"))
        if hl and c < hl["price"] and pc >= hl["price"]: checks.append((hl, DOWN, "CONFIRMED_CHOCH"))
    elif structure == DOWN:
        if ll and c < ll["price"] and pc >= ll["price"]: checks.append((ll, DOWN, "CONFIRMED_BOS"))
        if lh and c > lh["price"] and pc <= lh["price"]: checks.append((lh, UP, "CONFIRMED_CHOCH"))
    events = [_event(bars[idx], p, d, atr, e, scope, idx) for p, d, e in checks]
    events = [e for e in events if e["confirmed"]]
    return max(events, key=lambda x: x["distance_atr"]) if events else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    return _current_break(bars, highs, lows, atr, prior_structure, scope)


def _structure_at(highs, lows, idx):
    return _resolve_structure([x for x in highs if x["confirmation_index"] <= idx], [x for x in lows if x["confirmation_index"] <= idx])


def _break_history(bars, highs, lows, atr, structure):
    events, active = [], None
    for i in range(len(bars)):
        if active:
            age = i - active["break_candle_index"]; active["follow_through_bars"] = age
            d, level = active["direction"], active["level"]
            reclaimed = (d == UP and bars[i]["close"] <= level - RECLAIM_MIN_ATR * atr) or (d == DOWN and bars[i]["close"] >= level + RECLAIM_MIN_ATR * atr)
            if reclaimed and i > active["break_candle_index"]:
                events.append({**active, "status": "FAILED_BREAK_RECLAIMED", "failure_candle_index": i}); active = None; continue
            if age >= FOLLOW_THROUGH_BARS and not active.get("accepted"):
                active["accepted"] = True; active["acceptance_candle_index"] = i; active["status"] = "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH"
        e = _current_break(bars, highs, lows, atr, _structure_at(highs, lows, i - 1), "EXTERNAL", i)
        if e["confirmed"] and active is None:
            active = {"event": e["event"], "direction": e["direction"], "level": e["level"], "swing_index": e["swing_index"],
                      "break_candle_index": i, "status": "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH", "follow_through_bars": 0, "accepted": False}
    return events, active


def _failure(bars, active, atr, current_index=None):
    if not active or active.get("status") != "FAILED_BREAK_RECLAIMED":
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False, "current": False}
    i = len(bars) - 1 if current_index is None else current_index
    d = active["direction"]; current = active.get("failure_candle_index") == i
    return {"event": "FAILED_BOS" if current else "HISTORICAL_FAILED_BOS", "direction": DOWN if d == UP else UP,
            "confirmed": True, "current": current, "closed_candle_confirmed": True, "level": active["level"],
            "break_candle_index": active["break_candle_index"], "failure_candle_index": active.get("failure_candle_index"), "scope": "EXTERNAL"}


def _sweep_reclaim(bars, highs, lows, atr, structure):
    if not bars or atr <= 0: return {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False}
    i, found = len(bars) - 1, []
    hi = _latest(highs, {"EQH"}, i - 1); lo = _latest(lows, {"EQL"}, i - 1)
    if hi:
        s = (bars[i]["high"] - hi["price"]) / atr; r = (hi["price"] - bars[i]["close"]) / atr
        if s >= SWEEP_MIN_ATR and r >= RECLAIM_MIN_ATR: found.append((r, {"event":"SWEEP_RECLAIM","direction":DOWN,"confirmed":True,"closed_candle_confirmed":True,"level":hi["price"],"swing_index":hi["index"],"sweep_candle_index":i,"sweep_distance_atr":round(s,4),"reclaim_distance_atr":round(r,4),"scope":"EXTERNAL"}))
    if lo:
        s = (lo["price"] - bars[i]["low"]) / atr; r = (bars[i]["close"] - lo["price"]) / atr
        if s >= SWEEP_MIN_ATR and r >= RECLAIM_MIN_ATR: found.append((r, {"event":"SWEEP_RECLAIM","direction":UP,"confirmed":True,"closed_candle_confirmed":True,"level":lo["price"],"swing_index":lo["index"],"sweep_candle_index":i,"sweep_distance_atr":round(s,4),"reclaim_distance_atr":round(r,4),"scope":"EXTERNAL"}))
    return max(found, key=lambda x: x[0])[1] if found else {"event":"NO_SWEEP_RECLAIM","direction":NEUTRAL,"confirmed":False}


def _sweep_failure(bars, highs, lows, atr, prior_structure=NEUTRAL):
    if not bars or atr <= 0: return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}
    i = len(bars) - 1
    if prior_structure == UP and highs:
        p = _latest(highs, {"HH"}, i - 1)
        if p and bars[i-1]["close"] > p["price"] and bars[i]["close"] <= p["price"] - RECLAIM_MIN_ATR * atr:
            return {"event":"FAILED_BOS","direction":DOWN,"confirmed":True,"closed_candle_confirmed":True,"level":p["price"],"break_candle_index":i-1,"failure_candle_index":i}
    if prior_structure == DOWN and lows:
        p = _latest(lows, {"LL"}, i - 1)
        if p and bars[i-1]["close"] < p["price"] and bars[i]["close"] >= p["price"] + RECLAIM_MIN_ATR * atr:
            return {"event":"FAILED_BOS","direction":UP,"confirmed":True,"closed_candle_confirmed":True,"level":p["price"],"break_candle_index":i-1,"failure_candle_index":i}
    return {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False}


def _lifecycle(current, failure, history, active, last_index):
    if failure.get("confirmed") and failure.get("current"):
        return {"stage":"FAILED_BREAK_RECLAIM","current":True,"active":False,"accepted":False,"follow_through":False,"failure":True,"terminal":True,"age_bars":0,"follow_through_bars":0,"level":failure["level"],"break_candle_index":failure["break_candle_index"],"failure_candle_index":failure.get("failure_candle_index")}
    if current.get("confirmed"):
        return {"stage":"CURRENT_BREAK_AWAITING_FOLLOW_THROUGH","current":True,"active":True,"accepted":False,"follow_through":False,"failure":False,"terminal":False,"age_bars":0,"follow_through_bars":0,"level":current["level"],"break_candle_index":current["break_candle_index"]}
    if active:
        age = last_index - active["break_candle_index"]; accepted = bool(active.get("accepted"))
        return {"stage":"CURRENT_BREAK_AWAITING_FOLLOW_THROUGH" if age == 0 else "HISTORICAL_ACCEPTED_BREAK" if accepted else "HISTORICAL_BREAK_AWAITING_FOLLOW_THROUGH","current":age == 0,"active":age == 0,"accepted":accepted,"follow_through":accepted,"failure":False,"terminal":age > 0,"age_bars":age,"follow_through_bars":active.get("follow_through_bars",0),"level":active["level"],"break_candle_index":active["break_candle_index"],"acceptance_candle_index":active.get("acceptance_candle_index")}
    if history:
        x = history[-1]; failed = x.get("status") == "FAILED_BREAK_RECLAIMED"; accepted = x.get("status") == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH"
        return {"stage":"HISTORICAL_FAILED_BREAK" if failed else "HISTORICAL_ACCEPTED_BREAK" if accepted else "HISTORICAL_BREAK","current":False,"active":False,"accepted":accepted,"follow_through":accepted,"failure":failed,"terminal":True,"age_bars":last_index-x["break_candle_index"],"follow_through_bars":x.get("follow_through_bars",0),"level":x["level"],"break_candle_index":x["break_candle_index"]}
    return {"stage":"NO_CONFIRMED_BREAK","current":False,"active":False,"accepted":False,"follow_through":False,"failure":False,"terminal":False,"age_bars":None,"follow_through_bars":0,"level":None,"break_candle_index":None}


def _invalidation(bars, structure, protected):
    level = protected.get("invalidation_level")
    base = {"direction":structure,"level":level,"type":protected.get("invalidation_type"),"confirmed":False,"closed_candle_confirmed":False,"source_label":protected.get("primary_label"),"source_index":None,"invalidates_current_external_thesis":False,"does_not_confirm_reversal":True}
    if not bars or structure not in {UP,DOWN} or level is None: return base
    atr = max(_atr(bars), 1e-12)
    ok = (structure == UP and bars[-1]["close"] <= level - RECLAIM_MIN_ATR * atr) or (structure == DOWN and bars[-1]["close"] >= level + RECLAIM_MIN_ATR * atr)
    p = protected.get("protected_high") if structure == DOWN else protected.get("protected_low")
    base.update({"confirmed":ok,"closed_candle_confirmed":True,"source_label":p.get("label") if p else None,"source_index":p.get("index") if p else None,"invalidates_current_external_thesis":ok})
    return base


def _authority(ext, inte, ec, ic, bos, failure, protected, sweep, invalidation, slope=NEUTRAL, slope_quality=0.0):
    score = 0.35 if ext in {UP,DOWN} else 0.0; support = []; penalties = []
    if ext in {UP,DOWN}: support.append(f"EXTERNAL_{ext}_PRIMARY")
    if ext in {UP,DOWN} and inte == ext: score += 0.20; support.append("INTERNAL_ALIGNS_WITH_EXTERNAL")
    elif inte in {UP,DOWN}: penalties.append("INTERNAL_COUNTER_STRUCTURE_CONTEXT_ONLY")
    if protected.get("primary_level") is not None:
        score += 0.15 if protected.get("anchor_quality") == "IDEAL" else 0.07; support.append("PROTECTED_PRIMARY_STRUCTURE_IDENTIFIED")
    else: penalties.append("PROTECTED_PRIMARY_STRUCTURE_MISSING")
    if bos.get("confirmed"): score += 0.15; support.append("CURRENT_CLOSED_CANDLE_BREAK")
    if failure.get("confirmed") and failure.get("current"): score -= 0.35; penalties.append("BREAK_FAILED_AND_RECLAIMED")
    if sweep.get("confirmed"): support.append("LIQUIDITY_SWEEP_RECLAIM_SEPARATED_FROM_BOS")
    if invalidation.get("confirmed"): score -= 0.40; penalties.append("PROTECTED_STRUCTURE_INVALIDATED")
    penalties.append("COUNT_STATE_DESCRIPTIVE_ONLY")
    score = round(max(0, min(1, score)), 4)
    return {"score":score,"level":"HIGH" if score >= 0.8 else "MEDIUM" if score >= 0.55 else "LOW","support":support,"penalties":penalties,
            "primary":"EXTERNAL_STRUCTURE_HAS_AUTHORITY; INTERNAL_STRUCTURE_IS_CONTEXT; COUNT_IS_DESCRIPTIVE; CLOSED_CANDLE_INVALIDATION_IS_DECISIVE",
            "authority_basis":"EXTERNAL_STRUCTURE","authority_direction":ext,"decision_rule":"EXTERNAL_FIRST_INTERNAL_CONTEXT_COUNT_DESCRIPTIVE",
            "why":f"External structure {ext} is authoritative; internal structure is contextual; count state cannot override confirmed structure."
                  if ext in {UP,DOWN} else "No directional external structure is confirmed, so authority remains unresolved.",
            "explanation":"PRIMARY=EXTERNAL_STRUCTURE; INTERNAL=CONTEXT; COUNT=DESCRIPTIVE_ONLY; HISTORICAL_EVENTS_CANNOT_OVERRIDE_CURRENT_STATE"}


def _state(ext, inte, bos, failure, sweep, invalidation, life):
    if invalidation.get("confirmed"): return "STRUCTURE_INVALIDATED"
    if failure.get("confirmed") and failure.get("current"): return "STRUCTURE_FAILURE"
    if bos.get("confirmed"): return "CHANGE_OF_CHARACTER" if bos["event"] == "CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"
    if life.get("stage") == "CURRENT_BREAK_ACCEPTED": return "BREAK_ACCEPTED"
    if ext in {UP,DOWN} and inte == ext: return "CONTINUATION"
    if ext in {UP,DOWN} and inte in {UP,DOWN} and ext != inte: return "STRUCTURE_CONFLICT"
    if ext in {UP,DOWN} and inte == MIXED: return "INTERNAL_CONFLICT"
    if ext == MIXED and inte in {UP,DOWN}: return "TRANSITION"
    if sweep.get("confirmed"): return "LIQUIDITY_RECLAIM_CONTEXT"
    return "RANGE_OR_UNCLEAR"


def _empty(status, reasons):
    p = _protected_structure(NEUTRAL, [], [])
    return {"architecture":ARCHITECTURE,"reasoning_role":"MARKET_STRUCTURE_ANALYST","question":QUESTION,"analysis_status":status,"finding":"INSUFFICIENT_DATA","direction":NEUTRAL,"structural_bias":NEUTRAL,"structure_state":"RANGE_OR_UNCLEAR","internal_structure":{"state":NEUTRAL,"count_state":NEUTRAL},"external_structure":{"state":NEUTRAL,"count_state":NEUTRAL},"internal_count_state":NEUTRAL,"external_count_state":NEUTRAL,"swing_map":{"internal_highs":[],"internal_lows":[],"external_highs":[],"external_lows":[]},"bos":{"event":"NO_BOS","direction":NEUTRAL,"confirmed":False},"failure":{"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False},"sweep_reclaim":{"event":"NO_SWEEP_RECLAIM","direction":NEUTRAL,"confirmed":False},"break_lifecycle":{"stage":"NO_CONFIRMED_BREAK"},"protected_structure":p,"structural_invalidation":{"confirmed":False,"level":None,"type":"NO_DIRECTIONAL_INVALIDATION_LEVEL"},"protected_level_break":{"confirmed":False},"structure_authority":0.0,"authority_detail":{"score":0.0,"level":"LOW","primary":"EXTERNAL_STRUCTURE_HAS_AUTHORITY"},"structure_strength":0.0,"confidence":0.0,"evidence":[],"conflicts":reasons,"reason_codes":reasons,"observations":reasons,"reasoning_trace":{"external_is_authority":True,"closed_candle_only":True,"upstream_inputs_used":False,"internal_bos_has_market_authority":False,"count_is_authority":False,"slope_is_structural_authority":False},"trade_decision_authority":False,"decision_authority":"E9_ONLY","decision":None,"gate":None,"specialists_active":False,"specialists_status":"PAUSED","sub_engines_active":False,"sub_engines_status":"PAUSED","specialists":{}}


def analyze_e3(bars):
    b, data = _clean(bars)
    if len(b) < MIN_CANDLES: return _empty("INCOMPLETE", ["INSUFFICIENT_CANDLES"] + data[:8])
    atr = _atr(b)
    ih, il = _compress(_pivots(b,"high",IR),atr,"high"), _compress(_pivots(b,"low",IR),atr,"low")
    eh, el = _compress(_pivots(b,"high",ER),atr,"high"), _compress(_pivots(b,"low",ER),atr,"low")
    ihl, ill = _label(ih,il,atr); ehl, ell = _label(eh,el,atr)
    inte, ext = _resolve_structure(ihl,ill), _resolve_external_state(ehl,ell)
    ic, ec = _count(ihl,ill), _count(ehl,ell); ics, ecs = _counts(ihl,ill), _counts(ehl,ell)
    protected = _protected_structure(ext,ehl,ell)
    eb = _current_break(b,ehl,ell,atr,ext,"EXTERNAL"); ib = _current_break(b,ihl,ill,atr,inte,"INTERNAL")
    history, active = _break_history(b,ehl,ell,atr,ext)
    failure = {"event":"NO_FAILURE","direction":NEUTRAL,"confirmed":False,"current":False}
    for x in reversed(history):
        if x.get("status") == "FAILED_BREAK_RECLAIMED": failure = _failure(b,x,atr); break
    sweep = _sweep_reclaim(b,ehl,ell,atr,ext); invalidation = _invalidation(b,ext,protected)
    life = _lifecycle(eb,failure,history,active,len(b)-1); auth = _authority(ext,inte,ec,ic,eb,failure,protected,sweep,invalidation)
    state = _state(ext,inte,eb,failure,sweep,invalidation,life)
    reasons = []
    if ext != ec: reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE_DESCRIPTIVE_ONLY")
    if inte != ic: reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE_DESCRIPTIVE_ONLY")
    if ib["confirmed"] and not eb["confirmed"]: reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if eb["confirmed"]: reasons.append("CURRENT_CLOSED_CANDLE_BREAK_CONFIRMED")
    if life["stage"] == "CURRENT_BREAK_AWAITING_FOLLOW_THROUGH": reasons.append("BREAK_FOLLOW_THROUGH_PENDING")
    if failure.get("confirmed"): reasons.append("CURRENT_STRUCTURAL_BREAK_FAILED_AND_RECLAIMED" if failure.get("current") else "HISTORICAL_STRUCTURAL_BREAK_FAILED_AND_RECLAIMED")
    if sweep.get("confirmed"): reasons.append("SWEEP_RECLAIM_SEPARATED_FROM_BOS")
    if invalidation.get("confirmed"): reasons.append("PROTECTED_STRUCTURE_INVALIDATED")
    if protected.get("anchor_quality") == "NON_IDEAL": reasons.append("PROTECTED_ANCHOR_NON_IDEAL_BUT_REAL")
    reasons = list(dict.fromkeys(reasons + data[:8])); conflicts = []
    if ext != ec: conflicts.append("EXTERNAL_COUNT_STATE_IS_NOT_AUTHORITY")
    if inte != ic: conflicts.append("INTERNAL_COUNT_STATE_IS_NOT_AUTHORITY")
    if ext in {UP,DOWN} and inte in {UP,DOWN} and ext != inte: conflicts.append("INTERNAL_VS_EXTERNAL_STRUCTURE")
    if ib["confirmed"] and not eb["confirmed"]: conflicts.append("INTERNAL_BREAK_VS_EXTERNAL_AUTHORITY")
    if failure.get("confirmed") and not failure.get("current"): conflicts.append("HISTORICAL_FAILURE_CANNOT_OVERRIDE_CURRENT_STRUCTURE")
    if failure.get("current"): conflicts.append("BREAK_FAILED_RECLAIMED")
    if invalidation.get("confirmed"): conflicts.append("PROTECTED_STRUCTURE_INVALIDATED")
    if life.get("stage") in {"HISTORICAL_ACCEPTED_BREAK","HISTORICAL_FAILED_BREAK"}: conflicts.append("HISTORICAL_EVENT_NOT_CURRENT_EVENT")
    finding = "STRUCTURE_INVALIDATED" if invalidation.get("confirmed") else "STRUCTURE_FAILURE=" + failure["direction"] if failure.get("current") else eb["event"] if eb["confirmed"] else f"{ext}_STRUCTURE_WITH_INTERNAL_CONFLICT" if ext in {UP,DOWN} and inte in {UP,DOWN} and ext != inte else f"{ext}_STRUCTURE" if ext in {UP,DOWN} else "MIXED_STRUCTURE"
    direction = failure["direction"] if failure.get("current") else eb["direction"] if eb["confirmed"] else ext if ext in {UP,DOWN} else sweep["direction"] if sweep.get("confirmed") else NEUTRAL
    conf = min(1.0, 0.40 + 0.55 * auth["score"] + (0.10 if eb["confirmed"] else 0.0)); conf = min(conf,0.60) if failure.get("current") or invalidation.get("confirmed") else conf
    evidence = [f"external_structure={ext}",f"internal_structure={inte}",f"external_count_state={ec}",f"internal_count_state={ic}",f"external_bos={eb['event']}",f"internal_bos={ib['event']}",f"sweep_reclaim={sweep['event']}",f"break_lifecycle={life['stage']}",f"protected_primary_level={protected['primary_level']}",f"protected_anchor_quality={protected.get('anchor_quality')}",f"structure_authority={auth['score']}","count_state_role=DESCRIPTIVE_NOT_AUTHORITY","historical_events_do_not_override_current_state"]
    trace = {"external_state":ext,"internal_state":inte,"external_count_state":ec,"internal_count_state":ic,"external_bos_confirmed":eb["confirmed"],"internal_bos_confirmed":ib["confirmed"],"internal_bos_has_market_authority":False,"external_is_authority":True,"closed_candle_only":True,"protected_structure_is_invalidation_anchor":True,"protected_level_break_invalidates_current_external_thesis":invalidation["confirmed"],"break_lifecycle_stage":life["stage"],"authority_explanation":auth["explanation"],"authority_basis":auth["authority_basis"],"authority_direction":auth["authority_direction"],"upstream_inputs_used":False,"upstream_direction_used":False,"upstream_decisions_used":False,"upstream_gates_used":False,"count_is_authority":False,"slope_is_structural_authority":False}
    return {"architecture":ARCHITECTURE,"reasoning_role":"MARKET_STRUCTURE_ANALYST","question":QUESTION,"analysis_status":"COMPLETE","finding":finding,"direction":direction,"structural_bias":ext if ext in {UP,DOWN} else NEUTRAL,"structure_state":state,"internal_structure":{"state":inte,"count_state":ic,"counts":ics},"external_structure":{"state":ext,"count_state":ec,"counts":ecs},"internal_count_state":ic,"external_count_state":ec,"internal_counts":ics,"external_counts":ecs,"internal_sequence":"→".join(x["label"] for x in sorted(ihl+ill,key=lambda x:x["index"])[-12:]),"external_sequence":"→".join(x["label"] for x in sorted(ehl+ell,key=lambda x:x["index"])[-12:]),"swing_map":{"internal_highs":ihl,"internal_lows":ill,"external_highs":ehl,"external_lows":ell},"atr14":round(atr,8),"closed_candles":len(b),"bos":eb,"external_bos":eb["event"],"internal_bos":ib["event"],"external_bos_detail":eb,"internal_bos_detail":ib,"failure":failure,"structural_failure":failure,"sweep_reclaim":sweep,"break_lifecycle":life,"break_history":history[-5:],"protected_structure":protected,"protected_high":protected["protected_high"]["price"] if protected.get("protected_high") else None,"protected_low":protected["protected_low"]["price"] if protected.get("protected_low") else None,"structural_invalidation":invalidation,"protected_level_break":invalidation,"BOS_type":eb["event"],"BOS_level":eb.get("level"),"BOS_candle_index":eb.get("break_candle_index"),"structure_strength":auth["score"],"structure_authority":auth["score"],"authority_detail":auth,"confidence":round(conf,4),"evidence":evidence,"conflicts":conflicts,"reason_codes":reasons,"observations":[f"closed_candles={len(b)}",f"atr14={round(atr,8)}"]+evidence,"reasoning_trace":trace,"upstream_inputs_used":False,"upstream_direction_used":False,"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False,"trade_decision_authority":False,"decision_authority":"E9_ONLY","decision":None,"gate":None,"specialists_active":False,"specialists_status":"PAUSED","sub_engines_active":False,"sub_engines_status":"PAUSED","specialists":{}}


__all__=["analyze_e3","_compress","_bos","_sweep_failure","_current_break","_break_history","_failure","_sweep_reclaim","_state","_resolve_external_state","_protected_structure","_authority","_lifecycle","_invalidation"]
