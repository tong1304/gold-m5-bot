from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V40"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 40
IR, ER = 2, 5
PROMINENCE_ATR = 0.10
EQ_TOLERANCE_ATR = 0.10
BOS_CLOSE_ATR = 0.08
BOS_BODY_ATR = 0.20
BOS_CLOSE_LOCATION = 0.50
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
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict):
            reasons.append(f"bar_{i}_not_mapping")
            continue
        o, h, l, c = [_num(bar.get(k)) for k in ("open", "high", "low", "close")]
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
    x, prev = b[i], b[i - 1]["close"]
    return max(x["high"] - x["low"], abs(x["high"] - prev), abs(x["low"] - prev))


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
        if ok:
            out.append((i, x, i + radius))
    return out


def _compress(points, atr, side=None, spacing=2):
    out, tol = [], max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        q = out[-1]
        if abs(p[1] - q[1]) <= tol or (side == "high" and p[1] > q[1]) or (side == "low" and p[1] < q[1]):
            out[-1] = p
    return out


def _label(hp, lp, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    highs, lows = [], []
    prev = None
    for i, p, ci in hp:
        label = "SWING_HIGH" if prev is None else "EQH" if abs(p - prev[1]) <= tol else "HH" if p > prev[1] else "LH"
        highs.append({"index": i, "price": round(p, 8), "label": label, "confirmation_index": ci})
        prev = (i, p)
    prev = None
    for i, p, ci in lp:
        label = "SWING_LOW" if prev is None else "EQL" if abs(p - prev[1]) <= tol else "HL" if p > prev[1] else "LL"
        lows.append({"index": i, "price": round(p, 8), "label": label, "confirmation_index": ci})
        prev = (i, p)
    return highs, lows


def _latest(xs, labels, max_confirm=None):
    for x in reversed(sorted(xs, key=lambda z: z["index"])):
        if x["label"] in labels and (max_confirm is None or x["confirmation_index"] <= max_confirm):
            return x
    return None


def _counts(h, l, n=8):
    counts = {k: 0 for k in ("HH", "HL", "LH", "LL", "EQH", "EQL")}
    for x in sorted(h + l, key=lambda z: z["index"])[-n:]:
        if x["label"] in counts:
            counts[x["label"]] += 1
    return counts


def _count(h, l, n=8):
    c = _counts(h, l, n)
    bull, bear = c["HH"] + c["HL"], c["LH"] + c["LL"]
    if bull >= bear + 2:
        return UP
    if bear >= bull + 2:
        return DOWN
    if bull == bear == 0:
        return NEUTRAL
    return MIXED


def _semantic_structure_state(highs, lows):
    """Resolve structure from ordered swing relationships, never from counts alone.

    A directional state is promoted only when the latest directional swing is part
    of a valid same-direction leg. A newer opposite leg cancels any stale pair.
    """
    events = sorted(
        [x for x in highs + lows if x["label"] in {"HH", "HL", "LH", "LL"}],
        key=lambda x: (x["index"], 0 if x["label"] in {"HH", "LH"} else 1),
    )
    state = NEUTRAL
    last_high = None
    last_low = None
    transitions = []
    for x in events:
        label = x["label"]
        if label in {"HH", "LH"}:
            last_high = x
            if last_low:
                if label == "HH" and last_low["label"] == "HL":
                    state = UP
                elif label == "LH" and last_low["label"] == "LL":
                    state = DOWN
                elif label == "HH" and last_low["label"] == "LL":
                    state = MIXED
                elif label == "LH" and last_low["label"] == "HL":
                    state = MIXED
        else:
            last_low = x
            if last_high:
                if label == "HL" and last_high["label"] == "HH":
                    state = UP
                elif label == "LL" and last_high["label"] == "LH":
                    state = DOWN
                elif label == "HL" and last_high["label"] == "LH":
                    state = MIXED
                elif label == "LL" and last_high["label"] == "HH":
                    state = MIXED
        transitions.append({"index": x["index"], "label": label, "state_after": state})

    latest = events[-1] if events else None
    return {
        "state": state,
        "basis": "ORDERED_ALTERNATING_SWING_RELATIONSHIPS",
        "counts_used_as_authority": False,
        "latest_directional_event": latest,
        "latest_hh": _latest(highs, {"HH"}),
        "latest_hl": _latest(lows, {"HL"}),
        "latest_lh": _latest(highs, {"LH"}),
        "latest_ll": _latest(lows, {"LL"}),
        "bullish_pair": bool(last_high and last_low and last_high["label"] == "HH" and last_low["label"] == "HL"),
        "bearish_pair": bool(last_high and last_low and last_high["label"] == "LH" and last_low["label"] == "LL"),
        "structural_sequence": "→".join(x["label"] for x in events[-12:]),
        "transitions": transitions[-12:],
        "semantic_rule": "LATEST_ORDERED_SWING_RELATIONSHIP;_STALE_PAIRS_NEVER_OVERRIDE_NEW_OPPOSITE_LEG",
    }


def _semantic_pair(h, l):
    return _semantic_structure_state(h, l)["state"]


def _resolve_structure(h, l):
    return _semantic_pair(h, l)


def _resolve_external_state(h, l):
    return _semantic_pair(h, l)


def _classify(h, l):
    return _semantic_pair(h, l)


def _protected_structure(direction, h, l):
    """Return only a structurally valid protected anchor; never promote a fallback."""
    highs, lows = sorted(h, key=lambda x: x["index"]), sorted(l, key=lambda x: x["index"])
    if direction == UP:
        impulse = _latest(highs, {"HH"})
        anchor = _latest(lows, {"HL"}) if impulse else None
        if anchor and impulse and anchor["index"] >= impulse["index"]:
            anchor = None
        if anchor and any(x["label"] == "LL" and anchor["index"] < x["index"] < impulse["index"] for x in lows):
            anchor = None
        return {
            "protected_high": impulse,
            "protected_low": anchor,
            "primary_direction": UP,
            "primary_level": anchor["price"] if anchor else None,
            "primary_label": anchor["label"] if anchor else None,
            "invalidation_level": anchor["price"] if anchor else None,
            "invalidation_type": "CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW",
            "anchor_quality": "IDEAL" if anchor else "MISSING",
            "anchor_status": "ACTIVE" if anchor else "MISSING",
            "anchor_index": anchor["index"] if anchor else None,
            "anchor_price": anchor["price"] if anchor else None,
            "anchor_is_ideal": bool(anchor),
            "candidate_anchor": None,
            "why_primary": "A bullish protected low must be the latest confirmed HL before the impulse HH and must not already be structurally broken.",
        }
    if direction == DOWN:
        impulse = _latest(lows, {"LL"})
        anchor = _latest(highs, {"LH"}) if impulse else None
        if anchor and impulse and anchor["index"] >= impulse["index"]:
            anchor = None
        if anchor and any(x["label"] == "HH" and anchor["index"] < x["index"] < impulse["index"] for x in highs):
            anchor = None
        return {
            "protected_high": anchor,
            "protected_low": impulse,
            "primary_direction": DOWN,
            "primary_level": anchor["price"] if anchor else None,
            "primary_label": anchor["label"] if anchor else None,
            "invalidation_level": anchor["price"] if anchor else None,
            "invalidation_type": "CLOSED_CANDLE_ACCEPTANCE_ABOVE_PROTECTED_HIGH",
            "anchor_quality": "IDEAL" if anchor else "MISSING",
            "anchor_status": "ACTIVE" if anchor else "MISSING",
            "anchor_index": anchor["index"] if anchor else None,
            "anchor_price": anchor["price"] if anchor else None,
            "anchor_is_ideal": bool(anchor),
            "candidate_anchor": None,
            "why_primary": "A bearish protected high must be the latest confirmed LH before the impulse LL and must not already be structurally broken.",
        }
    return {
        "protected_high": _latest(highs, {"HH", "LH"}),
        "protected_low": _latest(lows, {"HL", "LL"}),
        "primary_direction": NEUTRAL,
        "primary_level": None,
        "primary_label": None,
        "invalidation_level": None,
        "invalidation_type": "NO_DIRECTIONAL_INVALIDATION_LEVEL",
        "anchor_quality": "UNRESOLVED",
        "anchor_status": "MISSING",
        "anchor_index": None,
        "anchor_price": None,
        "anchor_is_ideal": False,
        "candidate_anchor": None,
        "why_primary": "No directional external structure has authority; no protected invalidation level is promoted.",
    }


def _quality(bar, level, direction, atr):
    if atr <= 0 or level is None:
        return {"confirmed": False, "distance_atr": 0.0, "body_atr": 0.0, "close_location": 0.0, "displacement_ok": False, "close_beyond_level": False}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body = abs(bar["close"] - bar["open"]) / atr
    location = (bar["close"] - bar["low"]) / rng
    distance = ((bar["close"] - level) if direction == UP else (level - bar["close"])) / atr
    close_ok = distance >= BOS_CLOSE_ATR
    displacement = body >= BOS_BODY_ATR or (location >= BOS_CLOSE_LOCATION if direction == UP else location <= 1 - BOS_CLOSE_LOCATION)
    return {"confirmed": bool(close_ok and displacement), "distance_atr": round(max(0.0, distance), 4), "body_atr": round(body, 4), "close_location": round(location, 4), "displacement_ok": displacement, "close_beyond_level": close_ok}


def _event(bar, pivot, direction, atr, event, scope, idx):
    q = _quality(bar, pivot["price"], direction, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope, **q}
    return {"event": event, "direction": direction, "confirmed": True, "scope": scope, "level": pivot["price"], "swing_index": pivot["index"], "swing_label": pivot["label"], "break_candle_index": idx, "closed_candle_confirmed": True, **q}


def _current_break(bars, highs, lows, atr, structure, scope="EXTERNAL", idx=None):
    idx = len(bars) - 1 if idx is None else idx
    if idx < 1 or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope, "closed_candle_confirmed": False}
    hh = _latest(highs, {"HH"}, idx - 1)
    lh = _latest(highs, {"LH"}, idx - 1)
    hl = _latest(lows, {"HL"}, idx - 1)
    ll = _latest(lows, {"LL"}, idx - 1)
    c, pc = bars[idx]["close"], bars[idx - 1]["close"]
    candidates = []
    if structure == UP:
        if hh and c > hh["price"] and pc <= hh["price"]:
            candidates.append((hh, UP, "CONFIRMED_BOS"))
        if hl and c < hl["price"] and pc >= hl["price"]:
            candidates.append((hl, DOWN, "CONFIRMED_CHOCH"))
    elif structure == DOWN:
        if ll and c < ll["price"] and pc >= ll["price"]:
            candidates.append((ll, DOWN, "CONFIRMED_BOS"))
        if lh and c > lh["price"] and pc <= lh["price"]:
            candidates.append((lh, UP, "CONFIRMED_CHOCH"))
    events = [_event(bars[idx], p, d, atr, e, scope, idx) for p, d, e in candidates]
    events = [e for e in events if e["confirmed"]]
    if not events:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope, "closed_candle_confirmed": True}
    return max(events, key=lambda e: e["distance_atr"])


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    return _current_break(bars, highs, lows, atr, prior_structure, scope)


