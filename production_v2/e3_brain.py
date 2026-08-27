from __future__ import annotations

"""E3 — Professional Market Structure Brain V5.

Scope: E3 only. E1/E2 and E4-E9 are not imported or modified.
E3 answers one question: "What is price structure communicating?"

Design principles:
- confirmed external structure is authoritative;
- internal structure is supporting evidence, never authority over external structure;
- counts describe evidence but never create a structure by themselves;
- a wick through a level is a liquidity sweep/failure, not BOS;
- BOS/CHOCH requires a CLOSED candle beyond a structural level with displacement
  or strong close location;
- slope is context only and cannot override structure;
- unresolved structure explicitly reports what price must break to resolve it.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V5"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
UNRESOLVED = "UNRESOLVED"
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
    if not points:
        return []
    side = side or "high"
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
    if bull == 2 and bear == 0:
        return UP
    if bear == 2 and bull == 0:
        return DOWN
    return MIXED if bull or bear else NEUTRAL


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
    # In unresolved structure, retain both sides as competing resolution levels.
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
        "event": event, "direction": direction, "confirmed": True, "scope": scope,
        "level": point["price"], "swing_index": point["index"], "swing_label": point["label"],
        "break_candle_index": idx, "break_distance_atr": q["distance_atr"],
        "break_body_atr": q["body_atr"], "close_location": q["close_location"],
        "displacement_ok": q["displacement_ok"], "close_beyond_level": q["close_beyond_level"],
    }


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    if not bars or atr <= 0:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    last, candidates = bars[-1], []
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
    return max(candidates, key=lambda x: x[0])[1] if candidates else {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _sweep_failure(bars, highs, lows, atr=None, prior_structure=UNRESOLVED):
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
            candidates.append({
                "event": "FAILED_BREAK", "direction": direction, "confirmed": True,
                "level": point["price"], "swing_index": point["index"], "swing_label": point["label"],
                "failure_candle_index": len(bars) - 1, "scope": "EXTERNAL",
                "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim, 4),
            })
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
    return (UP if z > .035 else DOWN if z < -.035 else NEUTRAL), round(min(1.0, abs(z) * 8.0), 4)


def _authority(external, internal, ext_bos, int_bos, failure):
    reasons = []
    if external in {UP, DOWN} and internal == external:
        authority = 1.0
    elif external in {UP, DOWN} and internal == MIXED:
        authority = .68
        reasons.append("INTERNAL_STRUCTURE_NOT_ALIGNED")
    elif external == MIXED and internal in {UP, DOWN}:
        authority = .48
        reasons.append("EXTERNAL_STRUCTURE_NOT_CONFIRMED")
    else:
        authority = .25 if external == MIXED or internal == MIXED else .10
        reasons.append("STRUCTURE_UNRESOLVED")
    if ext_bos.get("confirmed"):
        authority = min(1.0, authority + .18)
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        authority = min(.72, authority + .04)
        reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if failure.get("confirmed"):
        authority = min(authority, .60)
        reasons.append("LIQUIDITY_FAILURE_REQUIRES_CONFIRMATION")
    return round(authority, 4), reasons


def _resolution(structure, protected):
    hi, lo = protected.get("protected_high"), protected.get("protected_low")
    if structure == UP:
        return {"state": "BULLISH_CONTINUATION", "bullish_level": hi, "bearish_invalidation": lo}
    if structure == DOWN:
        return {"state": "BEARISH_CONTINUATION", "bullish_invalidation": hi, "bearish_level": lo}
    return {
        "state": "WAIT_FOR_STRUCTURAL_RESOLUTION",
        "bullish_resolution_level": hi,
        "bearish_resolution_level": lo,
        "bullish_condition": "CLOSED_CANDLE_ABOVE_PROTECTED_HIGH" if hi else "LEVEL_UNAVAILABLE",
        "bearish_condition": "CLOSED_CANDLE_BELOW_PROTECTED_LOW" if lo else "LEVEL_UNAVAILABLE",
    }


def _finding(external, internal, ext_bos, int_bos, failure, resolution):
    if failure.get("confirmed"):
        return f"LIQUIDITY_FAILURE={failure['direction']}"
    if ext_bos.get("confirmed"):
        return ext_bos["event"]
    if external == UP and internal == UP:
        return "BULLISH_STRUCTURE"
    if external == DOWN and internal == DOWN:
        return "BEARISH_STRUCTURE"
    if external in {UP, DOWN}:
        return f"{external}_EXTERNAL_STRUCTURE_INTERNAL_CONFLICT"
    return "MIXED_STRUCTURE"


def analyze_e3(bars):
    clean, data_reasons = _clean_bars(bars)
    if len(clean) < MIN_CANDLES:
        return {
            "architecture": ARCHITECTURE, "question": QUESTION, "finding": "INSUFFICIENT_DATA",
            "internal_structure": NEUTRAL, "external_structure": NEUTRAL,
            "internal_count_state": NEUTRAL, "external_count_state": NEUTRAL,
            "external_bos": "NO_BOS", "internal_bos": "NO_BOS",
            "protected_high": None, "protected_low": None,
            "resolution": {"state": "WAIT_FOR_DATA"}, "structure_resolution": "UNRESOLVED",
            "slope_context": NEUTRAL, "slope_quality": 0.0, "confidence": 0.0,
            "reason_codes": ["INSUFFICIENT_CANDLES"] + data_reasons[:8],
            "observations": [f"closed_candles={len(clean)}"],
        }

    atr = _atr(clean)
    ih = _compress(_pivot_points(clean, "high", INTERNAL_RADIUS), atr, "high")
    il = _compress(_pivot_points(clean, "low", INTERNAL_RADIUS), atr, "low")
    eh = _compress(_pivot_points(clean, "high", EXTERNAL_RADIUS), atr, "high")
    el = _compress(_pivot_points(clean, "low", EXTERNAL_RADIUS), atr, "low")
    ihl, ill = _label(ih, il, atr)
    ehl, ell = _label(eh, el, atr)

    internal = _classify(ihl, ill)
    external = _classify(ehl, ell)
    internal_counts = _counts(ihl, ill)
    external_counts = _counts(ehl, ell)
    internal_count_state = _count_state(ihl, ill)
    external_count_state = _count_state(ehl, ell)

    # E3 has one authority hierarchy: external structure > internal structure > counts.
    # Counts are diagnostics only.
    ext_bos = _bos(clean, ehl, ell, atr, external, "EXTERNAL")
    int_bos = _bos(clean, ihl, ill, atr, internal, "INTERNAL")
    failure = _failure(clean, ehl, ell, external, atr)
    choch = _choch(clean, ehl, ell, external, atr)
    authority, authority_reasons = _authority(external, internal, ext_bos, int_bos, failure)
    protected = _protected(external, ehl, ell)
    resolution = _resolution(external, protected)
    slope_context, slope_quality = _slope(clean)

    # A current closed candle that both sweeps and reclaims is a failure event,
    # never a BOS. External BOS has precedence over internal BOS as authority.
    if failure.get("confirmed"):
        primary_event = failure
        structure_resolution = "LIQUIDITY_FAILURE_PENDING_CONFIRMATION"
    elif ext_bos.get("confirmed"):
        primary_event = ext_bos
        structure_resolution = ext_bos["event"]
    elif choch.get("confirmed"):
        primary_event = choch
        structure_resolution = choch["event"]
    elif int_bos.get("confirmed"):
        primary_event = int_bos
        structure_resolution = "INTERNAL_BREAK_EXTERNAL_AUTHORITY_UNCHANGED"
    else:
        primary_event = {"event": "NO_STRUCTURAL_EVENT", "direction": NEUTRAL, "confirmed": False}
        structure_resolution = resolution["state"]

    reasons = list(data_reasons[:4])
    reasons.extend(authority_reasons)
    if external_count_state != external:
        reasons.append("EXTERNAL_COUNT_STATE_DIVERGENCE")
    if internal_count_state != internal:
        reasons.append("INTERNAL_COUNT_STATE_DIVERGENCE")
    if ext_bos.get("event") == "NO_BOS":
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if int_bos.get("confirmed") and not ext_bos.get("confirmed"):
        reasons.append("INTERNAL_BREAK_NOT_EXTERNAL_AUTHORITY")
    if slope_context != external and external in {UP, DOWN}:
        reasons.append("SLOPE_DISAGREES_WITH_STRUCTURE")
    if external == MIXED or internal == MIXED:
        reasons.append("STRUCTURE_UNRESOLVED")
    if primary_event.get("event") == "NO_STRUCTURAL_EVENT" and external == MIXED:
        reasons.append("WAIT_FOR_STRUCTURAL_RESOLUTION")
    reasons = list(dict.fromkeys(reasons))

    # Confidence reflects structural agreement, event quality and data sufficiency;
    # it is descriptive evidence, not a trade score.
    confidence = min(1.0, 0.55 + 0.20 * authority + (0.15 if ext_bos.get("confirmed") else 0.0))
    if external == MIXED:
        confidence = min(confidence, 0.55)
    if failure.get("confirmed"):
        confidence = min(confidence, 0.60)

    seq_ext = _sequence(ehl, ell)
    seq_int = _sequence(ihl, ill)
    fmt = lambda seq: "→".join(x["label"] for x in seq)
    observation = [
        f"closed_candles={len(clean)}", f"atr14={round(atr, 8)}",
        f"external_structure={external}", f"internal_structure={internal}",
        f"external_count_state={external_count_state}", f"internal_count_state={internal_count_state}",
        f"external_bos={ext_bos.get('event')}", f"internal_bos={int_bos.get('event')}",
        f"primary_event={primary_event.get('event')}", f"structure_authority={authority}",
    ]

    out = {
        "architecture": ARCHITECTURE,
        "question": QUESTION,
        "finding": _finding(external, internal, ext_bos, int_bos, failure, resolution),
        "internal_structure": internal,
        "external_structure": external,
        "internal_count_state": internal_count_state,
        "external_count_state": external_count_state,
        "internal_counts": internal_counts,
        "external_counts": external_counts,
        "external_sequence": fmt(seq_ext),
        "internal_sequence": fmt(seq_int),
        "external_bos": ext_bos.get("event", "NO_BOS"),
        "internal_bos": int_bos.get("event", "NO_BOS"),
        "external_bos_detail": ext_bos,
        "internal_bos_detail": int_bos,
        "choch": choch,
        "failure": failure,
        "primary_event": primary_event,
        "protected_high": protected.get("protected_high", {}).get("price") if protected.get("protected_high") else None,
        "protected_low": protected.get("protected_low", {}).get("price") if protected.get("protected_low") else None,
        "protected_high_detail": protected.get("protected_high"),
        "protected_low_detail": protected.get("protected_low"),
        "structure_authority": authority,
        "structure_resolution": structure_resolution,
        "resolution": resolution,
        "next_structural_event": resolution,
        "slope_context": slope_context,
        "slope_quality": slope_quality,
        "atr14": round(atr, 8),
        "closed_candles": len(clean),
        "confidence": round(confidence, 4),
        "observations": observation,
        "reason_codes": reasons,
        "decision": None,
        "gate": None,
        "trade_decision_authority": False,
    }
    return out
