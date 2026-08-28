from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V10"
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
            reasons.append(f"bar_{i}_not_mapping")
            continue
        o, h, l, c = [_num(b.get(k)) for k in ("open", "high", "low", "close")]
        if any(x is None for x in (o, h, l, c)):
            reasons.append(f"bar_{i}_ohlc_invalid")
            continue
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent")
            continue
        out.append({"open": o, "high": h, "low": l, "close": c})
    return out, reasons


def _tr(b, i):
    if i <= 0:
        return 0.0
    x, p = b[i], b[i - 1]["close"]
    return max(x["high"] - x["low"], abs(x["high"] - p), abs(x["low"] - p))


def _atr(b, p=14):
    if len(b) <= 1:
        return 0.0
    return mean(_tr(b, i) for i in range(max(1, len(b) - p), len(b)))


def _atr_at(b, i, p=14):
    if i <= 0:
        return 0.0
    return mean(_tr(b, j) for j in range(max(1, i - p + 1), i + 1))


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
        if ok:
            out.append((i, x, i + radius))
    return out


def _compress(points, atr, side=None, spacing=2):
    """Collapse clustered pivots while retaining the meaningful extreme."""
    if isinstance(side, int) and spacing == 2:
        spacing, side = side, None
    out = []
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        q = out[-1]
        if abs(p[1] - q[1]) <= tol:
            out[-1] = p
        elif side == "high" and p[1] > q[1]:
            out[-1] = p
        elif side == "low" and p[1] < q[1]:
            out[-1] = p
        elif side is None:
            out[-1] = p
    return out