def _structure_at(highs, lows, idx):
    return _resolve_structure([x for x in highs if x["confirmation_index"] <= idx], [x for x in lows if x["confirmation_index"] <= idx])


def _break_history(bars, highs, lows, atr, structure):
    history, active = [], None
    for i in range(len(bars)):
        if active:
            age = i - active["break_candle_index"]
            active["follow_through_bars"] = age
            d, level = active["direction"], active["level"]
            failed = (d == UP and bars[i]["close"] <= level - RECLAIM_MIN_ATR * atr) or (d == DOWN and bars[i]["close"] >= level + RECLAIM_MIN_ATR * atr)
            if failed and i > active["break_candle_index"]:
                history.append({**active, "status": "FAILED_BREAK_RECLAIMED", "failure_candle_index": i})
                active = None
                continue
            if age >= FOLLOW_THROUGH_BARS and not active.get("accepted"):
                start = active["break_candle_index"] + 1
                closes_ok = all((bars[j]["close"] >= level + RECLAIM_MIN_ATR * atr) if d == UP else (bars[j]["close"] <= level - RECLAIM_MIN_ATR * atr) for j in range(start, i + 1))
                if closes_ok:
                    active["accepted"] = True
                    active["acceptance_candle_index"] = i
                    active["status"] = "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH"
        e = _current_break(bars, highs, lows, atr, _structure_at(highs, lows, i - 1), "EXTERNAL", i)
        if e["confirmed"] and active is None:
            active = {"event": e["event"], "direction": e["direction"], "level": e["level"], "swing_index": e["swing_index"], "break_candle_index": i, "status": "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH", "follow_through_bars": 0, "accepted": False}
    return history, active


