from __future__ import annotations

"""E3 V6 — single professional market-structure brain.

E3 is analysis-only. It never consumes E1/E2 direction, score, gate, or
trade decision, and it never authorizes a trade. External structure is the
highest structural authority; internal structure and counts are evidence.
All break decisions are based on closed candles.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V6"
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
        if side == "high" and x >= max(left) and x > max(right):
            if min(x - max(left), x - max(right)) >= prominence:
                out.append((i, x))
        if side == "low" and x <= min(left) and x < min(right):
            if min(min(left) - x, min(right) - x) >= prominence:
                out.append((i, x))
    return out


def _compress(points, atr, side=None, spacing=2):
    points = list(points or [])
    if not points:
        return []
    if side is None:
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
        d = 0.0 if prev is None else p - prev[1]
        label = "SWING_HIGH" if prev is None else "EQH" if abs(d) <= tol else "HH" if d > 0 else "LH"
        highs.append({"index": int(i), "price": round(float(p), 8), "label": label})
        prev = (i, p)
    lows, prev = [], None
    for i, p in lp:
        d = 0.0 if prev is None else p - prev[1]
        label = "SWING_LOW" if prev is None else "EQL" if abs(d) <= tol else "HL" if d > 0 else "LL"
        lows.append({"index": int(i), "price": round(float(p), 8), "label": label})
        prev = (i, p)
    return highs, lows


def _latest(xs, labels):
    return next((x for x in reversed(xs) if x["label"] in labels), None)


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
    """Classify from the latest two structural swings on each side.

    Unlike count-based classification, this does not let an old HH/HL pair
    outweigh a newer structural failure. Both sides must support a directional
    state; otherwise the state remains MIXED/NEUTRAL.
    """
    hs, ls = highs[-2:], lows[-2:]
    if len(hs) < 2 or len(ls) < 2:
        return NEUTRAL
    high_up = hs[-1]["price"] > hs[-2]["price"]
    high_down = hs[-1]["price"] < hs[-2]["price"]
    low_up = ls[-1]["price"] > ls[-2]["price"]
    low_down = ls[-1]["price"] < ls[-2]["price"]
    if high_up and low_up:
        return UP
    if high_down and low_down:
        return DOWN
    return MIXED


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
            candidates.append((q["distance_atr"], _event(last, high, UP, atr, event, scope, len(bars) - 1)))
    if low:
        q = _quality(last, low["price"], DOWN, atr)
        if q["confirmed"]:
            event = "CONFIRMED_CHOCH" if prior_structure == UP else "CONFIRMED_BOS"
            candidates.append((q["distance_atr"], _event(last, low, DOWN, atr, event, scope, len(bars) - 1)))
    return max(candidates, key=lambda x: x[0])[1] if candidates else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _sweep_failure(bars, highs, lows, atr=None, prior_structure=MIXED):
    if not bars:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    atr = atr or _atr(bars)
    if atr <= 0:
        atr = max(bars[-1]["high"] - bars[-1]["low"], 1e-12)
    b = bars[-1]
    p = _protected(prior_structure, highs, lows)
    candidates = []
    for point, direction in ((p.get("protected_high"), DOWN), (p.get("protected_low"), UP)):
        if not point:
            continue
        if direction == DOWN:
            sweep = (b["high"] - point["price"]) / atr
            reclaim = (point["price"] - b["close"]) / atr
        else:
            sweep = (point["price"] - b["low"]) / atr
            reclaim = (b["close"] - point["price"]) / atr
        if sweep >= FAILURE_SWEEP_ATR and reclaim >= FAILURE_RECLAIM_ATR:
            candidates.append({"event": "FAILED_BOS", "direction": direction, "confirmed": True, "level": point["price"], "swing_index": point["index"], "swing_label": point["label"], "failure_candle_index": len(bars) - 1, "scope": "EXTERNAL", "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4)})
    return max(candidates, key=lambda x: x["sweep_distance_atr"] + x["reclaim_distance_atr"]) if candidates else {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _structure_state(external, internal, bos, failure, slope):
    if failure.get("confirmed"):
        return "STRUCTURE_FAILURE"
    if bos.get("confirmed"):
        return "CHANGE_OF_CHARACTER" if bos.get("event") == "CONFIRMED_CHOCH" else "BREAKOUT_CONFIRMED"
    if external in {UP, DOWN} and internal == external:
        return "CONTINUATION"
    if external in {UP, DOWN} and internal == MIXED:
        return "INTERNAL_CONFLICT"
    if external == MIXED and internal in {UP, DOWN}:
        return "INTERNAL_COUNTER_MOVE"
    if slope in {UP, DOWN}:
        return "DIRECTIONAL_CONTEXT_UNCONFIRMED"
    return "RANGE_OR_UNCLEAR"


def _state_reason(external, internal, ext_count, int_count, slope):
    reasons = []
    if ext_count != external:
        reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if int_count != internal:
        reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if external == MIXED:
        reasons.append("STRUCTURE_UNRESOLVED")
    if slope != external and external in {UP, DOWN}:
        reasons.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    return list(dict.fromkeys(reasons))


def _slope(bars, n=20):
    if len(bars) < 5:
        return NEUTRAL, 0.0
    closes = [x["close"] for x in bars[-n:]]
    z = (closes[-1] - closes[0]) / (max(_atr(bars), 1e-12) * max(1, len(closes) - 1))
    return (UP if z > .035 else DOWN if z < -.035 else NEUTRAL), round(min(1.0, abs(z) * 8.0), 4)


def _empty(status, reasons):
    return {
        "architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
        "analysis_status": status, "finding": "INSUFFICIENT_DATA", "direction": NEUTRAL,
        "structure_state": "RANGE_OR_UNCLEAR", "internal_structure": {"state": NEUTRAL, "count_state": NEUTRAL},
        "external_structure": {"state": NEUTRAL, "count_state": NEUTRAL}, "internal_count_state": NEUTRAL,
        "external_count_state": NEUTRAL, "swing_map": {"internal_highs": [], "internal_lows": [], "external_highs": [], "external_lows": []},
        "bos": {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False}, "failure": {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False},
        "structure_strength": 0.0, "confidence": 0.0, "evidence": [], "conflicts": [], "reason_codes": reasons,
        "observations": [f"closed_candles={status}"], "reasoning_trace": {"external_state": NEUTRAL, "internal_state": NEUTRAL, "external_count_state": NEUTRAL, "internal_count_state": NEUTRAL, "slope_is_structural_authority": False},
        "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False,
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None,
        "specialists_active": False, "specialists_status": "PAUSED",
    }


def analyze_e3(bars):
    clean, data_reasons = _clean_bars(bars)
    if len(clean) < MIN_CANDLES:
        return _empty("INCOMPLETE", ["INSUFFICIENT_CANDLES"] + data_reasons[:8])

    atr = _atr(clean)
    ih = _compress(_pivot_points(clean, "high", INTERNAL_RADIUS), atr, "high")
    il = _compress(_pivot_points(clean, "low", INTERNAL_RADIUS), atr, "low")
    eh = _compress(_pivot_points(clean, "high", EXTERNAL_RADIUS), atr, "high")
    el = _compress(_pivot_points(clean, "low", EXTERNAL_RADIUS), atr, "low")
    ihl, ill = _label(ih, il, atr)
    ehl, ell = _label(eh, el, atr)
    internal, external = _classify(ihl, ill), _classify(ehl, ell)
    int_count, ext_count = _count_state(ihl, ill), _count_state(ehl, ell)
    int_counts, ext_counts = _counts(ihl, ill), _counts(ehl, ell)
    ext_bos = _bos(clean, ehl, ell, atr, external, "EXTERNAL")
    int_bos = _bos(clean, ihl, ill, atr, internal, "INTERNAL")
    failure = _sweep_failure(clean, ehl, ell, atr, external)
    slope, slope_quality = _slope(clean)
    state = _structure_state(external, internal, ext_bos, failure, slope)
    reasons = _state_reason(external, internal, ext_count, int_count, slope)
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if ext_bos.get("event") == "NO_BOS":
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    reasons = list(dict.fromkeys(reasons))

    direction = external if external in {UP, DOWN} else (int_bos.get("direction") if int_bos.get("confirmed") else NEUTRAL)
    finding = "LIQUIDITY_FAILURE=" + failure["direction"] if failure.get("confirmed") else ext_bos.get("event") if ext_bos.get("confirmed") else "BULLISH_STRUCTURE" if external == UP and internal == UP else "BEARISH_STRUCTURE" if external == DOWN and internal == DOWN else "MIXED_STRUCTURE"
    authority = 1.0 if external in {UP, DOWN} and internal == external else 0.68 if external in {UP, DOWN} else 0.48 if internal in {UP, DOWN} else 0.25
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        authority = min(.72, authority)
    if failure.get("confirmed"):
        authority = min(.60, authority)
    confidence = min(1.0, 0.55 + 0.20 * authority + (0.15 if ext_bos.get("confirmed") else 0.0))
    if external == MIXED:
        confidence = min(confidence, 0.55)
    if failure.get("confirmed"):
        confidence = min(confidence, 0.60)

    protected = _protected(external, ehl, ell)
    swing_map = {"internal_highs": ihl, "internal_lows": ill, "external_highs": ehl, "external_lows": ell}
    evidence = [
        f"external_structure={external}", f"internal_structure={internal}", f"external_count_state={ext_count}",
        f"internal_count_state={int_count}", f"external_bos={ext_bos.get('event')}", f"internal_bos={int_bos.get('event')}",
        f"slope_context={slope}", f"slope_quality={slope_quality}", f"structure_authority={round(authority, 4)}",
    ]
    conflicts = []
    if external != int_count:
        conflicts.append("EXTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE")
    if internal != int_count and internal != ext_count:
        conflicts.append("INTERNAL_STRUCTURAL_STATE_VS_COUNT_STATE")
    if slope != external and external in {UP, DOWN}:
        conflicts.append("SLOPE_VS_EXTERNAL_STRUCTURE")
    reasoning_trace = {
        "external_state": external, "internal_state": internal, "external_count_state": ext_count,
        "internal_count_state": int_count, "slope_context": slope, "slope_is_structural_authority": False,
        "external_bos_confirmed": bool(ext_bos.get("confirmed")), "internal_bos_confirmed": bool(int_bos.get("confirmed")),
        "external_is_authority": True, "closed_candle_only": True,
    }
    return {
        "architecture": ARCHITECTURE, "reasoning_role": "MARKET_STRUCTURE_ANALYST", "question": QUESTION,
        "analysis_status": "COMPLETE", "finding": finding, "direction": direction, "structure_state": state,
        "internal_structure": {"state": internal, "count_state": int_count, "counts": int_counts},
        "external_structure": {"state": external, "count_state": ext_count, "counts": ext_counts},
        "internal_count_state": int_count, "external_count_state": ext_count,
        "internal_counts": int_counts, "external_counts": ext_counts,
        "internal_sequence": "→".join(x["label"] for x in sorted(ihl + ill, key=lambda x: x["index"])[-12:]),
        "external_sequence": "→".join(x["label"] for x in sorted(ehl + ell, key=lambda x: x["index"])[-12:]),
        "swing_map": swing_map, "atr14": round(atr, 8), "closed_candles": len(clean),
        "bos": ext_bos, "external_bos": ext_bos.get("event", "NO_BOS"), "internal_bos": int_bos.get("event", "NO_BOS"),
        "external_bos_detail": ext_bos, "internal_bos_detail": int_bos, "failure": failure,
        "protected_high": protected.get("protected_high", {}).get("price") if protected.get("protected_high") else None,
        "protected_low": protected.get("protected_low", {}).get("price") if protected.get("protected_low") else None,
        "structure_strength": round(authority, 4), "structure_authority": round(authority, 4), "confidence": round(confidence, 4),
        "evidence": evidence, "conflicts": conflicts, "reason_codes": reasons,
        "observations": [f"closed_candles={len(clean)}", f"atr14={round(atr, 8)}"] + evidence,
        "reasoning_trace": reasoning_trace, "slope_context": slope, "slope_quality": slope_quality,
        "upstream_direction_used": False, "upstream_decisions_used": False, "upstream_gates_used": False, "score_used": False,
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None,
        "specialists_active": False, "specialists_status": "PAUSED", "specialists": {},
    }


# Backward-compatible exports used by the E3 regression suite.
__all__ = ["analyze_e3", "_compress", "_bos", "_sweep_failure"]
