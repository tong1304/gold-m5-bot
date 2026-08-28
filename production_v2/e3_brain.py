from __future__ import annotations

"""E3 — Professional Market Structure Brain.

E3 answers one question only: "What is price structure communicating?"
It is deliberately independent from E1/E2 and has no trade/risk authority.
All live structural decisions are based on CLOSED candles only.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V8"
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
FOLLOW_THROUGH_BARS = 2


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
    """Return confirmed pivots only; a pivot is usable after radius future bars close."""
    out = []
    if len(b) <= radius * 2:
        return out
    for i in range(radius, len(b) - radius):
        x = b[i][side]
        left = [b[j][side] for j in range(i - radius, i)]
        right = [b[j][side] for j in range(i + 1, i + radius + 1)]
        prominence = PROMINENCE_ATR * max(_atr_at(b, i), 1e-12)
        if side == "high" and x >= max(left) and x > max(right):
            if min(x - max(left), x - max(right)) >= prominence:
                out.append((i, x, i + radius))
        elif side == "low" and x <= min(left) and x < min(right):
            if min(min(left) - x, min(right) - x) >= prominence:
                out.append((i, x, i + radius))
    return out


def _compress(points, atr, side, spacing=2):
    out = []
    tol = max(float(atr) * EQ_TOLERANCE_ATR, 1e-12)
    for p in points or []:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        old = out[-1]
        if abs(p[1] - old[1]) <= tol:
            if (side == "high" and p[1] >= old[1]) or (side == "low" and p[1] <= old[1]):
                out[-1] = p
        elif (side == "high" and p[1] > old[1]) or (side == "low" and p[1] < old[1]):
            out[-1] = p
    return out


def _label(hp, lp, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    highs, prev = [], None
    for i, p, confirm in hp:
        d = 0.0 if prev is None else p - prev[1]
        label = "SWING_HIGH" if prev is None else "EQH" if abs(d) <= tol else "HH" if d > 0 else "LH"
        highs.append({"index": int(i), "price": round(float(p), 8), "label": label, "confirmation_index": int(confirm)})
        prev = (i, p)
    lows, prev = [], None
    for i, p, confirm in lp:
        d = 0.0 if prev is None else p - prev[1]
        label = "SWING_LOW" if prev is None else "EQL" if abs(d) <= tol else "HL" if d > 0 else "LL"
        lows.append({"index": int(i), "price": round(float(p), 8), "label": label, "confirmation_index": int(confirm)})
        prev = (i, p)
    return highs, lows


def _latest(xs, labels, max_confirm=None):
    for x in reversed(xs):
        if x["label"] in labels and (max_confirm is None or x["confirmation_index"] <= max_confirm):
            return x
    return None


def _count_state(highs, lows, n=8):
    items = highs[-n:] + lows[-n:]
    bull = sum(x["label"] in {"HH", "HL"} for x in items)
    bear = sum(x["label"] in {"LH", "LL"} for x in items)
    if bull == bear == 0:
        return NEUTRAL
    if bull >= bear + 2:
        return UP
    if bear >= bull + 2:
        return DOWN
    return MIXED


def _counts(highs, lows, n=8):
    c = {k: 0 for k in ("HH", "HL", "LH", "LL", "EQH", "EQL")}
    for x in highs[-n:] + lows[-n:]:
        if x["label"] in c:
            c[x["label"]] += 1
    return c


def _classify(highs, lows):
    if len(highs) < 2 or len(lows) < 2:
        return NEUTRAL
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    if h2["price"] > h1["price"] and l2["price"] > l1["price"]:
        return UP
    if h2["price"] < h1["price"] and l2["price"] < l1["price"]:
        return DOWN
    return MIXED


def _protected(structure, highs, lows):
    if structure == UP:
        low = _latest(lows, {"HL"})
        high = _latest(highs, {"HH", "EQH"})
    elif structure == DOWN:
        low = _latest(lows, {"LL", "EQL"})
        high = _latest(highs, {"LH", "EQH"})
    else:
        low = _latest(lows, {"HL", "LL", "EQL"})
        high = _latest(highs, {"HH", "LH", "EQH"})
    return {"protected_low": low, "protected_high": high}


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
    return {"confirmed": bool(close_beyond and (displacement_ok or location_ok)),
            "distance_atr": round(max(0.0, distance), 4), "body_atr": round(body_atr, 4),
            "close_location": round(loc, 4), "displacement_ok": displacement_ok,
            "close_beyond_level": close_beyond}


def _make_event(bar, point, direction, atr, event, scope, idx):
    q = _quality(bar, point["price"] if point else None, direction, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return {"event": event, "direction": direction, "confirmed": True, "scope": scope,
            "level": point["price"], "swing_index": point["index"], "swing_label": point["label"],
            "break_candle_index": idx, "break_distance_atr": q["distance_atr"],
            "break_body_atr": q["body_atr"], "close_location": q["close_location"],
            "displacement_ok": q["displacement_ok"], "close_beyond_level": q["close_beyond_level"]}


def _current_break(bars, highs, lows, atr, structure, scope="EXTERNAL", idx=None):
    idx = len(bars) - 1 if idx is None else idx
    if idx < 0 or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    high = _latest(highs, {"HH", "LH", "EQH"}, idx)
    low = _latest(lows, {"HL", "LL", "EQL"}, idx)
    candidates = []
    if high and high["index"] < idx:
        q = _quality(bars[idx], high["price"], UP, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if structure == DOWN else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _make_event(bars[idx], high, UP, atr, event, scope, idx)))
    if low and low["index"] < idx:
        q = _quality(bars[idx], low["price"], DOWN, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if structure == UP else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _make_event(bars[idx], low, DOWN, atr, event, scope, idx)))
    return max(candidates, key=lambda x: x[0])[1] if candidates else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _break_history(bars, highs, lows, atr, structure):
    """Scan closed candles chronologically; pivots become usable only at confirmation_index."""
    events, active = [], None
    for idx in range(1, len(bars)):
        if active is not None:
            level, direction, break_idx = active["level"], active["direction"], active["break_candle_index"]
            if idx > break_idx:
                active["follow_through_bars"] += 1
            if (direction == UP and bars[idx]["close"] < level) or (direction == DOWN and bars[idx]["close"] > level):
                active["status"] = "FAILED_BREAK_RECLAIMED"
                active["failure_candle_index"] = idx
                events.append(active.copy())
                active = None
            elif active["follow_through_bars"] >= FOLLOW_THROUGH_BARS:
                active["status"] = "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH"
                events.append(active.copy())
                active = None
        if active is None:
            ext = _current_break(bars, highs, lows, atr, structure, "EXTERNAL", idx)
            if ext.get("confirmed"):
                active = {"event": ext["event"], "direction": ext["direction"], "level": ext["level"],
                          "swing_index": ext["swing_index"], "break_candle_index": idx,
                          "status": "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH", "follow_through_bars": 0}
    return events, active


def _failure_from_active(bars, active, atr):
    if not active:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    level, direction = active["level"], active["direction"]
    for idx in range(active["break_candle_index"] + 1, len(bars)):
        c = bars[idx]["close"]
        if (direction == UP and c < level) or (direction == DOWN and c > level):
            return {"event": "FAILED_BOS", "direction": DOWN if direction == UP else UP, "confirmed": True,
                    "level": level, "break_candle_index": active["break_candle_index"],
                    "failure_candle_index": idx, "scope": "EXTERNAL",
                    "reclaim_distance_atr": round(abs(c - level) / max(atr, 1e-12), 4)}
    return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _break_lifecycle(bars, current_break, failure, history, active):
    if failure.get("confirmed"):
        return {"stage": "FAILED_BREAK_RECLAIM", "active": False, "accepted": False, "follow_through": False,
                "failure": True, "level": failure.get("level"), "break_candle_index": failure.get("break_candle_index"),
                "failure_candle_index": failure.get("failure_candle_index"),
                "explanation": "A previously confirmed break was invalidated by a closed-candle reclaim through its break level."}
    if current_break.get("confirmed"):
        idx, level, direction = current_break["break_candle_index"], current_break["level"], current_break["direction"]
        after = bars[idx + 1: idx + 1 + FOLLOW_THROUGH_BARS]
        follow = len(after) >= FOLLOW_THROUGH_BARS and all(
            x["close"] > level if direction == UP else x["close"] < level for x in after)
        return {"stage": "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH" if follow else "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH",
                "active": True, "accepted": True, "follow_through": follow, "failure": False,
                "level": level, "break_candle_index": idx,
                "explanation": "The latest closed candle broke structure; follow-through is measured separately and never assumed."}
    if active and active.get("status") == "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH":
        return {"stage": active["status"], "active": True, "accepted": True, "follow_through": False,
                "failure": False, "level": active.get("level"), "break_candle_index": active.get("break_candle_index"),
                "explanation": "A closed-candle break exists but the required continuation sequence is not complete."}
    if history:
        last = history[-1]
        return {"stage": last["status"], "active": False, "accepted": True,
                "follow_through": last["status"] == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH", "failure": False,
                "level": last["level"], "break_candle_index": last["break_candle_index"],
                "explanation": "The latest completed structural break lifecycle is reported without treating it as a live entry signal."}
    return {"stage": "NO_CONFIRMED_BREAK", "active": False, "accepted": False, "follow_through": False,
            "failure": False, "level": None, "break_candle_index": None,
            "explanation": "No closed candle has proven acceptance beyond a confirmed structural level."}


def _invalidation(external, protected):
    ph, pl = protected.get("protected_high"), protected.get("protected_low")
    if external == UP and pl:
        return {"direction": UP, "level": pl["price"], "type": "CLOSED_CANDLE_ACCEPTANCE_BELOW_PROTECTED_LOW",
                "source_label": pl["label"], "source_index": pl["index"]}
    if external == DOWN and ph:
        return {"direction": DOWN, "level": ph["price"], "type": "CLOSED_CANDLE_ACCEPTANCE_ABOVE_PROTECTED_HIGH",
                "source_label": ph["label"], "source_index": ph["index"]}
    return {"direction": external, "level": None, "type": "NO_DIRECTIONAL_INVALIDATION_LEVEL",
            "source_label": None, "source_index": None}


def _slope(bars, n=20):
    if len(bars) < 5:
        return NEUTRAL, 0.0
    closes = [x["close"] for x in bars[-n:]]
    z = (closes[-1] - closes[0]) / (max(_atr(bars), 1e-12) * max(1, len(closes) - 1))
    return (UP if z > .035 else DOWN if z < -.035 else NEUTRAL), round(min(1.0, abs(z) * 8.0), 4)


def _authority(external, internal, ext_count, int_count, current_break, failure, protected, slope, slope_quality, lifecycle):
    score = 0.0; support = []; penalties = []
    if external in {UP, DOWN}: score += .35; support.append(f"EXTERNAL_{external}")
    else: penalties.append("EXTERNAL_STRUCTURE_UNRESOLVED")
    if internal == external and external in {UP, DOWN}: score += .20; support.append(f"INTERNAL_ALIGNS_{external}")
    elif internal in {UP, DOWN}: penalties.append("INTERNAL_COUNTER_STRUCTURE")
    if ext_count == external and external in {UP, DOWN}: score += .15; support.append("EXTERNAL_COUNT_CONFIRMS")
    elif external in {UP, DOWN}: penalties.append("EXTERNAL_COUNT_DIVERGES")
    if protected.get("protected_high") or protected.get("protected_low"): score += .10; support.append("PROTECTED_STRUCTURE_IDENTIFIED")
    else: penalties.append("PROTECTED_STRUCTURE_MISSING")
    if current_break.get("confirmed"): score += .15; support.append("CURRENT_CLOSED_CANDLE_BREAK")
    if lifecycle.get("follow_through"): score += .05; support.append("FOLLOW_THROUGH_CONFIRMED")
    if failure.get("confirmed"): score -= .30; penalties.append("BREAK_FAILED_RECLAIMED")
    if slope != external and external in {UP, DOWN}: score -= min(.10, .10 * slope_quality); penalties.append("SLOPE_CONFLICT")
    score = round(max(0.0, min(1.0, score)), 4)
    return {"score": score, "level": "HIGH" if score >= .80 else "MEDIUM" if score >= .55 else "LOW",
            "support": support, "penalties": penalties,
            "explanation": "support=" + ",".join(support) + "; penalties=" + ",".join(penalties)}


def _state(external, internal, current_break, failure, lifecycle):
    if failure.get("confirmed"): return "STRUCTURE_FAILURE"
    if current_break.get("confirmed"): return "CHANGE_OF_CHARACTER" if current_break.get("event") == "CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"
    if lifecycle.get("follow_through"): return "CONTINUATION"
    if external in {UP, DOWN} and internal == external: return "CONTINUATION"
    if external in {UP, DOWN} and internal == MIXED: return "INTERNAL_CONFLICT"
    if external == MIXED and internal in {UP, DOWN}: return "INTERNAL_COUNTER_MOVE"
    return "RANGE_OR_UNCLEAR"


def _empty(status, reasons):
    return {"architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
            "analysis_status": status, "finding": "INSUFFICIENT_DATA", "direction": NEUTRAL,
            "structure_state": "RANGE_OR_UNCLEAR", "internal_structure": {"state": NEUTRAL, "count_state": NEUTRAL},
            "external_structure": {"state": NEUTRAL, "count_state": NEUTRAL}, "internal_count_state": NEUTRAL,
            "external_count_state": NEUTRAL, "swing_map": {"internal_highs": [], "internal_lows": [], "external_highs": [], "external_lows": []},
            "bos": {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False}, "failure": {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False},
            "break_lifecycle": {"stage": "NO_CONFIRMED_BREAK", "active": False}, "protected_structure": {"protected_high": None, "protected_low": None},
            "structural_invalidation": _invalidation(NEUTRAL, {}), "structure_authority": 0.0,
            "authority_detail": {"score": 0.0, "level": "LOW", "support": [], "penalties": [], "explanation": ""},
            "structure_strength": 0.0, "confidence": 0.0, "evidence": [], "conflicts": reasons, "reason_codes": reasons,
            "observations": [f"closed_candles={status}"], "reasoning_trace": {"external_is_authority": True, "closed_candle_only": True},
            "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False,
            "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None,
            "specialists_active": False, "specialists_status": "PAUSED"}


def analyze_e3(bars):
    clean, data_reasons = _clean_bars(bars)
    if len(clean) < MIN_CANDLES:
        return _empty("INCOMPLETE", ["INSUFFICIENT_CANDLES"] + data_reasons[:8])
    atr = _atr(clean)
    ih = _compress(_pivot_points(clean, "high", INTERNAL_RADIUS), atr, "high")
    il = _compress(_pivot_points(clean, "low", INTERNAL_RADIUS), atr, "low")
    eh = _compress(_pivot_points(clean, "high", EXTERNAL_RADIUS), atr, "high")
    el = _compress(_pivot_points(clean, "low", EXTERNAL_RADIUS), atr, "low")
    ihl, ill = _label(ih, il, atr); ehl, ell = _label(eh, el, atr)
    internal, external = _classify(ihl, ill), _classify(ehl, ell)
    int_count, ext_count = _count_state(ihl, ill), _count_state(ehl, ell)
    int_counts, ext_counts = _counts(ihl, ill), _counts(ehl, ell)
    protected = _protected(external, ehl, ell)
    ext_bos = _current_break(clean, ehl, ell, atr, external, "EXTERNAL")
    int_bos = _current_break(clean, ihl, ill, atr, internal, "INTERNAL")
    history, active = _break_history(clean, ehl, ell, atr, external)
    failure = _failure_from_active(clean, active, atr)
    lifecycle = _break_lifecycle(clean, ext_bos, failure, history, active)
    slope, slope_quality = _slope(clean)
    state = _state(external, internal, ext_bos, failure, lifecycle)
    invalidation = _invalidation(external, protected)
    authority_detail = _authority(external, internal, ext_count, int_count, ext_bos, failure, protected, slope, slope_quality, lifecycle)
    authority = authority_detail["score"]

    reasons = []
    if external != ext_count: reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if internal != int_count: reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if external == MIXED: reasons.append("STRUCTURE_UNRESOLVED")
    if slope != external and external in {UP, DOWN}: reasons.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"): reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if not ext_bos.get("confirmed"): reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if lifecycle["stage"] == "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH": reasons.append("BREAK_FOLLOW_THROUGH_PENDING")
    if lifecycle["stage"] == "ACCEPTED_BREAK_WITH_FOLLOW_THROUGH": reasons.append("BREAK_FOLLOW_THROUGH_CONFIRMED")
    if failure.get("confirmed"): reasons.append("STRUCTURAL_BREAK_FAILED_AND_RECLAIMED")
    reasons = list(dict.fromkeys(reasons + data_reasons[:8]))

    direction = external if external in {UP, DOWN} else (ext_bos.get("direction") if ext_bos.get("confirmed") else NEUTRAL)
    if failure.get("confirmed"): finding = "STRUCTURE_FAILURE=" + failure["direction"]
    elif ext_bos.get("confirmed"): finding = ext_bos["event"]
    elif external == UP and internal == UP: finding = "BULLISH_STRUCTURE"
    elif external == DOWN and internal == DOWN: finding = "BEARISH_STRUCTURE"
    else: finding = "MIXED_STRUCTURE"
    confidence = min(1.0, 0.45 + 0.45 * authority + (0.10 if ext_bos.get("confirmed") else 0.0))
    if external == MIXED: confidence = min(confidence, .55)
    if failure.get("confirmed"): confidence = min(confidence, .60)
    if lifecycle["stage"] == "BREAK_CONFIRMED_AWAITING_FOLLOW_THROUGH": confidence = min(confidence, .72)

    conflicts = []
    if external != ext_count: conflicts.append("EXTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE")
    if internal != int_count: conflicts.append("INTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE")
    if slope != external and external in {UP, DOWN}: conflicts.append("SLOPE_VS_EXTERNAL_STRUCTURE")
    if external in {UP, DOWN} and internal in {UP, DOWN} and internal != external: conflicts.append("INTERNAL_VS_EXTERNAL_STRUCTURE")
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"): conflicts.append("INTERNAL_BREAK_VS_EXTERNAL_AUTHORITY")
    if failure.get("confirmed"): conflicts.append("BREAK_FAILED_RECLAIMED")

    evidence = [f"external_structure={external}", f"internal_structure={internal}", f"external_count_state={ext_count}",
                f"internal_count_state={int_count}", f"external_bos={ext_bos.get('event')}", f"internal_bos={int_bos.get('event')}",
                f"break_lifecycle={lifecycle['stage']}", f"protected_high={protected.get('protected_high', {}).get('price') if protected.get('protected_high') else None}",
                f"protected_low={protected.get('protected_low', {}).get('price') if protected.get('protected_low') else None}",
                f"invalidation={invalidation.get('type')}@{invalidation.get('level')}", f"slope_context={slope}",
                f"slope_quality={slope_quality}", f"structure_authority={authority}"]
    reasoning_trace = {"external_state": external, "internal_state": internal, "external_count_state": ext_count,
                       "internal_count_state": int_count, "slope_context": slope, "slope_is_structural_authority": False,
                       "external_bos_confirmed": bool(ext_bos.get("confirmed")), "internal_bos_confirmed": bool(int_bos.get("confirmed")),
                       "external_is_authority": True, "closed_candle_only": True, "protected_structure_is_invalidation_anchor": True,
                       "break_lifecycle_stage": lifecycle["stage"], "authority_explanation": authority_detail["explanation"],
                       "upstream_inputs_used": False}

    return {"architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
            "analysis_status": "COMPLETE", "finding": finding, "direction": direction, "structure_state": state,
            "internal_structure": {"state": internal, "count_state": int_count, "counts": int_counts},
            "external_structure": {"state": external, "count_state": ext_count, "counts": ext_counts},
            "internal_count_state": int_count, "external_count_state": ext_count, "internal_counts": int_counts,
            "external_counts": ext_counts, "internal_sequence": "→".join(x["label"] for x in sorted(ihl + ill, key=lambda x:x["index"])[-12:]),
            "external_sequence": "→".join(x["label"] for x in sorted(ehl + ell, key=lambda x:x["index"])[-12:]),
            "swing_map": {"internal_highs": ihl, "internal_lows": ill, "external_highs": ehl, "external_lows": ell},
            "atr14": round(atr, 8), "closed_candles": len(clean), "bos": ext_bos, "external_bos": ext_bos.get("event", "NO_BOS"),
            "internal_bos": int_bos.get("event", "NO_BOS"), "external_bos_detail": ext_bos, "internal_bos_detail": int_bos,
            "failure": failure, "break_lifecycle": lifecycle, "break_history": history[-5:], "protected_structure": protected,
            "protected_high": protected.get("protected_high", {}).get("price") if protected.get("protected_high") else None,
            "protected_low": protected.get("protected_low", {}).get("price") if protected.get("protected_low") else None,
            "structural_invalidation": invalidation, "structure_strength": round(authority, 4), "structure_authority": round(authority, 4),
            "authority_detail": authority_detail, "confidence": round(confidence, 4), "evidence": evidence, "conflicts": conflicts,
            "reason_codes": reasons, "observations": [f"closed_candles={len(clean)}", f"atr14={round(atr, 8)}"] + evidence,
            "reasoning_trace": reasoning_trace, "slope_context": slope, "slope_quality": slope_quality,
            "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False,
            "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None,
            "specialists_active": False, "specialists_status": "PAUSED", "specialists": {}}


__all__ = ["analyze_e3", "_compress", "_current_break", "_break_history", "_failure_from_active"]