def _break_event_lifecycle(history, last_index):
    if not history:
        return {"stage": "NONE", "current": False, "accepted": False, "terminal": False, "age_bars": None}
    x = history[-1]
    age = max(0, last_index - x.get("break_candle_index", last_index))
    if x.get("failure_candle_index") is not None:
        return {"stage": "HISTORICAL_FAILED_BREAK", "current": False, "accepted": False, "terminal": True, "age_bars": age, **x}
    if x.get("acceptance_candle_index") is not None or x.get("accepted"):
        return {"stage": "HISTORICAL_ACCEPTED_BREAK", "current": False, "accepted": True, "terminal": True, "age_bars": age, **x}
    return {"stage": "HISTORICAL_BREAK", "current": False, "accepted": False, "terminal": True, "age_bars": age, **x}


def _failure(bars, active, atr, current_index=None):
    if not active or active.get("status") != "FAILED_BREAK_RECLAIMED":
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False, "current": False}
    i = len(bars) - 1 if current_index is None else current_index
    d = active["direction"]
    current = active.get("failure_candle_index") == i
    return {"event": "FAILED_BOS" if current else "HISTORICAL_FAILED_BOS", "direction": DOWN if d == UP else UP, "confirmed": True, "current": current, "closed_candle_confirmed": True, "level": active["level"], "break_candle_index": active["break_candle_index"], "failure_candle_index": active.get("failure_candle_index"), "scope": "EXTERNAL"}


