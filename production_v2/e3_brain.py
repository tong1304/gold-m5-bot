from __future__ import annotations
"""E3 — Professional Market Structure Brain.

E3 answers one question only: "What is price structure communicating?"
It is deliberately independent from E1/E2 and has no trading authority.

Professional structure rules:
- only closed-candle OHLC evidence
- highs are compared with prior highs; lows with prior lows
- external structure has authority over internal noise
- BOS/CHOCH require a close beyond a structural level plus displacement/strong close
- wick-only breaks are not BOS
- failed breaks are explicitly identified
- slope is context only, never structural authority
- E9 remains the sole trade-decision authority
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V5"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 40
INTERNAL_RADIUS, EXTERNAL_RADIUS = 2, 5
PROMINENCE_ATR = 0.10
EQ_TOLERANCE_ATR = 0.10
MIN_SWING_SEPARATION = 2
BOS_CLOSE_ATR = 0.08
BOS_BODY_ATR = 0.20
BOS_CLOSE_LOCATION = 0.55
FAILURE_SWEEP_ATR = 0.05
FAILURE_RECLAIM_ATR = 0.05
RECENT_EVENT_BARS = 2


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
        vals = [_num(b.get(k)) for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            reasons.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = vals
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent")
            continue
        out.append({"open": o, "high": h, "low": l, "close": c})
    return out, reasons


def _tr(bars, i):
    if i <= 0 or i >= len(bars):
        return 0.0
    b, prev = bars[i], bars[i - 1]["close"]
    return max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev))


def _atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    start = max(1, len(bars) - period)
    vals = [_tr(bars, i) for i in range(start, len(bars))]
    return mean(vals) if vals else 0.0


def _atr_at(bars, i, period=14):
    if i <= 0:
        return 0.0
    vals = [_tr(bars, j) for j in range(max(1, i - period + 1), i + 1)]
    return mean(vals) if vals else 0.0


def _pivot_points(bars, side: str, radius: int):
    points = []
    for i in range(radius, len(bars) - radius):
        x = bars[i][side]
        left = [bars[j][side] for j in range(i - radius, i)]
        right = [bars[j][side] for j in range(i + 1, i + radius + 1)]
        prominence = PROMINENCE_ATR * max(_atr_at(bars, i), 1e-12)
        if side == "high" and x >= max(left) and x > max(right):
            if min(x - max(left), x - max(right)) >= prominence:
                points.append((i, x))
        elif side == "low" and x <= min(left) and x < min(right):
            if min(min(left) - x, min(right) - x) >= prominence:
                points.append((i, x))
    return points


def _compress(points, atr, side=None, spacing=2):
    """Cluster compression kept backward compatible with the E3 regression contract."""
    if side is None:
        side = "high" if not points else "high"
    out = []
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        old = out[-1]
        if abs(p[1] - old[1]) <= tol:
            # Infer side from which point is more extreme when caller omits side.
            if side == "high" or (side not in {"high", "low"}):
                if p[1] > old[1]:
                    out[-1] = p
            else:
                if p[1] < old[1]:
                    out[-1] = p
        elif side == "high" and p[1] > old[1]:
            out[-1] = p
        elif side == "low" and p[1] < old[1]:
            out[-1] = p
    return out


def _label(high_points, low_points, atr):
    """HH/LH are compared only against previous highs; HL/LL only against previous lows."""
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    highs, prev = [], None
    for idx, price in high_points:
        if prev is None:
            label = "SWING_HIGH"
        else:
            d = price - prev[1]
            label = "EQH" if abs(d) <= tol else ("HH" if d > 0 else "LH")
        highs.append({"index": int(idx), "price": round(float(price), 8), "label": label})
        prev = (idx, price)
    lows, prev = [], None
    for idx, price in low_points:
        if prev is None:
            label = "SWING_LOW"
        else:
            d = price - prev[1]
            label = "EQL" if abs(d) <= tol else ("HL" if d > 0 else "LL")
        lows.append({"index": int(idx), "price": round(float(price), 8), "label": label})
        prev = (idx, price)
    return highs, lows


def _latest(points, labels):
    return next((x for x in reversed(points) if x["label"] in labels), None)


def _classify_structure(highs, lows):
    h = _latest(highs, {"HH", "LH"})
    l = _latest(lows, {"HL", "LL"})
    if h and l and h["label"] == "HH" and l["label"] == "HL":
        return UP
    if h and l and h["label"] == "LH" and l["label"] == "LL":
        return DOWN
    return MIXED if h or l else NEUTRAL


def _count_state(highs, lows, window=8):
    recent = highs[-window:] + lows[-window:]
    bull = sum(x["label"] in {"HH", "HL"} for x in recent)
    bear = sum(x["label"] in {"LH", "LL"} for x in recent)
    if bull == 0 and bear == 0:
        return NEUTRAL
    if bull >= bear + 2:
        return UP
    if bear >= bull + 2:
        return DOWN
    return MIXED


def _counts(highs, lows, window=8):
    c = {k: 0 for k in ("HH", "HL", "LH", "LL", "EQH", "EQL")}
    for x in highs[-window:] + lows[-window:]:
        if x["label"] in c:
            c[x["label"]] += 1
    return c


def _sequence(highs, lows, limit=12):
    return sorted(highs + lows, key=lambda x: x["index"])[-limit:]


def _protected_levels(structure, highs, lows):
    if structure == UP:
        return {
            "protected_low": _latest(lows, {"HL"}),
            "protected_high": _latest(highs, {"HH", "EQH"}),
        }
    if structure == DOWN:
        return {
            "protected_low": _latest(lows, {"LL", "EQL"}),
            "protected_high": _latest(highs, {"LH", "EQH"}),
        }
    return {
        "protected_low": _latest(lows, {"HL", "LL"}),
        "protected_high": _latest(highs, {"HH", "LH"}),
    }


def _break_quality(bar, level, direction, atr):
    if atr <= 0 or level is None:
        return {"confirmed": False}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body_atr = abs(bar["close"] - bar["open"]) / atr
    close_location = (bar["close"] - bar["low"]) / rng
    if direction == UP:
        distance_atr = (bar["close"] - level) / atr
        close_ok = distance_atr >= BOS_CLOSE_ATR
        location_ok = close_location >= BOS_CLOSE_LOCATION
    else:
        distance_atr = (level - bar["close"]) / atr
        close_ok = distance_atr >= BOS_CLOSE_ATR
        location_ok = close_location <= (1.0 - BOS_CLOSE_LOCATION)
    displacement_ok = body_atr >= BOS_BODY_ATR
    return {
        "confirmed": bool(close_ok and (displacement_ok or location_ok)),
        "distance_atr": round(max(0.0, distance_atr), 4),
        "body_atr": round(body_atr, 4),
        "close_location": round(close_location, 4),
        "displacement_ok": displacement_ok,
        "close_beyond_level": close_ok,
    }


def _detect_break(bars, highs, lows, structure, atr, scope="EXTERNAL"):
    """Continuation BOS against the current trend's structural extreme."""
    if not bars or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    p = _protected_levels(structure, highs, lows)
    candidate = None
    if structure == UP and p["protected_high"]:
        candidate = (p["protected_high"], UP)
    elif structure == DOWN and p["protected_low"]:
        candidate = (p["protected_low"], DOWN)
    elif structure == MIXED:
        candidates = []
        for s, d in ((highs[-1] if highs else None, UP), (lows[-1] if lows else None, DOWN)):
            if s:
                q = _break_quality(bars[-1], s["price"], d, atr)
                if q["confirmed"]:
                    candidates.append((s, d, q))
        if len(candidates) == 1:
            s, d, q = candidates[0]
            return {"event": "CONFIRMED_BOS", "direction": d, "confirmed": True, "scope": scope,
                    "level": s["price"], "swing_index": s["index"], "swing_label": s["label"],
                    "break_candle_index": len(bars) - 1, "break_distance_atr": q["distance_atr"],
                    "break_body_atr": q["body_atr"], "close_location": q["close_location"],
                    "displacement_ok": q["displacement_ok"], "close_beyond_level": q["close_beyond_level"]}
        if len(candidates) > 1:
            return {"event": "CONFLICTING_BOS", "direction": MIXED, "confirmed": False, "scope": scope}
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    if candidate:
        s, d = candidate
        q = _break_quality(bars[-1], s["price"], d, atr)
        if q["confirmed"]:
            return {"event": "CONFIRMED_BOS", "direction": d, "confirmed": True, "scope": scope,
                    "level": s["price"], "swing_index": s["index"], "swing_label": s["label"],
                    "break_candle_index": len(bars) - 1, "break_distance_atr": q["distance_atr"],
                    "break_body_atr": q["body_atr"], "close_location": q["close_location"],
                    "displacement_ok": q["displacement_ok"], "close_beyond_level": q["close_beyond_level"]}
    return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _detect_choch(bars, highs, lows, structure, atr, scope="EXTERNAL"):
    """Reversal event: break of the protected swing opposite the established structure."""
    if structure not in {UP, DOWN} or not bars or atr <= 0:
        return {"event": "NO_CHOCH", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    p = _protected_levels(structure, highs, lows)
    if structure == UP and p["protected_low"]:
        s, d = p["protected_low"], DOWN
    elif structure == DOWN and p["protected_high"]:
        s, d = p["protected_high"], UP
    else:
        return {"event": "NO_CHOCH", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    q = _break_quality(bars[-1], s["price"], d, atr)
    if not q["confirmed"]:
        return {"event": "NO_CHOCH", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    return {"event": "CONFIRMED_CHOCH", "direction": d, "confirmed": True, "scope": scope,
            "level": s["price"], "swing_index": s["index"], "swing_label": s["label"],
            "break_candle_index": len(bars) - 1, "break_distance_atr": q["distance_atr"],
            "break_body_atr": q["body_atr"], "close_location": q["close_location"],
            "displacement_ok": q["displacement_ok"], "close_beyond_level": q["close_beyond_level"]}


def _detect_failure(bars, highs, lows, structure, atr):
    if not bars or atr <= 0:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    b = bars[-1]
    p = _protected_levels(structure, highs, lows)
    candidates = []
    if p["protected_high"]:
        s = p["protected_high"]
        sweep = (b["high"] - s["price"]) / atr
        reclaim = (s["price"] - b["close"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append((DOWN, s, sweep, reclaim))
    if p["protected_low"]:
        s = p["protected_low"]
        sweep = (s["price"] - b["low"]) / atr
        reclaim = (b["close"] - s["price"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append((UP, s, sweep, reclaim))
    if len(candidates) != 1:
        if candidates:
            return {"event": "CONFLICTING_FAILURES", "direction": MIXED, "confirmed": False}
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    d, s, sweep, reclaim = candidates[0]
    return {"event": "FAILED_BOS", "direction": d, "confirmed": True,
            "level": s["price"], "swing_index": s["index"], "swing_label": s["label"],
            "failure_candle_index": len(bars) - 1, "scope": "EXTERNAL",
            "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4)}


# Backward-compatible core test API. These wrappers contain no extra trading logic.
def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    if prior_structure == DOWN:
        return _detect_choch(bars, highs, lows, prior_structure, atr, scope)
    return _detect_break(bars, highs, lows, prior_structure, atr, scope)


def _sweep_failure(bars, highs, lows, atr=None, prior_structure="UP"):
    if atr is None:
        atr = _atr(bars)
    return _detect_failure(bars, highs, lows, prior_structure, atr)


def _slope_context(bars, lookback=20):
    if len(bars) < 5:
        return NEUTRAL, 0.0
    c = [b["close"] for b in bars[-lookback:]]
    n = (c[-1] - c[0]) / (max(_atr(bars), 1e-12) * max(1, len(c) - 1))
    q = min(1.0, abs(n) * 8.0)
    return (UP if n > 0.035 else DOWN if n < -0.035 else NEUTRAL), round(q, 4)


def _structural_quality(ext, inte, ext_count, int_count, bos, choch, failure, recent):
    q = 0.25
    if ext in {UP, DOWN}: q += 0.20
    if ext == inte and ext in {UP, DOWN}: q += 0.20
    elif inte in {UP, DOWN} and ext in {UP, DOWN}: q += 0.05
    if ext_count == ext and ext in {UP, DOWN}: q += 0.10
    if int_count == inte and inte in {UP, DOWN}: q += 0.05
    if bos.get("confirmed") and recent: q += 0.12
    if choch.get("confirmed") and recent: q += 0.08
    if failure.get("confirmed"): q -= 0.15
    if ext == MIXED or inte == MIXED: q -= 0.10
    return round(max(0.0, min(1.0, q)), 4)


def _base():
    return {"architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
            "decision": None, "trade_decision_authority": False, "decision_authority": "E9_ONLY",
            "gate": None, "sub_engines_active": False, "sub_engines_status": "PAUSED",
            "specialists_active": False, "specialists_status": "PAUSED", "upstream_direction_used": False,
            "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False}


def analyze_e3(bars):
    clean, data_reasons = _clean_bars(bars)
    base = _base()
    if len(clean) < MIN_CANDLES:
        reasons = ["E3_INSUFFICIENT_DATA", *data_reasons[:4]]
        return {**base, "analysis_status": "INSUFFICIENT_DATA", "finding": "STRUCTURE_INSUFFICIENT_DATA",
                "structure": "UNKNOWN", "structure_state": "INSUFFICIENT_DATA", "direction": NEUTRAL,
                "directional_bias": NEUTRAL, "structural_bias": NEUTRAL, "swing_map": {"highs": [], "lows": []},
                "internal_structure": {}, "external_structure": {}, "BOS": "NONE", "BOS_type": "NONE",
                "structural_failure": "NONE", "failure_type": "NONE", "strength": 0.0,
                "structure_strength": 0.0, "confidence": 0.0, "evidence": [], "observations": [],
                "conflicts": [], "reason_codes": reasons, "reasons": reasons,
                "reasoning_trace": {"closed_candles": len(clean)}}

    atr = _atr(clean)
    ihp = _compress(_pivot_points(clean, "high", INTERNAL_RADIUS), atr, "high")
    ilp = _compress(_pivot_points(clean, "low", INTERNAL_RADIUS), atr, "low")
    ehp = _compress(_pivot_points(clean, "high", EXTERNAL_RADIUS), atr, "high")
    elp = _compress(_pivot_points(clean, "low", EXTERNAL_RADIUS), atr, "low")
    ih, il = _label(ihp, ilp, atr)
    eh, el = _label(ehp, elp, atr)

    internal = _classify_structure(ih, il)
    external = _classify_structure(eh, el)
    internal_count, external_count = _count_state(ih, il), _count_state(eh, el)
    ic, ec = _counts(ih, il), _counts(eh, el)

    bos = _detect_break(clean, eh, el, external, atr)
    choch = _detect_choch(clean, eh, el, external, atr)
    failure = _detect_failure(clean, eh, el, external, atr)
    current = len(clean) - 1
    event_recent = any(x.get("confirmed") and current - x.get("break_candle_index", current) <= RECENT_EVENT_BARS
                       for x in (bos, choch))

    conflicts = []
    if external in {UP, DOWN} and internal in {UP, DOWN} and external != internal:
        conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if external_count != NEUTRAL and external_count != external:
        conflicts.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if internal_count != NEUTRAL and internal_count != internal:
        conflicts.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if bos.get("event") == "CONFLICTING_BOS": conflicts.append("CONFLICTING_BREAKS")
    if choch.get("confirmed"): conflicts.append("CHANGE_OF_CHARACTER_DETECTED")
    if failure.get("confirmed"): conflicts.append("FAILED_BREAK_DETECTED")
    if external == MIXED or internal == MIXED: conflicts.append("STRUCTURE_CONFLICT")
    if not eh or not el: conflicts.append("LIMITED_EXTERNAL_SWINGS")

    if failure.get("confirmed"):
        direction, state, finding = failure["direction"], "STRUCTURE_FAILURE", "FAILED_BREAK"
    elif choch.get("confirmed"):
        direction, state = choch["direction"], "CHANGE_OF_CHARACTER"
        finding = "BULLISH_CHOCH" if direction == UP else "BEARISH_CHOCH"
    elif bos.get("confirmed"):
        direction, state = bos["direction"], "BREAKOUT_CONFIRMED"
        finding = "BULLISH_BOS" if direction == UP else "BEARISH_BOS"
    elif external in {UP, DOWN}:
        direction, state = external, "DIRECTIONAL_CONTEXT_UNCONFIRMED"
        finding = "BULLISH_EXTERNAL_STRUCTURE" if external == UP else "BEARISH_EXTERNAL_STRUCTURE"
    else:
        direction = NEUTRAL if external == MIXED else external
        state = "RANGE_OR_UNCLEAR" if external == MIXED else "DIRECTIONAL_CONTEXT_UNCONFIRMED"
        finding = "MIXED_STRUCTURE" if external == MIXED else "STRUCTURE_NEUTRAL"

    slope, slope_q = _slope_context(clean)
    if external in {UP, DOWN} and slope in {UP, DOWN} and slope != external:
        conflicts.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    if bos.get("confirmed") and choch.get("confirmed"):
        conflicts.append("BOS_CHOCH_SIMULTANEOUS")
    conflicts = list(dict.fromkeys(conflicts))

    strength = _structural_quality(external, internal, external_count, internal_count, bos, choch, failure, event_recent)
    confidence = strength
    if external == MIXED: confidence = min(confidence, 0.55)
    if "INTERNAL_EXTERNAL_DIVERGENCE" in conflicts: confidence = min(confidence, 0.60)
    if "SLOPE_DISAGREES_WITH_STRUCTURE" in conflicts: confidence = min(confidence, 0.65)
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    observations = [
        f"closed_candles={len(clean)}", f"atr14={atr:.8f}", f"external_structure={external}",
        f"internal_structure={internal}", f"external_count_state={external_count}",
        f"internal_count_state={internal_count}", f"external_counts={ec}", f"internal_counts={ic}",
        f"external_sequence={'→'.join(x['label'] for x in _sequence(eh, el))}",
        f"internal_sequence={'→'.join(x['label'] for x in _sequence(ih, il))}",
        f"slope_context={slope}", f"slope_quality={slope_q:.4f}",
        f"external_bos={bos.get('event')}", f"external_choch={choch.get('event')}",
        f"structural_failure={failure.get('event')}",
    ]
    reasons = list(dict.fromkeys([*conflicts,
                                  "CONFIRMED_EXTERNAL_BOS" if bos.get("confirmed") else "NO_CONFIRMED_EXTERNAL_BOS",
                                  "CONFIRMED_EXTERNAL_CHOCH" if choch.get("confirmed") else "NO_CONFIRMED_STRUCTURAL_REVERSAL"]))

    trace = {
        "closed_candles": len(clean), "atr14": round(atr, 8),
        "external_state": external, "internal_state": internal,
        "external_structure": external, "internal_structure": internal,
        "external_count_state": external_count, "internal_count_state": internal_count,
        "external_counts": ec, "internal_counts": ic,
        "external_sequence": _sequence(eh, el), "internal_sequence": _sequence(ih, il),
        "slope_context": slope, "slope_quality": slope_q, "slope_is_structural_authority": False,
        "external_bos": bos, "external_choch": choch, "structural_failure": failure,
        "event_recent": event_recent, "protected_levels": _protected_levels(external, eh, el),
    }
    evidence = {"external": {"structure": external, "count_state": external_count, "counts": ec,
                              "protected_levels": _protected_levels(external, eh, el)},
                "internal": {"structure": internal, "count_state": internal_count, "counts": ic},
                "BOS": bos, "CHOCH": choch, "failure": failure}

    return {**base, "analysis_status": "COMPLETE", "finding": finding, "structure": external,
            "structure_state": state, "direction": direction, "directional_bias": direction,
            "structural_bias": external,
            "external_structure": {"state": external, "count_state": external_count, "counts": ec,
                                    "swings": {"highs": eh, "lows": el}},
            "internal_structure": {"state": internal, "count_state": internal_count, "counts": ic,
                                    "swings": {"highs": ih, "lows": il}},
            "swing_map": {"highs": eh, "lows": el}, "BOS": bos.get("event", "NO_BOS"),
            "BOS_type": bos.get("event", "NO_BOS"), "bos": bos,
            "CHOCH": choch.get("event", "NO_CHOCH"), "choch": choch,
            "structural_failure": failure.get("event", "NO_FAILURE"),
            "failure_type": failure.get("event", "NO_FAILURE"), "failure": failure,
            "strength": strength, "structure_strength": strength, "confidence": confidence,
            "evidence": evidence, "observations": observations, "conflicts": conflicts,
            "reason_codes": reasons, "reasons": reasons, "reasoning_trace": trace}