def _label(hp, lp, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    hs, prev = [], None
    for i, p, ci in hp:
        d = 0.0 if prev is None else p - prev[1]
        lab = "SWING_HIGH" if prev is None else "EQH" if abs(d) <= tol else "HH" if d > 0 else "LH"
        hs.append({"index": i, "price": round(p, 8), "label": lab, "confirmation_index": ci})
        prev = (i, p)
    ls, prev = [], None
    for i, p, ci in lp:
        d = 0.0 if prev is None else p - prev[1]
        lab = "SWING_LOW" if prev is None else "EQL" if abs(d) <= tol else "HL" if d > 0 else "LL"
        ls.append({"index": i, "price": round(p, 8), "label": lab, "confirmation_index": ci})
        prev = (i, p)
    return hs, ls


def _latest(xs, labels, max_confirm=None):
    for x in reversed(xs):
        if x["label"] in labels and (max_confirm is None or x["confirmation_index"] <= max_confirm):
            return x
    return None


def _count(h, l, n=8):
    z = h[-n:] + l[-n:]
    bull = sum(x["label"] in {"HH", "HL"} for x in z)
    bear = sum(x["label"] in {"LH", "LL"} for x in z)
    if bull >= bear + 2:
        return UP
    if bear >= bull + 2:
        return DOWN
    if bull == bear == 0:
        return NEUTRAL
    return MIXED


def _counts(h, l, n=8):
    c = {k: 0 for k in ("HH", "HL", "LH", "LL", "EQH", "EQL")}
    for x in h[-n:] + l[-n:]:
        if x["label"] in c:
            c[x["label"]] += 1
    return c


def _classify(h, l):
    if len(h) < 2 or len(l) < 2:
        return NEUTRAL
    hu = h[-1]["price"] > h[-2]["price"]
    hd = h[-1]["price"] < h[-2]["price"]
    lu = l[-1]["price"] > l[-2]["price"]
    ld = l[-1]["price"] < l[-2]["price"]
    return UP if hu and lu else DOWN if hd and ld else MIXED


def _protected(s, h, l):
    if s == UP:
        low = _latest(l, {"HL"})
        high = _latest(h, {"HH", "EQH"})
    elif s == DOWN:
        high = _latest(h, {"LH", "EQH"})
        low = _latest(l, {"LL", "EQL"})
    else:
        high = _latest(h, {"HH", "LH", "EQH"})
        low = _latest(l, {"HL", "LL", "EQL"})
    return {"protected_high": high, "protected_low": low}


def _quality(bar, level, direction, atr):
    if atr <= 0 or level is None:
        return {"confirmed": False}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body = abs(bar["close"] - bar["open"]) / atr
    location = (bar["close"] - bar["low"]) / rng
    dist = ((bar["close"] - level) if direction == UP else (level - bar["close"])) / atr
    displacement = body >= BOS_BODY_ATR
    close_quality = location >= BOS_CLOSE_LOCATION if direction == UP else location <= 1 - BOS_CLOSE_LOCATION
    return {
        "confirmed": dist >= BOS_CLOSE_ATR and (displacement or close_quality),
        "distance_atr": round(max(0.0, dist), 4),
        "body_atr": round(body, 4),
        "close_location": round(location, 4),
        "displacement_ok": displacement,
        "close_beyond_level": dist >= BOS_CLOSE_ATR,
    }


def _event(bar, pivot, direction, atr, event, scope, idx):
    q = _quality(bar, pivot["price"], direction, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return {
        "event": event,
        "direction": direction,
        "confirmed": True,
        "scope": scope,
        "level": pivot["price"],
        "swing_index": pivot["index"],
        "swing_label": pivot["label"],
        "break_candle_index": idx,
        **{k: q[k] for k in ("distance_atr", "body_atr", "close_location", "displacement_ok", "close_beyond_level")},
    }


def _current_break(bars, highs, lows, atr, structure, scope="EXTERNAL", idx=None):
    idx = len(bars) - 1 if idx is None else idx
    if idx < 0 or atr <= 0 or not bars:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    max_confirm = idx - 1
    hi = _latest(highs, {"HH", "LH", "EQH"}, max_confirm)
    lo = _latest(lows, {"HL", "LL", "EQL"}, max_confirm)
    out = []
    if hi and (idx == 0 or bars[idx - 1]["close"] <= hi["price"]):
        q = _quality(bars[idx], hi["price"], UP, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if structure == DOWN else "CONFIRMED_BOS"
            out.append((q["distance_atr"], _event(bars[idx], hi, UP, atr, event, scope, idx)))
    if lo and (idx == 0 or bars[idx - 1]["close"] >= lo["price"]):
        q = _quality(bars[idx], lo["price"], DOWN, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if structure == UP else "CONFIRMED_BOS"
            out.append((q["distance_atr"], _event(bars[idx], lo, DOWN, atr, event, scope, idx)))
    return max(out, key=lambda x: x[0])[1] if out else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    return _current_break(bars, highs, lows, atr, prior_structure, scope)


def _break_history(bars, highs, lows, atr, structure):
    events = []
    active = None
    for i in range(len(bars)):
        if active:
            level, direction = active["level"], active["direction"]
            active["follow_through_bars"] += 1
            reclaimed = (direction == UP and bars[i]["close"] <= level - RECLAIM_MIN_ATR * atr) or (direction == DOWN and bars[i]["close"] >= level + RECLAIM_MIN_ATR * atr)
            if reclaimed:
                active = dict(active, status="FAILED_BREAK_RECLAIMED", failure_candle_index=i)
                events.append(active)
                active = None
            elif active["follow_through_bars"] >= FOLLOW_THROUGH_BARS:
                active = dict(active, status="ACCEPTED_BREAK_WITH_FOLLOW_THROUGH")
                events.append(active)
                active = None
        if active is None:
            e = _current_break(bars, highs, lows, atr, structure, "EXTERNAL", i)
            if e["confirmed"]:
                active = {
                    "event": e["event"],
                    "direction": e["direction"],
                    "level": e["level"],
                    "swing_index": e["swing_index"],
                    "break_candle_index": i,
                    "status": "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH",
                    "follow_through_bars": 0,
                }
    return events, active


def _failure(bars, active, atr):
    if not active:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    level, direction = active["level"], active["direction"]
    start = active["break_candle_index"] + 1
    for i in range(start, len(bars)):
        reclaimed = (direction == UP and bars[i]["close"] <= level - RECLAIM_MIN_ATR * atr) or (direction == DOWN and bars[i]["close"] >= level + RECLAIM_MIN_ATR * atr)
        if reclaimed:
            return {
                "event": "FAILED_BOS",
                "direction": DOWN if direction == UP else UP,
                "confirmed": True,
                "level": level,
                "break_candle_index": active["break_candle_index"],
                "failure_candle_index": i,
                "scope": "EXTERNAL",
                "reclaim_distance_atr": round(abs(bars[i]["close"] - level) / max(atr, 1e-12), 4),
            }
    return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _sweep_reclaim(bars, highs, lows, atr, structure):
    if not bars or atr <= 0:
        return {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False}
    i = len(bars) - 1
    hi = _latest(highs, {"HH", "LH", "EQH"}, i - 1)
    lo = _latest(lows, {"HL", "LL", "EQL"}, i - 1)
    candidates = []
    if hi:
        sweep = (bars[i]["high"] - hi["price"]) / atr
        reclaim = (hi["price"] - bars[i]["close"]) / atr
        if sweep >= SWEEP_MIN_ATR and reclaim >= RECLAIM_MIN_ATR:
            candidates.append((reclaim, {"event": "SWEEP_RECLAIM", "direction": DOWN, "confirmed": True, "level": hi["price"], "swing_index": hi["index"], "sweep_candle_index": i, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4), "scope": "EXTERNAL"}))
    if lo:
        sweep = (lo["price"] - bars[i]["low"]) / atr
        reclaim = (bars[i]["close"] - lo["price"]) / atr
        if sweep >= SWEEP_MIN_ATR and reclaim >= RECLAIM_MIN_ATR:
            candidates.append((reclaim, {"event": "SWEEP_RECLAIM", "direction": UP, "confirmed": True, "level": lo["price"], "swing_index": lo["index"], "sweep_candle_index": i, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4), "scope": "EXTERNAL"}))
    return max(candidates, key=lambda x: x[0])[1] if candidates else {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False}


def _sweep_failure(bars, highs, lows, atr=None, prior_structure=MIXED):
    """Compatibility helper: only a real break followed by close-back-inside is FAILED_BOS."""
    atr = atr or _atr(bars)
    if not bars or atr <= 0:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    events, active = _break_history(bars, highs, lows, atr, prior_structure)
    failure = _failure(bars, active, atr)
    if failure["confirmed"]:
        return failure
    for x in reversed(events):
        if x.get("status") == "FAILED_BREAK_RECLAIMED":
            return {"event": "FAILED_BOS", "direction": DOWN if x["direction"] == UP else UP, "confirmed": True, "level": x["level"], "break_candle_index": x["break_candle_index"], "failure_candle_index": x["failure_candle_index"], "scope": "EXTERNAL"}
    return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _lifecycle(current, failure, history, active):
    if failure["confirmed"]:
        return {"stage": "FAILED_BREAK_RECLAIM", "current": False, "active": False, "accepted": False, "follow_through": False, "failure": True, "level": failure["level"], "break_candle_index": failure["break_candle_index"], "failure_candle_index": failure["failure_candle_index"]}
    if current["confirmed"]:
        return {"stage": "CURRENT_BREAK_AWAITING_FOLLOW_THROUGH", "current": True, "active": True, "accepted": False, "follow_through": False, "failure": False, "level": current["level"], "break_candle_index": current["break_candle_index"]}
    if active:
        return {"stage": "CURRENT_BREAK_AWAITING_FOLLOW_THROUGH", "current": active["break_candle_index"] == current.get("break_candle_index"), "active": True, "accepted": False, "follow_through": False, "failure": False, "level": active["level"], "break_candle_index": active["break_candle_index"]}
    if history:
        x = history[-1]
        return {"stage": "HISTORICAL_ACCEPTED_BREAK" if x["status"] == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH" else "HISTORICAL_FAILED_BREAK", "current": False, "active": False, "accepted": x["status"] == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH", "follow_through": x["status"] == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH", "failure": x["status"] == "FAILED_BREAK_RECLAIMED", "level": x["level"], "break_candle_index": x["break_candle_index"]}
    return {"stage": "NO_CONFIRMED_BREAK", "current": False, "active": False, "accepted": False, "follow_through": False, "failure": False, "level": None, "break_candle_index": None}


def _invalidation(bars, structure, protected):
    ph, pl = protected.get("protected_high"), protected.get("protected_low")
    if structure == UP and pl:
        confirmed = bars[-1]["close"] <= pl["price"] - RECLAIM_MIN_ATR * max(_atr(bars), 1e-12)
        return {"direction": UP, "level": pl["price"], "type": "CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW", "confirmed": confirmed, "source_label": pl["label"], "source_index": pl["index"], "invalidates_current_external_thesis": confirmed}
    if structure == DOWN and ph:
        confirmed = bars[-1]["close"] >= ph["price"] + RECLAIM_MIN_ATR * max(_atr(bars), 1e-12)
        return {"direction": DOWN, "level": ph["price"], "type": "CLOSED_CANDLE_ACCEPTANCE_ABOVE_PROTECTED_HIGH", "confirmed": confirmed, "source_label": ph["label"], "source_index": ph["index"], "invalidates_current_external_thesis": confirmed}
    return {"direction": structure, "level": None, "type": "NO_DIRECTIONAL_INVALIDATION_LEVEL", "confirmed": False, "source_label": None, "source_index": None, "invalidates_current_external_thesis": False}


def _slope(b, n=20):
    if len(b) < 5:
        return NEUTRAL, 0.0
    c = [x["close"] for x in b[-n:]]
    z = (c[-1] - c[0]) / (max(_atr(b), 1e-12) * max(1, len(c) - 1))
    return (UP if z > 0.035 else DOWN if z < -0.035 else NEUTRAL), round(min(1.0, abs(z) * 8), 4)


def _authority(ext, inte, ec, ic, bos, failure, protected, sweep, invalidation, slope, slope_quality):
    support, penalties = [], []
    score = 0.0
    if ext in {UP, DOWN}:
        score += 0.35
        support.append(f"EXTERNAL_{ext}_PRIMARY")
    else:
        penalties.append("EXTERNAL_STRUCTURE_UNRESOLVED")
    if ext in {UP, DOWN} and inte == ext:
        score += 0.20
        support.append("INTERNAL_ALIGNS_WITH_EXTERNAL")
    elif inte in {UP, DOWN}:
        penalties.append("INTERNAL_COUNTER_STRUCTURE")
    if ext in {UP, DOWN} and ec == ext:
        score += 0.15
        support.append("EXTERNAL_COUNT_CONFIRMS_SEQUENCE")
    elif ext in {UP, DOWN}:
        penalties.append("EXTERNAL_COUNT_DIVERGES")
    if protected["protected_high"] or protected["protected_low"]:
        score += 0.10
        support.append("PROTECTED_STRUCTURE_IDENTIFIED")
    else:
        penalties.append("PROTECTED_STRUCTURE_MISSING")
    if bos["confirmed"]:
        score += 0.15
        support.append("CURRENT_CLOSED_CANDLE_BREAK")
    if failure["confirmed"]:
        score -= 0.30
        penalties.append("BREAK_FAILED_AND_RECLAIMED")
    if sweep["confirmed"]:
        support.append("LIQUIDITY_SWEEP_RECLAIM_SEPARATED_FROM_BOS")
    if invalidation["confirmed"]:
        score -= 0.35
        penalties.append("PROTECTED_STRUCTURE_INVALIDATED")
    if slope != ext and ext in {UP, DOWN}:
        penalties.append("SLOPE_CONFLICT_CONTEXT_ONLY")
    score = round(max(0.0, min(1.0, score)), 4)
    level = "HIGH" if score >= 0.80 else "MEDIUM" if score >= 0.55 else "LOW"
    return {"score": score, "level": level, "support": support, "penalties": penalties, "primary": "External structure has authority; internal structure is context unless it breaks protected external structure on a closed candle.", "explanation": "PRIMARY=EXTERNAL_STRUCTURE; support=" + ",".join(support) + "; penalties=" + ",".join(penalties)}


def _state(ext, inte, bos, failure, sweep, invalidation):
    if invalidation["confirmed"]:
        return "STRUCTURE_INVALIDATED"
    if failure["confirmed"]:
        return "STRUCTURE_FAILURE"
    if bos["confirmed"]:
        return "CHANGE_OF_CHARACTER" if bos["event"] == "CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"
    if ext in {UP, DOWN} and inte == ext:
        return "CONTINUATION"
    if ext in {UP, DOWN} and inte in {UP, DOWN} and inte != ext:
        return "INTERNAL_COUNTER_MOVE"
    if ext in {UP, DOWN} and inte == MIXED:
        return "INTERNAL_CONFLICT"
    if ext == MIXED and inte in {UP, DOWN}:
        return "TRANSITION"
    if sweep["confirmed"]:
        return "LIQUIDITY_RECLAIM_CONTEXT"
    return "RANGE_OR_UNCLEAR"


def _empty(status, reasons):
    return {
        "architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
        "analysis_status": status, "finding": "INSUFFICIENT_DATA", "direction": NEUTRAL, "structural_bias": NEUTRAL,
        "structure_state": "RANGE_OR_UNCLEAR", "internal_structure": {"state": NEUTRAL, "count_state": NEUTRAL},
        "external_structure": {"state": NEUTRAL, "count_state": NEUTRAL}, "internal_count_state": NEUTRAL, "external_count_state": NEUTRAL,
        "swing_map": {"internal_highs": [], "internal_lows": [], "external_highs": [], "external_lows": []},
        "bos": {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False}, "failure": {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False},
        "sweep_reclaim": {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False}, "break_lifecycle": {"stage": "NO_CONFIRMED_BREAK", "current": False},
        "protected_structure": {"protected_high": None, "protected_low": None}, "structural_invalidation": _invalidation([], NEUTRAL, {"protected_high": None, "protected_low": None}),
        "protected_level_break": {"confirmed": False}, "structure_authority": 0.0, "authority_detail": {"score": 0.0, "level": "LOW", "primary": "External structure has authority."},
        "structure_strength": 0.0, "confidence": 0.0, "evidence": [], "conflicts": reasons, "reason_codes": reasons,
        "observations": [f"closed_candles={status}"], "reasoning_trace": {"external_is_authority": True, "closed_candle_only": True, "upstream_inputs_used": False, "slope_is_structural_authority": False, "internal_bos_has_market_authority": False, "protected_level_break_is_not_automatic_reversal": True, "protected_level_break_invalidates_current_external_thesis": False},
        "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None, "specialists_active": False, "specialists_status": "PAUSED", "specialists": {},
    }


def analyze_e3(bars):
    b, data = _clean(bars)
    if len(b) < MIN_CANDLES:
        return _empty("INCOMPLETE", ["INSUFFICIENT_CANDLES"] + data[:8])

    atr = _atr(b)
    ih = _compress(_pivots(b, "high", IR), atr, "high")
    il = _compress(_pivots(b, "low", IR), atr, "low")
    eh = _compress(_pivots(b, "high", ER), atr, "high")
    el = _compress(_pivots(b, "low", ER), atr, "low")
    ihl, ill = _label(ih, il, atr)
    ehl, ell = _label(eh, el, atr)
    inte, ext = _classify(ihl, ill), _classify(ehl, ell)
    ic, ec = _count(ihl, ill), _count(ehl, ell)
    ics, ecs = _counts(ihl, ill), _counts(ehl, ell)
    protected = _protected(ext, ehl, ell)

    eb = _current_break(b, ehl, ell, atr, ext, "EXTERNAL")
    ib = _current_break(b, ihl, ill, atr, inte, "INTERNAL")
    history, active = _break_history(b, ehl, ell, atr, ext)
    fail = _failure(b, active, atr)
    sweep = _sweep_reclaim(b, ehl, ell, atr, ext)
    invalidation = _invalidation(b, ext, protected)
    life = _lifecycle(eb, fail, history, active)
    slope, slope_quality = _slope(b)
    state = _state(ext, inte, eb, fail, sweep, invalidation)
    auth = _authority(ext, inte, ec, ic, eb, fail, protected, sweep, invalidation, slope, slope_quality)

    reasons = []
    if ext != ec:
        reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if inte != ic:
        reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if ext == MIXED:
        reasons.append("STRUCTURE_UNRESOLVED")
    if slope != ext and ext in {UP, DOWN}:
        reasons.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    if ib["confirmed"] and not eb["confirmed"]:
        reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if not eb["confirmed"]:
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if life["stage"] == "CURRENT_BREAK_AWAITING_FOLLOW_THROUGH":
        reasons.append("BREAK_FOLLOW_THROUGH_PENDING")
    if life["stage"] == "HISTORICAL_ACCEPTED_BREAK":
        reasons.append("HISTORICAL_BREAK_NOT_CURRENT_AUTHORITY")
    if fail["confirmed"]:
        reasons.append("STRUCTURAL_BREAK_FAILED_AND_RECLAIMED")
    if sweep["confirmed"]:
        reasons.append("SWEEP_RECLAIM_SEPARATED_FROM_BOS")
    if invalidation["confirmed"]:
        reasons.append("PROTECTED_STRUCTURE_INVALIDATED")
    reasons = list(dict.fromkeys(reasons + data[:8]))

    direction = NEUTRAL if invalidation["confirmed"] else ext if ext in {UP, DOWN} else eb["direction"] if eb["confirmed"] else NEUTRAL
    finding = "STRUCTURE_FAILURE=" + fail["direction"] if fail["confirmed"] else eb["event"] if eb["confirmed"] else "BULLISH_STRUCTURE" if ext == UP and inte == UP else "BEARISH_STRUCTURE" if ext == DOWN and inte == DOWN else "MIXED_STRUCTURE"
    conf = min(1.0, 0.45 + 0.45 * auth["score"] + (0.10 if eb["confirmed"] else 0.0))
    if ext == MIXED:
        conf = min(conf, 0.55)
    if fail["confirmed"]:
        conf = min(conf, 0.60)
    if life["stage"] == "CURRENT_BREAK_AWAITING_FOLLOW_THROUGH":
        conf = min(conf, 0.72)
    if invalidation["confirmed"]:
        conf = min(conf, 0.60)

    conflicts = []
    if ext != ec:
        conflicts.append("EXTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE")
    if inte != ic:
        conflicts.append("INTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE")
    if slope != ext and ext in {UP, DOWN}:
        conflicts.append("SLOPE_VS_EXTERNAL_STRUCTURE")
    if ext in {UP, DOWN} and inte in {UP, DOWN} and inte != ext:
        conflicts.append("INTERNAL_VS_EXTERNAL_STRUCTURE")
    if ib["confirmed"] and not eb["confirmed"]:
        conflicts.append("INTERNAL_BREAK_VS_EXTERNAL_AUTHORITY")
    if fail["confirmed"]:
        conflicts.append("BREAK_FAILED_RECLAIMED")
    if sweep["confirmed"] and eb["confirmed"]:
        conflicts.append("SWEEP_VS_BREAK_EVENT_DISTINCTION")
    if invalidation["confirmed"]:
        conflicts.append("PROTECTED_STRUCTURE_INVALIDATED")

    recent_high = ehl[-1] if ehl else None
    recent_low = ell[-1] if ell else None
    prior_high = ehl[-2] if len(ehl) >= 2 else None
    prior_low = ell[-2] if len(ell) >= 2 else None
    protected_level_break = {**invalidation}
    evidence = [
        f"external_structure={ext}", f"internal_structure={inte}", f"external_count_state={ec}", f"internal_count_state={ic}",
        f"external_bos={eb['event']}", f"internal_bos={ib['event']}", f"sweep_reclaim={sweep['event']}", f"break_lifecycle={life['stage']}",
        f"protected_high={protected['protected_high']['price'] if protected['protected_high'] else None}",
        f"protected_low={protected['protected_low']['price'] if protected['protected_low'] else None}",
        f"invalidation={invalidation['type']}@{invalidation['level']}", f"slope_context={slope}", f"slope_quality={slope_quality}", f"structure_authority={auth['score']}",
    ]
    trace = {
        "external_state": ext, "internal_state": inte, "external_count_state": ec, "internal_count_state": ic,
        "slope_context": slope, "slope_is_structural_authority": False, "external_bos_confirmed": eb["confirmed"],
        "internal_bos_confirmed": ib["confirmed"], "internal_bos_has_market_authority": False, "external_is_authority": True,
        "closed_candle_only": True, "protected_structure_is_invalidation_anchor": True,
        "protected_level_break_is_not_automatic_reversal": True, "protected_level_break_invalidates_current_external_thesis": invalidation["confirmed"],
        "break_lifecycle_stage": life["stage"], "authority_explanation": auth["explanation"], "upstream_inputs_used": False,
    }
    return {
        "architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION, "analysis_status": "COMPLETE",
        "finding": finding, "direction": direction, "structural_bias": ext if ext in {UP, DOWN} else NEUTRAL, "structure_state": state,
        "internal_structure": {"state": inte, "count_state": ic, "counts": ics}, "external_structure": {"state": ext, "count_state": ec, "counts": ecs},
        "internal_count_state": ic, "external_count_state": ec, "internal_counts": ics, "external_counts": ecs,
        "internal_sequence": "→".join(x["label"] for x in sorted(ihl + ill, key=lambda x: x["index"])[-12:]),
        "external_sequence": "→".join(x["label"] for x in sorted(ehl + ell, key=lambda x: x["index"])[-12:]),
        "swing_map": {"internal_highs": ihl, "internal_lows": ill, "external_highs": ehl, "external_lows": ell},
        "atr14": round(atr, 8), "closed_candles": len(b), "bos": eb, "external_bos": eb["event"], "internal_bos": ib["event"],
        "external_bos_detail": eb, "internal_bos_detail": ib, "failure": fail, "structural_failure": fail,
        "sweep_reclaim": sweep, "break_lifecycle": life, "break_history": history[-5:], "protected_structure": protected,
        "protected_high": protected["protected_high"]["price"] if protected["protected_high"] else None,
        "protected_low": protected["protected_low"]["price"] if protected["protected_low"] else None,
        "structural_invalidation": invalidation, "protected_level_break": protected_level_break,
        "BOS_type": eb["event"], "BOS_level": eb.get("level"), "BOS_candle_index": eb.get("break_candle_index"),
        "recent_high": recent_high, "recent_low": recent_low, "prior_high": prior_high, "prior_low": prior_low,
        "structure_strength": auth["score"], "structure_authority": auth["score"], "authority_detail": auth, "confidence": round(conf, 4),
        "evidence": evidence, "conflicts": conflicts, "reason_codes": reasons, "observations": [f"closed_candles={len(b)}", f"atr14={round(atr, 8)}"] + evidence,
        "reasoning_trace": trace, "slope_context": slope, "slope_quality": slope_quality,
        "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False,
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None,
        "specialists_active": False, "specialists_status": "PAUSED", "specialists": {},
    }


__all__ = ["analyze_e3", "_compress", "_bos", "_sweep_failure", "_current_break", "_break_history", "_failure"]