def _sweep_reclaim(bars, highs, lows, atr, structure):
    if not bars or atr <= 0:
        return {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE"}
    i = len(bars) - 1
    found = []
    candidates = [(_latest(highs, {"HH", "LH", "EQH"}, i - 1), DOWN, "high", "STRUCTURAL_SWING_HIGH"), (_latest(lows, {"HL", "LL", "EQL"}, i - 1), UP, "low", "STRUCTURAL_SWING_LOW")]
    for p, direction, side, liquidity_type in candidates:
        if not p:
            continue
        if side == "high":
            sweep = (bars[i]["high"] - p["price"]) / atr
            reclaim = (p["price"] - bars[i]["close"]) / atr
        else:
            sweep = (p["price"] - bars[i]["low"]) / atr
            reclaim = (bars[i]["close"] - p["price"]) / atr
        if sweep >= SWEEP_MIN_ATR and reclaim >= RECLAIM_MIN_ATR:
            found.append((reclaim, {"event": "SWEEP_RECLAIM", "direction": direction, "confirmed": True, "closed_candle_confirmed": True, "level": p["price"], "swing_index": p["index"], "sweep_candle_index": i, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4), "scope": "EXTERNAL", "liquidity_type": "EQUAL_HIGH" if p["label"] == "EQH" else "EQUAL_LOW" if p["label"] == "EQL" else liquidity_type, "lifecycle": "RECLAIM"}))
    return max(found, key=lambda x: x[0])[1] if found else {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE"}


def _sweep_history(bars, highs, lows, atr):
    events = []
    for i in range(1, len(bars)):
        candidates = [(_latest(highs, {"HH", "LH", "EQH"}, i - 1), DOWN, "high"), (_latest(lows, {"HL", "LL", "EQL"}, i - 1), UP, "low")]
        for p, direction, side in candidates:
            if not p:
                continue
            if side == "high":
                sweep = (bars[i]["high"] - p["price"]) / atr
                reclaim = (p["price"] - bars[i]["close"]) / atr
            else:
                sweep = (p["price"] - bars[i]["low"]) / atr
                reclaim = (bars[i]["close"] - p["price"]) / atr
            if sweep >= SWEEP_MIN_ATR:
                events.append({"event": "SWEEP_RECLAIM" if reclaim >= RECLAIM_MIN_ATR else "SWEEP", "direction": direction, "confirmed": True, "closed_candle_confirmed": True, "level": p["price"], "swing_index": p["index"], "sweep_candle_index": i, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(max(0.0, reclaim), 4), "lifecycle": "RECLAIM" if reclaim >= RECLAIM_MIN_ATR else "SWEEP"})
    return events


def _sweep_failure(bars, highs, lows, atr, prior_structure=NEUTRAL):
    if not bars or atr <= 0:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    i = len(bars) - 1
    if prior_structure == UP:
        p = _latest(highs, {"HH"}, i - 1)
        if p and bars[i - 1]["close"] > p["price"] and bars[i]["close"] <= p["price"] - RECLAIM_MIN_ATR * atr:
            return {"event": "FAILED_BOS", "direction": DOWN, "confirmed": True, "closed_candle_confirmed": True, "level": p["price"], "break_candle_index": i - 1, "failure_candle_index": i}
    if prior_structure == DOWN:
        p = _latest(lows, {"LL"}, i - 1)
        if p and bars[i - 1]["close"] < p["price"] and bars[i]["close"] >= p["price"] + RECLAIM_MIN_ATR * atr:
            return {"event": "FAILED_BOS", "direction": UP, "confirmed": True, "closed_candle_confirmed": True, "level": p["price"], "break_candle_index": i - 1, "failure_candle_index": i}
    return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _lifecycle(current, failure, history, active, last_index):
    if failure.get("confirmed") and failure.get("current"):
        return {"stage": "FAILED_BREAK_RECLAIM", "current": True, "active": False, "accepted": False, "follow_through": False, "failure": True, "terminal": True, "age_bars": 0, "follow_through_bars": 0, "level": failure["level"], "break_candle_index": failure["break_candle_index"], "failure_candle_index": failure.get("failure_candle_index")}
    if current.get("confirmed"):
        return {"stage": "CONFIRMED", "current": True, "active": True, "accepted": False, "follow_through": False, "failure": False, "terminal": False, "age_bars": 0, "follow_through_bars": 0, "level": current["level"], "break_candle_index": current["break_candle_index"], "event": current["event"]}
    if active:
        age = last_index - active["break_candle_index"]
        accepted = bool(active.get("accepted"))
        return {"stage": "ACCEPTED" if accepted else "CONFIRMED", "current": True, "active": True, "accepted": accepted, "follow_through": accepted, "failure": False, "terminal": False, "age_bars": age, "follow_through_bars": active.get("follow_through_bars", 0), "level": active["level"], "break_candle_index": active["break_candle_index"], "acceptance_candle_index": active.get("acceptance_candle_index"), "event": active.get("event")}
    if history:
        x = history[-1]
        failed = x.get("status") == "FAILED_BREAK_RECLAIMED"
        accepted = x.get("status") == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH"
        return {"stage": "FAILED" if failed else "ACCEPTED" if accepted else "HISTORICAL", "current": False, "active": False, "accepted": accepted, "follow_through": accepted, "failure": failed, "terminal": True, "age_bars": last_index - x["break_candle_index"], "follow_through_bars": x.get("follow_through_bars", 0), "level": x["level"], "break_candle_index": x["break_candle_index"], "failure_candle_index": x.get("failure_candle_index"), "acceptance_candle_index": x.get("acceptance_candle_index"), "event": x.get("event")}
    return {"stage": "NONE", "current": False, "active": False, "accepted": False, "follow_through": False, "failure": False, "terminal": False, "age_bars": None, "follow_through_bars": 0, "level": None, "break_candle_index": None}


def _invalidation(bars, structure, protected):
    level = protected.get("invalidation_level")
    base = {"direction": structure, "level": level, "type": protected.get("invalidation_type"), "confirmed": False, "closed_candle_confirmed": False, "source_label": protected.get("primary_label"), "source_index": protected.get("anchor_index"), "invalidates_current_external_thesis": False, "does_not_confirm_reversal": True}
    if not bars or structure not in {UP, DOWN} or level is None or protected.get("anchor_status") != "ACTIVE":
        return base
    atr = max(_atr(bars), 1e-12)
    broken = (structure == UP and bars[-1]["close"] <= level - RECLAIM_MIN_ATR * atr) or (structure == DOWN and bars[-1]["close"] >= level + RECLAIM_MIN_ATR * atr)
    base.update({"confirmed": broken, "closed_candle_confirmed": True, "invalidates_current_external_thesis": broken})
    return base


def _structure_authority(external, internal, protected, current_event, invalidation):
    ext = external.get("state", NEUTRAL)
    inte = internal.get("state", NEUTRAL)
    if invalidation.get("confirmed"):
        return {"authority": "NONE", "direction": NEUTRAL, "internal_role": "CONTEXT_ONLY", "count_role": "DESCRIPTIVE_ONLY", "reason": "PROTECTED_STRUCTURE_INVALIDATED", "score": 0.0, "internal_state": inte, "authority_is_actionable": False}
    if ext in {UP, DOWN}:
        score = 0.55 + (0.25 if protected.get("anchor_status") == "ACTIVE" else 0.0) + (0.15 if current_event.get("confirmed") else 0.0)
        return {"authority": "EXTERNAL", "direction": ext, "internal_role": "CONTEXT_ONLY", "count_role": "DESCRIPTIVE_ONLY", "reason": "EXTERNAL_ORDERED_STRUCTURE_HAS_PRIMARY_AUTHORITY", "score": round(min(1.0, score), 4), "internal_state": inte, "authority_is_actionable": True}
    return {"authority": "NONE", "direction": NEUTRAL, "internal_role": "CONTEXT_ONLY", "count_role": "DESCRIPTIVE_ONLY", "reason": "NO_DIRECTIONAL_EXTERNAL_STRUCTURE", "score": 0.0, "internal_state": inte, "authority_is_actionable": False}


def _authority(ext, inte, ec, ic, bos, failure, protected, sweep, invalidation, slope=NEUTRAL, slope_quality=0.0):
    return _structure_authority({"state": ext}, {"state": inte}, protected, bos, invalidation) | {"external_count_state": ec, "internal_count_state": ic}


def _state(ext, inte, bos, failure, sweep, invalidation, life):
    if invalidation.get("confirmed"):
        return "STRUCTURE_INVALIDATED"
    if failure.get("confirmed") and failure.get("current"):
        return "STRUCTURE_FAILURE"
    if bos.get("confirmed"):
        return "CHANGE_OF_CHARACTER" if bos["event"] == "CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"
    if ext in {UP, DOWN} and inte == ext:
        return "CONTINUATION"
    if ext in {UP, DOWN} and inte in {UP, DOWN} and ext != inte:
        return "STRUCTURE_CONFLICT"
    if ext == MIXED or inte == MIXED:
        return "TRANSITION"
    if sweep.get("confirmed"):
        return "LIQUIDITY_RECLAIM_CONTEXT"
    return "RANGE_STRUCTURE"


def _empty(status, reasons):
    p = _protected_structure(NEUTRAL, [], [])
    return {"architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION, "analysis_status": status, "finding": "INSUFFICIENT_DATA", "direction": NEUTRAL, "structural_bias": NEUTRAL, "structure_state": "RANGE_STRUCTURE", "internal_structure": {"state": NEUTRAL, "count_state": NEUTRAL}, "external_structure": {"state": NEUTRAL, "count_state": NEUTRAL}, "internal_count_state": NEUTRAL, "external_count_state": NEUTRAL, "swing_map": {"internal_highs": [], "internal_lows": [], "external_highs": [], "external_lows": []}, "bos": {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False}, "failure": {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}, "sweep_reclaim": {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE"}, "break_lifecycle": {"stage": "NONE"}, "protected_structure": p, "structural_invalidation": {"confirmed": False, "level": None, "type": "NO_DIRECTIONAL_INVALIDATION_LEVEL"}, "protected_level_break": {"confirmed": False}, "structure_authority": 0.0, "authority_detail": {"authority": "NONE", "score": 0.0, "reason": "INSUFFICIENT_DATA"}, "structure_strength": 0.0, "confidence": 0.0, "evidence": [], "conflicts": reasons, "reason_codes": reasons, "observations": reasons, "reasoning_trace": {"external_is_authority": False, "closed_candle_only": True, "upstream_inputs_used": False, "internal_bos_has_market_authority": False, "count_is_authority": False, "slope_is_structural_authority": False, "current_state": "INCOMPLETE", "historical_context": "NONE", "invalidation_rule": "CLOSED_CANDLE_ONLY", "structure_narrative": "Insufficient confirmed structure."}, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None, "specialists_active": False, "specialists_status": "PAUSED", "sub_engines_active": False, "sub_engines_status": "PAUSED", "specialists": {}}


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
    int_sem = _semantic_structure_state(ihl, ill)
    ext_sem = _semantic_structure_state(ehl, ell)
    inte, ext = int_sem["state"], ext_sem["state"]
    ic, ec = _count(ihl, ill), _count(ehl, ell)
    ics, ecs = _counts(ihl, ill), _counts(ehl, ell)
    protected = _protected_structure(ext, ehl, ell)
    eb = _current_break(b, ehl, ell, atr, ext, "EXTERNAL")
    ib = _current_break(b, ihl, ill, atr, inte, "INTERNAL")
    history, active = _break_history(b, ehl, ell, atr, ext)
    failure = _failure(b, history[-1], atr) if history and history[-1].get("status") == "FAILED_BREAK_RECLAIMED" else {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False, "current": False}
    sweep = _sweep_reclaim(b, ehl, ell, atr, ext)
    sweep_history = _sweep_history(b, ehl, ell, atr)
    if not sweep["confirmed"] and sweep_history:
        last_sweep = sweep_history[-1]
        if last_sweep["sweep_candle_index"] < len(b) - 1:
            sweep = {**last_sweep, "lifecycle": "HISTORICAL", "current": False}
    invalidation = _invalidation(b, ext, protected)
    life = _lifecycle(eb, failure, history, active, len(b) - 1)
    auth = _structure_authority(ext_sem, int_sem, protected, eb, invalidation)
    state = _state(ext, inte, eb, failure, sweep, invalidation, life)

    reasons = []
    if ext != ec:
        reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE_DESCRIPTIVE_ONLY")
    if inte != ic:
        reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE_DESCRIPTIVE_ONLY")
    if ib["confirmed"] and not eb["confirmed"]:
        reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if eb["confirmed"]:
        reasons.append("CURRENT_CLOSED_CANDLE_BREAK_CONFIRMED")
    if eb.get("event") == "CONFIRMED_CHOCH":
        reasons.append("CURRENT_CHOCH_CONFIRMED_BY_CLOSED_CANDLE")
    if life["stage"] == "CONFIRMED":
        reasons.append("BREAK_FOLLOW_THROUGH_PENDING")
    if life["stage"] == "ACCEPTED":
        reasons.append("BREAK_ACCEPTED_AFTER_FOLLOW_THROUGH")
    if failure.get("confirmed"):
        reasons.append("CURRENT_STRUCTURAL_BREAK_FAILED_AND_RECLAIMED" if failure.get("current") else "HISTORICAL_STRUCTURAL_BREAK_FAILED_AND_RECLAIMED")
    if sweep.get("confirmed"):
        reasons.append("CURRENT_SWEEP_RECLAIM_CONFIRMED" if sweep.get("current", True) else "HISTORICAL_SWEEP_RECLAIM")
    if invalidation.get("confirmed"):
        reasons.append("PROTECTED_STRUCTURE_INVALIDATED")
    if protected.get("anchor_quality") == "MISSING" and ext in {UP, DOWN}:
        reasons.append("PROTECTED_ANCHOR_MISSING_NO_FALLBACK_AUTHORIZED")
    if ext == MIXED:
        reasons.append("EXTERNAL_STRUCTURE_HAS_NO_DIRECTIONAL_AUTHORITY")
    if inte == MIXED:
        reasons.append("INTERNAL_STRUCTURE_IS_MIXED")
    reasons = list(dict.fromkeys(reasons + data[:8]))

    conflicts = []
    if ext != ec:
        conflicts.append("EXTERNAL_COUNT_STATE_IS_NOT_AUTHORITY")
    if inte != ic:
        conflicts.append("INTERNAL_COUNT_STATE_IS_NOT_AUTHORITY")
    if ext in {UP, DOWN} and inte in {UP, DOWN} and ext != inte:
        conflicts.append("INTERNAL_VS_EXTERNAL_STRUCTURE")
    if ib["confirmed"] and not eb["confirmed"]:
        conflicts.append("INTERNAL_BREAK_VS_EXTERNAL_AUTHORITY")
    if failure.get("confirmed") and not failure.get("current"):
        conflicts.append("HISTORICAL_FAILURE_CANNOT_OVERRIDE_CURRENT_STRUCTURE")
    if failure.get("current"):
        conflicts.append("BREAK_FAILED_RECLAIMED")
    if invalidation.get("confirmed"):
        conflicts.append("PROTECTED_STRUCTURE_INVALIDATED")
    if life.get("stage") in {"HISTORICAL", "FAILED", "ACCEPTED"}:
        conflicts.append("HISTORICAL_EVENT_NOT_CURRENT_EVENT")
    if ext == MIXED or inte == MIXED:
        conflicts.append("STRUCTURAL_SEMANTICS_NOT_DIRECTIONALLY_ALIGNED")

    if invalidation.get("confirmed"):
        finding = "STRUCTURE_INVALIDATED"
    elif failure.get("current"):
        finding = f"STRUCTURE_FAILURE={failure['direction']}"
    elif eb["confirmed"]:
        finding = eb["event"]
    elif ext in {UP, DOWN} and inte in {UP, DOWN} and ext != inte:
        finding = f"{ext}_STRUCTURE_WITH_INTERNAL_CONFLICT"
    elif ext in {UP, DOWN}:
        finding = f"{ext}_STRUCTURE"
    elif ext == MIXED or inte == MIXED:
        finding = "MIXED_STRUCTURE"
    else:
        finding = "RANGE_STRUCTURE"

    if invalidation.get("confirmed") or failure.get("current"):
        direction = failure["direction"] if failure.get("current") else NEUTRAL
    elif eb.get("confirmed"):
        direction = eb["direction"]
    else:
        direction = ext if ext in {UP, DOWN} else NEUTRAL

    confidence = min(1.0, 0.30 + 0.65 * auth["score"] + (0.08 if eb["confirmed"] else 0.0))
    if ext == MIXED or ext == NEUTRAL:
        confidence = min(confidence, 0.55)
    if failure.get("current") or invalidation.get("confirmed"):
        confidence = min(confidence, 0.60)

    evidence = [
        f"external_structure={ext}", f"internal_structure={inte}",
        f"external_count_state={ec}", f"internal_count_state={ic}",
        f"external_bos={eb['event']}", f"internal_bos={ib['event']}",
        f"sweep_reclaim={sweep['event']}", f"break_lifecycle={life['stage']}",
        f"protected_primary_level={protected['primary_level']}",
        f"protected_anchor_quality={protected.get('anchor_quality')}",
        f"structure_authority={auth['score']}",
        "count_state_role=DESCRIPTIVE_NOT_AUTHORITY",
        "historical_events_do_not_override_current_state",
        "semantic_basis=ORDERED_ALTERNATING_SWING_RELATIONSHIPS",
    ]
    narrative = (
        f"External={ext}; Internal={inte}; current_event={eb['event']}; "
        f"lifecycle={life['stage']}; protected={protected.get('anchor_quality')}; "
        f"authority={auth['authority']}; invalidation={'CONFIRMED' if invalidation.get('confirmed') else 'NOT_CONFIRMED'}. "
        "Counts are descriptive only. Internal structure is context, not market authority. "
        "Historical breaks and sweeps cannot overwrite the current structural thesis."
    )
    trace = {
        "external_state": ext, "internal_state": inte,
        "external_semantics": ext_sem, "internal_semantics": int_sem,
        "external_count_state": ec, "internal_count_state": ic,
        "external_bos_confirmed": eb["confirmed"], "internal_bos_confirmed": ib["confirmed"],
        "internal_bos_has_market_authority": False,
        "external_is_authority": auth["authority"] == "EXTERNAL",
        "closed_candle_only": True,
        "protected_structure_is_invalidation_anchor": protected.get("anchor_is_ideal", False),
        "protected_level_break_invalidates_current_external_thesis": invalidation["confirmed"],
        "break_lifecycle_stage": life["stage"],
        "authority_explanation": auth["reason"], "authority_basis": auth["authority"],
        "authority_direction": auth["direction"],
        "upstream_inputs_used": False, "upstream_direction_used": False,
        "upstream_decisions_used": False, "upstream_gates_used": False,
        "count_is_authority": False, "slope_is_structural_authority": False,
        "current_state": state, "historical_context": life.get("stage"),
        "invalidation_rule": protected.get("invalidation_type"),
        "structure_narrative": narrative,
    }
    return {
        "architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
        "analysis_status": "COMPLETE", "finding": finding, "direction": direction,
        "structural_bias": ext if ext in {UP, DOWN} else NEUTRAL, "structure_state": state,
        "internal_structure": {"state": inte, "count_state": ic, "counts": ics, "semantic": int_sem},
        "external_structure": {"state": ext, "count_state": ec, "counts": ecs, "semantic": ext_sem},
        "internal_count_state": ic, "external_count_state": ec, "internal_counts": ics, "external_counts": ecs,
        "internal_sequence": "→".join(x["label"] for x in sorted(ihl + ill, key=lambda x: x["index"])[-12:]),
        "external_sequence": "→".join(x["label"] for x in sorted(ehl + ell, key=lambda x: x["index"])[-12:]),
        "swing_map": {"internal_highs": ihl, "internal_lows": ill, "external_highs": ehl, "external_lows": ell},
        "atr14": round(atr, 8), "closed_candles": len(b),
        "bos": eb, "external_bos": eb["event"], "internal_bos": ib["event"],
        "external_bos_detail": eb, "internal_bos_detail": ib,
        "failure": failure, "structural_failure": failure,
        "sweep_reclaim": sweep, "sweep_history": sweep_history[-5:],
        "break_lifecycle": life, "break_history": history[-5:],
        "protected_structure": protected,
        "protected_high": protected["protected_high"]["price"] if protected.get("protected_high") else None,
        "protected_low": protected["protected_low"]["price"] if protected.get("protected_low") else None,
        "structural_invalidation": invalidation, "protected_level_break": invalidation,
        "BOS_type": eb["event"], "BOS_level": eb.get("level"), "BOS_candle_index": eb.get("break_candle_index"),
        "structure_strength": auth["score"], "structure_authority": auth["score"], "authority_detail": auth,
        "confidence": round(confidence, 4), "evidence": evidence, "conflicts": conflicts,
        "reason_codes": reasons, "observations": [f"closed_candles={len(b)}", f"atr14={round(atr, 8)}"] + evidence,
        "reasoning_trace": trace,
        "upstream_inputs_used": False, "upstream_direction_used": False, "upstream_decisions_used": False,
        "upstream_gates_used": False, "score_used": False, "trade_decision_authority": False,
        "decision_authority": "E9_ONLY", "decision": None, "gate": None,
        "specialists_active": False, "specialists_status": "PAUSED", "sub_engines_active": False,
        "sub_engines_status": "PAUSED", "specialists": {},
    }


__all__ = [
    "analyze_e3", "_compress", "_bos", "_sweep_failure", "_current_break", "_break_history",
    "_failure", "_sweep_reclaim", "_state", "_resolve_external_state", "_protected_structure",
    "_authority", "_lifecycle", "_invalidation", "_semantic_structure_state", "_break_event_lifecycle",
    "_structure_authority", "_resolve_structure",
]
