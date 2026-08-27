from __future__ import annotations

"""E3 — Professional Market Structure Brain.

Structure analysis only. E3 never consumes E1/E2 decisions, gates or scores and
never authorizes a trade; E9 remains the sole trade-decision authority.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
# Keep the public contract identifier stable while the implementation is rebuilt.
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V3"
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
        if side == "high" and x >= max(left) and x > max(right) and min(x - max(left), x - max(right)) >= prominence:
            out.append((i, x))
        elif side == "low" and x <= min(left) and x < min(right) and min(min(left) - x, min(right) - x) >= prominence:
            out.append((i, x))
    return out


def _compress(points, atr, side=None, spacing=2):
    """Compress clustered pivots; keep the most extreme member of a cluster."""
    points = list(points or [])
    if side is None:
        # Compatibility with the older helper API used by the regression suite.
        # Callers inside E3 always provide the side explicitly.
        if len(points) < 2:
            side = "high"
        else:
            side = "high" if points[-1][1] >= points[0][1] else "low"
    out = []
    tol = max(float(atr) * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        old = out[-1]
        if abs(p[1] - old[1]) <= tol:
            if side == "high" and p[1] > old[1]:
                out[-1] = p
            elif side == "low" and p[1] < old[1]:
                out[-1] = p
        elif side == "high" and p[1] > old[1]:
            out[-1] = p
        elif side == "low" and p[1] < old[1]:
            out[-1] = p
    return out


def _label(hp, lp, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    highs, prev = [], None
    for i, p in hp:
        if prev is None:
            label = "SWING_HIGH"
        else:
            d = p - prev[1]
            label = "EQH" if abs(d) <= tol else ("HH" if d > 0 else "LH")
        highs.append({"index": int(i), "price": round(float(p), 8), "label": label})
        prev = (i, p)
    lows, prev = [], None
    for i, p in lp:
        if prev is None:
            label = "SWING_LOW"
        else:
            d = p - prev[1]
            label = "EQL" if abs(d) <= tol else ("HL" if d > 0 else "LL")
        lows.append({"index": int(i), "price": round(float(p), 8), "label": label})
        prev = (i, p)
    return highs, lows


def _latest(xs, labels):
    return next((x for x in reversed(xs) if x["label"] in labels), None)


def _recent(xs, labels, n=2):
    return [x for x in reversed(xs) if x["label"] in labels][:n]


def _classify(highs, lows):
    """Classify from confirmed swing evidence, not from slope."""
    hh, lh = _recent(highs, {"HH"}, 2), _recent(highs, {"LH"}, 2)
    hl, ll = _recent(lows, {"HL"}, 2), _recent(lows, {"LL"}, 2)
    if hh and hl and not (lh and ll):
        return UP
    if lh and ll and not (hh and hl):
        return DOWN
    bull = 2 * bool(hh) + 2 * bool(hl)
    bear = 2 * bool(lh) + 2 * bool(ll)
    if bull >= bear + 2:
        return UP
    if bear >= bull + 2:
        return DOWN
    return MIXED if (bull or bear) else NEUTRAL


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
    return {
        "confirmed": bool(close_beyond and (displacement_ok or location_ok)),
        "distance_atr": round(max(0.0, distance), 4),
        "body_atr": round(body_atr, 4),
        "close_location": round(loc, 4),
        "displacement_ok": displacement_ok,
        "close_beyond_level": close_beyond,
    }


def _event(bar, point, direction, atr, event, scope="EXTERNAL", idx=0):
    q = _quality(bar, point["price"] if point else None, direction, atr)
    if not q["confirmed"]:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return {
        "event": event,
        "direction": direction,
        "confirmed": True,
        "scope": scope,
        "level": point["price"],
        "swing_index": point["index"],
        "swing_label": point["label"],
        "break_candle_index": idx,
        "break_distance_atr": q["distance_atr"],
        "break_body_atr": q["body_atr"],
        "close_location": q["close_location"],
        "displacement_ok": q["displacement_ok"],
        "close_beyond_level": q["close_beyond_level"],
    }


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    """Detect bullish and bearish BOS/CHOCH from confirmed structural levels."""
    if not bars or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    last = bars[-1]
    candidates = []
    high = _latest(highs, {"HH", "LH", "EQH"})
    low = _latest(lows, {"HL", "LL", "EQL"})
    if high:
        q = _quality(last, high["price"], UP, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if prior_structure == DOWN else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _event(last, high, UP, atr, event, scope, len(bars) - 1)))
    if low:
        q = _quality(last, low["price"], DOWN, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if prior_structure == UP else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _event(last, low, DOWN, atr, event, scope, len(bars) - 1)))
    if not candidates:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return max(candidates, key=lambda x: x[0])[1]


def _sweep_failure(bars, highs, lows, atr=None, prior_structure="UP"):
    """Detect sweep + meaningful close back inside a protected level."""
    if not bars:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    atr = max(float(atr if atr is not None else _atr(bars)), 1e-12)
    b = bars[-1]
    p = _protected(prior_structure, highs, lows)
    candidates = []
    high = p.get("protected_high")
    if high:
        sweep = (b["high"] - high["price"]) / atr
        reclaim = (high["price"] - b["close"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append({"event": "FAILED_BREAK", "direction": DOWN, "confirmed": True, "level": high["price"], "swing_index": high["index"], "swing_label": high["label"], "failure_candle_index": len(bars) - 1, "scope": "EXTERNAL", "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4)})
    low = p.get("protected_low")
    if low:
        sweep = (low["price"] - b["low"]) / atr
        reclaim = (b["close"] - low["price"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append({"event": "FAILED_BREAK", "direction": UP, "confirmed": True, "level": low["price"], "swing_index": low["index"], "swing_label": low["label"], "failure_candle_index": len(bars) - 1, "scope": "EXTERNAL", "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4)})
    return max(candidates, key=lambda x: x["sweep_distance_atr"] + x["reclaim_distance_atr"]) if candidates else {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _failure(bars, highs, lows, structure, atr):
    return _sweep_failure(bars, highs, lows, atr, structure)


def _choch(bars, highs, lows, structure, atr):
    if structure not in {UP, DOWN} or not bars:
        return {"event": "NO_CHOCH", "direction": NEUTRAL, "confirmed": False}
    p = _protected(structure, highs, lows)
    point = p.get("protected_low") if structure == UP else p.get("protected_high")
    direction = DOWN if structure == UP else UP
    if not point:
        return {"event": "NO_CHOCH", "direction": NEUTRAL, "confirmed": False}
    return _event(bars[-1], point, direction, atr, "CONFIRMED_CHOCH", "EXTERNAL", len(bars) - 1)


def _slope(bars, n=20):
    if len(bars) < 5:
        return NEUTRAL, 0.0
    closes = [x["close"] for x in bars[-n:]]
    z = (closes[-1] - closes[0]) / (max(_atr(bars), 1e-12) * max(1, len(closes) - 1))
    return (UP if z > 0.035 else DOWN if z < -0.035 else NEUTRAL), round(min(1.0, abs(z) * 8.0), 4)


def analyze_e3(bars):
    clean, data_errors = _clean_bars(bars)
    base = {
        "architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
        "decision": None, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "gate": None,
        "sub_engines_active": False, "sub_engines_status": "PAUSED", "specialists_active": False,
        "specialists_status": "PAUSED", "upstream_direction_used": False, "upstream_decisions_used": False,
        "upstream_gates_used": False, "score_used": False,
    }
    if len(clean) < MIN_CANDLES:
        reasons = ["E3_INSUFFICIENT_DATA", *data_errors[:4]]
        return {**base, "analysis_status": "INSUFFICIENT_DATA", "finding": "STRUCTURE_INSUFFICIENT_DATA", "structure": "UNKNOWN", "structure_state": "INSUFFICIENT_DATA", "direction": NEUTRAL, "directional_bias": NEUTRAL, "structural_bias": NEUTRAL, "swing_map": {"highs": [], "lows": []}, "internal_structure": {}, "external_structure": {}, "BOS": "NONE", "BOS_type": "NONE", "bos": {"event": "NO_BOS", "confirmed": False}, "structural_failure": "NONE", "failure_type": "NONE", "failure": {"event": "NO_FAILURE", "confirmed": False}, "strength": 0.0, "structure_strength": 0.0, "confidence": 0.0, "evidence": [], "observations": [], "conflicts": [], "reason_codes": reasons, "reasons": reasons, "reasoning_trace": {"closed_candles": len(clean), "pivot_windows": {"internal": INTERNAL_RADIUS, "external": EXTERNAL_RADIUS}}}

    atr = _atr(clean)
    ih, il = _label(_compress(_pivot_points(clean, "high", INTERNAL_RADIUS), atr, "high"), _compress(_pivot_points(clean, "low", INTERNAL_RADIUS), atr, "low"), atr)
    eh, el = _label(_compress(_pivot_points(clean, "high", EXTERNAL_RADIUS), atr, "high"), _compress(_pivot_points(clean, "low", EXTERNAL_RADIUS), atr, "low"), atr)
    internal_state, external_state = _classify(ih, il), _classify(eh, el)
    internal_count, external_count = _count_state(ih, il), _count_state(eh, el)
    internal_counts, external_counts = _counts(ih, il), _counts(eh, el)

    external_bos = _bos(clean, eh, el, atr, external_state, "EXTERNAL")
    internal_bos = _bos(clean, ih, il, atr, internal_state, "INTERNAL")
    failure = _failure(clean, eh, el, external_state, atr)
    choch = _choch(clean, eh, el, external_state, atr)
    slope_context, slope_quality = _slope(clean)
    protected = _protected(external_state, eh, el)

    conflicts = []
    if external_state in {UP, DOWN} and internal_state in {UP, DOWN} and external_state != internal_state:
        conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if external_count != NEUTRAL and external_count != external_state:
        conflicts.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if internal_count != NEUTRAL and internal_count != internal_state:
        conflicts.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if external_state == MIXED or internal_state == MIXED:
        conflicts.append("STRUCTURE_CONFLICT")
    if not external_bos.get("confirmed"):
        conflicts.append("NO_CONFIRMED_EXTERNAL_BOS")
    if failure.get("confirmed"):
        conflicts.append("FAILED_BREAK_DETECTED")
    if choch.get("confirmed"):
        conflicts.append("CHANGE_OF_CHARACTER_DETECTED")
    if external_state in {UP, DOWN} and slope_context in {UP, DOWN} and slope_context != external_state:
        conflicts.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    conflicts = list(dict.fromkeys(conflicts))

    # Professional hierarchy: failed break > CHOCH > external BOS > structural context.
    if failure.get("confirmed"):
        direction, state, finding = failure["direction"], "STRUCTURE_FAILURE", "FAILED_BREAK"
    elif choch.get("confirmed"):
        direction = choch["direction"]
        state = "CHANGE_OF_CHARACTER"
        finding = "BULLISH_CHOCH" if direction == UP else "BEARISH_CHOCH"
    elif external_bos.get("confirmed"):
        direction = external_bos["direction"]
        state = "BREAKOUT_CONFIRMED"
        finding = "BULLISH_BOS" if direction == UP else "BEARISH_BOS"
    elif external_state in {UP, DOWN}:
        direction, state = external_state, "DIRECTIONAL_CONTEXT_UNCONFIRMED"
        finding = "BULLISH_EXTERNAL_STRUCTURE" if direction == UP else "BEARISH_EXTERNAL_STRUCTURE"
    elif slope_context in {UP, DOWN} and not eh and not el:
        # Slope can describe an emerging directional context when structure has
        # not produced a confirmed swing map. It does NOT become structural bias.
        direction, state, finding = slope_context, "DIRECTIONAL_CONTEXT_UNCONFIRMED", "DEVELOPING_DIRECTIONAL_CONTEXT"
    else:
        direction, state = NEUTRAL, "RANGE_OR_UNCLEAR"
        finding = "STRUCTURE_NEUTRAL" if external_state == NEUTRAL else "MIXED_STRUCTURE"

    evidence_count = len(eh) + len(el)
    strength = 0.0
    strength += 0.25 if external_state in {UP, DOWN} else 0.10 if external_state == MIXED else 0.0
    strength += 0.20 if internal_state == external_state and external_state in {UP, DOWN} else 0.0
    strength += 0.15 if external_count == external_state and external_state in {UP, DOWN} else 0.0
    strength += 0.15 if external_bos.get("confirmed") else 0.0
    strength += 0.10 if failure.get("confirmed") or choch.get("confirmed") else 0.0
    strength += min(0.15, evidence_count / 80.0)
    if "INTERNAL_EXTERNAL_DIVERGENCE" in conflicts:
        strength -= 0.12
    if "STRUCTURE_CONFLICT" in conflicts:
        strength -= 0.08
    structure_strength = round(max(0.0, min(1.0, strength)), 4)

    observations = [
        f"closed_candles={len(clean)}", f"atr14={round(atr, 8)}",
        f"internal_structure={internal_state}", f"external_structure={external_state}",
        f"internal_count_state={internal_count}", f"external_count_state={external_count}",
        f"internal_counts={internal_counts}", f"external_counts={external_counts}",
        f"external_sequence={'→'.join(x['label'] for x in _sequence(eh, el)) or 'NONE'}",
        f"internal_sequence={'→'.join(x['label'] for x in _sequence(ih, il)) or 'NONE'}",
        f"external_bos={external_bos.get('event')}", f"internal_bos={internal_bos.get('event')}",
        f"structural_failure={failure.get('event')}", f"choch={choch.get('event')}",
        f"protected_high={protected.get('protected_high')}", f"protected_low={protected.get('protected_low')}",
        f"slope_context={slope_context}", f"slope_quality={slope_quality}",
        "slope_is_context_only=True", f"structure_strength={structure_strength}",
    ]

    reason_codes = []
    if not external_bos.get("confirmed"):
        reason_codes.append("NO_CONFIRMED_EXTERNAL_BOS")
    if internal_state != external_state and internal_state in {UP, DOWN} and external_state in {UP, DOWN}:
        reason_codes.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if external_state == MIXED or internal_state == MIXED:
        reason_codes.append("STRUCTURE_CONFLICT")
    if external_state in {UP, DOWN} and slope_context != external_state:
        reason_codes.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    if failure.get("confirmed"):
        reason_codes.append("FAILED_BREAK_DETECTED")
    if choch.get("confirmed"):
        reason_codes.append("CHANGE_OF_CHARACTER_DETECTED")
    reason_codes = list(dict.fromkeys(reason_codes))

    failure_output = dict(failure)
    if failure_output.get("event") == "FAILED_BREAK":
        # Public E3 contract uses FAILED_BOS; helper retains FAILED_BREAK for
        # backwards compatibility with the low-level regression tests.
        failure_output["event"] = "FAILED_BOS"

    def compact(x):
        return {"event": x.get("event"), "direction": x.get("direction"), "confirmed": bool(x.get("confirmed")), "level": x.get("level"), "swing_index": x.get("swing_index"), "swing_label": x.get("swing_label"), "break_candle_index": x.get("break_candle_index"), "break_distance_atr": x.get("break_distance_atr"), "break_body_atr": x.get("break_body_atr"), "close_location": x.get("close_location"), "displacement_ok": x.get("displacement_ok"), "close_beyond_level": x.get("close_beyond_level"), "scope": x.get("scope")}

    return {
        **base, "analysis_status": "COMPLETE", "finding": finding, "structure": external_state,
        "structure_state": state, "direction": direction, "directional_bias": direction, "structural_bias": external_state,
        "swing_map": {"highs": eh, "lows": el},
        "internal_structure": {"state": internal_state, "count_state": internal_count, "counts": internal_counts, "highs": ih, "lows": il, "bos": compact(internal_bos)},
        "external_structure": {"state": external_state, "count_state": external_count, "counts": external_counts, "highs": eh, "lows": el, "bos": compact(external_bos), "protected_high": protected.get("protected_high"), "protected_low": protected.get("protected_low")},
        "HH": external_counts["HH"], "HL": external_counts["HL"], "LH": external_counts["LH"], "LL": external_counts["LL"],
        "BOS": external_bos.get("event", "NO_BOS"), "bos": compact(external_bos), "BOS_type": external_bos.get("event", "NONE"),
        "bos_level": external_bos.get("level"), "BOS_candle_index": external_bos.get("break_candle_index"),
        "structural_failure": failure_output.get("event", "NONE"), "failure": failure_output, "failure_type": failure_output.get("event", "NONE"), "failure_level": failure_output.get("level"),
        "strength": structure_strength, "structure_strength": structure_strength, "confidence": structure_strength, "atr": round(atr, 8),
        "recent_high": eh[-1] if eh else None, "recent_low": el[-1] if el else None, "prior_high": eh[-2] if len(eh) >= 2 else None, "prior_low": el[-2] if len(el) >= 2 else None,
        "evidence": [
            {"type": "EXTERNAL_STRUCTURE", "state": external_state, "counts": external_counts},
            {"type": "INTERNAL_STRUCTURE", "state": internal_state, "counts": internal_counts},
            {"type": "EXTERNAL_BOS", **compact(external_bos)}, {"type": "INTERNAL_BOS", **compact(internal_bos)},
            {"type": "STRUCTURAL_FAILURE", **failure_output},
        ],
        "observations": observations, "conflicts": conflicts, "reason_codes": reason_codes, "reasons": reason_codes,
        "reasoning_trace": {
            "closed_candles": len(clean), "pivot_windows": {"internal": INTERNAL_RADIUS, "external": EXTERNAL_RADIUS},
            "atr_normalization": {"atr_period": 14, "pivot_prominence_atr": PROMINENCE_ATR, "equal_swing_tolerance_atr": EQ_TOLERANCE_ATR, "bos_close_distance_atr": BOS_CLOSE_ATR, "bos_body_atr": BOS_BODY_ATR},
            "swing_references": {"external_high_count": len(eh), "external_low_count": len(el), "internal_high_count": len(ih), "internal_low_count": len(il)},
            "structural_levels": {"protected_high": protected.get("protected_high"), "protected_low": protected.get("protected_low"), "recent_high": eh[-1] if eh else None, "recent_low": el[-1] if el else None},
            "events": {"external_bos": compact(external_bos), "internal_bos": compact(internal_bos), "failure": failure_output, "choch": compact(choch)},
            "external_state": external_state, "internal_state": internal_state,
            "external_count_state": external_count, "internal_count_state": internal_count,
            "states": {"external": external_state, "internal": internal_state, "external_count": external_count, "internal_count": internal_count, "slope_context": slope_context},
            "slope_is_structural_authority": False, "upstream_context": "E1_E2_NOT_CONSUMED", "decision_boundary": "E9_ONLY", "gate": None, "score": None,
        },
    }
