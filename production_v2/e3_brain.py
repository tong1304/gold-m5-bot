from __future__ import annotations

"""E3 — Professional Market Structure Brain V4.

E3 is a price-structure specialist. It reasons only from closed OHLC data and
never consumes upstream direction, decisions, gates, scores, or trade plans.
It identifies meaningful swings, external/internal structure, BOS/CHOCH,
failed breaks, protected structural levels, and structural clarity. E9 is the
only component allowed to make the trading decision.
"""

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V4"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"

MIN_CANDLES = 20
INTERNAL_RADIUS = 2
EXTERNAL_RADIUS = 5
PROMINENCE_ATR = 0.10
BOS_DISTANCE_ATR = 0.10
BOS_BODY_ATR = 0.20
FAILURE_CLOSE_ATR = 0.05
EQ_TOLERANCE_ATR = 0.10


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
            reasons.append(f"bar_{i}_not_mapping")
            continue
        v = {k: _num(b.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            reasons.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = (float(v[k]) for k in ("open", "high", "low", "close"))
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent")
            continue
        out.append({"open": o, "high": h, "low": l, "close": c})
    return out, reasons


def _atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    prev, trs = bars[0]["close"], []
    for b in bars[1:]:
        trs.append(max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev)))
        prev = b["close"]
    return mean(trs[-period:]) if trs else 0.0


def _atr_at(bars, index, period=14):
    start = max(1, index - period + 1)
    if index < 1:
        return 0.0
    trs = []
    for i in range(start, index + 1):
        b, prev = bars[i], bars[i - 1]["close"]
        trs.append(max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev)))
    return mean(trs) if trs else 0.0


def _pivots(bars, side, radius=2):
    """Return volatility-normalized, confirmed pivots.

    A pivot is confirmed only after ``radius`` candles exist on both sides.
    The prominence requirement prevents tiny M5 noise from becoming a swing.
    """
    if len(bars) < 2 * radius + 1:
        return []
    pts = []
    for i in range(radius, len(bars) - radius):
        x = bars[i][side]
        left = [bars[j][side] for j in range(i - radius, i)]
        right = [bars[j][side] for j in range(i + 1, i + radius + 1)]
        atr_i = max(_atr_at(bars, i), 1e-12)
        if side == "high":
            if x >= max(left) and x > max(right):
                prominence = min(x - max(left), x - max(right))
                if prominence >= PROMINENCE_ATR * atr_i:
                    pts.append((i, x))
        else:
            if x <= min(left) and x < min(right):
                prominence = min(min(left) - x, min(right) - x)
                if prominence >= PROMINENCE_ATR * atr_i:
                    pts.append((i, x))
    return pts


def _compress(points, atr, side, spacing=2):
    """Remove duplicate/noise pivots without changing structural intent."""
    out, tol = [], max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p[0] - out[-1][0] >= spacing:
            out.append(p)
            continue
        if abs(p[1] - out[-1][1]) <= tol:
            # Equal highs/lows are one liquidity/structure reference, not two.
            continue
        if side == "high" and p[1] > out[-1][1]:
            out[-1] = p
        elif side == "low" and p[1] < out[-1][1]:
            out[-1] = p
    return out


def _label(points, kind, atr):
    out, tol = [], max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for i, (idx, price) in enumerate(points):
        if i == 0:
            label = "SWING_HIGH" if kind == "HIGH" else "SWING_LOW"
        else:
            d = price - points[i - 1][1]
            if abs(d) <= tol:
                label = "EQH" if kind == "HIGH" else "EQL"
            elif kind == "HIGH":
                label = "HH" if d > 0 else "LH"
            else:
                label = "HL" if d > 0 else "LL"
        out.append({"index": idx, "price": round(price, 8), "label": label})
    return out


def _structure_direction(highs, lows):
    hd = next((x["label"] for x in reversed(highs) if x["label"] in {"HH", "LH"}), None)
    ld = next((x["label"] for x in reversed(lows) if x["label"] in {"HL", "LL"}), None)
    if hd == "HH" and ld == "HL":
        return UP
    if hd == "LH" and ld == "LL":
        return DOWN
    return MIXED if hd and ld else NEUTRAL


def _structure_counts(highs, lows):
    counts = {"HH": 0, "HL": 0, "LH": 0, "LL": 0}
    for item in highs[-6:] + lows[-6:]:
        label = item.get("label")
        if label in counts:
            counts[label] += 1
    bull = counts["HH"] + counts["HL"]
    bear = counts["LH"] + counts["LL"]
    if bull >= 2 and bull > bear + 1:
        state = UP
    elif bear >= 2 and bear > bull + 1:
        state = DOWN
    elif bull or bear:
        state = MIXED
    else:
        state = NEUTRAL
    return state, counts


def _latest_break_candidates(highs, lows, latest_index):
    h = next((x for x in reversed(highs) if x["index"] < latest_index), None)
    l = next((x for x in reversed(lows) if x["index"] < latest_index), None)
    out = []
    if h:
        out.append((float(h["price"]), int(h["index"]), UP))
    if l:
        out.append((float(l["price"]), int(l["index"]), DOWN))
    return out


def _candle_break_quality(bar, level, direction, atr):
    """Measure whether the close break has displacement characteristics."""
    if atr <= 0:
        return {"valid": False, "distance_atr": 0.0, "body_atr": 0.0, "close_location": 0.5}
    rng = max(bar["high"] - bar["low"], 1e-12)
    body = abs(bar["close"] - bar["open"])
    location = (bar["close"] - bar["low"]) / rng
    distance = (bar["close"] - level) if direction == UP else (level - bar["close"])
    body_atr = body / atr
    close_ok = distance >= BOS_DISTANCE_ATR * atr
    directional_close = location >= 0.55 if direction == UP else location <= 0.45
    # A close beyond the level is mandatory. A small body is allowed only when
    # the close is decisively positioned in the candle range.
    quality_ok = body_atr >= BOS_BODY_ATR or directional_close
    return {
        "valid": bool(close_ok and quality_ok),
        "distance_atr": round(max(0.0, distance / atr), 4),
        "body_atr": round(body_atr, 4),
        "close_location": round(location, 4),
        "close_beyond_level": bool(close_ok),
        "displacement_ok": bool(quality_ok),
    }


def _bos(bars, highs, lows, atr, prior_structure, scope="EXTERNAL"):
    if atr <= 0 or len(bars) < 2:
        return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    latest = bars[-1]
    candidates = []
    for level, idx, direction in _latest_break_candidates(highs, lows, len(bars) - 1):
        quality = _candle_break_quality(latest, level, direction, atr)
        if not quality["valid"]:
            continue
        event = "CONFIRMED_CHOCH" if prior_structure in {UP, DOWN} and direction != prior_structure else "CONFIRMED_BOS"
        candidates.append({
            "event": event,
            "direction": direction,
            "confirmed": True,
            "scope": scope,
            "level": round(level, 8),
            "swing_index": idx,
            "break_candle_index": len(bars) - 1,
            "break_distance_atr": quality["distance_atr"],
            "break_body_atr": quality["body_atr"],
            "close_location": quality["close_location"],
            "close_beyond_level": True,
            "displacement_ok": quality["displacement_ok"],
        })
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return {"event": "CONFLICTING_BREAKS", "direction": MIXED, "confirmed": False, "scope": scope, "candidates": candidates}
    return {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False, "scope": scope}


def _sweep_failure(bars, highs, lows):
    if not bars:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    b = bars[-1]
    failures = []
    for level, idx, direction in _latest_break_candidates(highs, lows, len(bars) - 1):
        if direction == UP and b["high"] > level and b["close"] < level:
            failures.append({
                "event": "FAILED_BREAK",
                "direction": DOWN,
                "confirmed": True,
                "level": round(level, 8),
                "swing_index": idx,
                "failure_candle_index": len(bars) - 1,
                "scope": "EXTERNAL",
            })
        elif direction == DOWN and b["low"] < level and b["close"] > level:
            failures.append({
                "event": "FAILED_BREAK",
                "direction": UP,
                "confirmed": True,
                "level": round(level, 8),
                "swing_index": idx,
                "failure_candle_index": len(bars) - 1,
                "scope": "EXTERNAL",
            })
    if len(failures) == 1:
        return failures[0]
    if len(failures) > 1:
        return {"event": "CONFLICTING_FAILURES", "direction": MIXED, "confirmed": False}
    return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _failure(bars, bos, atr):
    # Public-test-compatible helper. A confirmed BOS can fail only when a
    # later/current closed candle sweeps the level and closes materially back.
    if not bos.get("confirmed") or atr <= 0 or not bars:
        return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}
    level, direction, b = float(bos["level"]), bos["direction"], bars[-1]
    if direction == UP and b["high"] > level and b["close"] < level - atr * FAILURE_CLOSE_ATR:
        return {"event": "FAILED_BOS", "direction": DOWN, "confirmed": True, "level": level, "failure_candle_index": len(bars) - 1}
    if direction == DOWN and b["low"] < level and b["close"] > level + atr * FAILURE_CLOSE_ATR:
        return {"event": "FAILED_BOS", "direction": UP, "confirmed": True, "level": level, "failure_candle_index": len(bars) - 1}
    return {"event": "NO_FAILURE", "direction": NEUTRAL, "confirmed": False}


def _slope_direction(bars, lookback=20):
    """Diagnostic only. Slope is never allowed to define structure."""
    closes = [b["close"] for b in bars[-lookback:]]
    if len(closes) < 5:
        return NEUTRAL, 0.0
    n = (closes[-1] - closes[0]) / (max(_atr(bars), 1e-12) * max(len(closes) - 1, 1))
    q = min(1.0, abs(n) * 8.0)
    return (UP if n > 0.035 else DOWN if n < -0.035 else NEUTRAL), q


def _strength(external, internal, bos, failure, swing_count, conflicts):
    """Structural clarity, not a trade score or win probability."""
    s = 0.25
    if external in {UP, DOWN}:
        s += 0.25
    if internal == external and internal in {UP, DOWN}:
        s += 0.22
    elif internal == MIXED:
        s += 0.03
    elif internal in {UP, DOWN} and external in {UP, DOWN}:
        s += 0.08
    if bos.get("confirmed"):
        s += min(0.20, 0.08 + float(bos.get("break_distance_atr", 0.0)) * 0.04)
        if bos.get("displacement_ok"):
            s += 0.05
    if failure.get("confirmed"):
        s -= 0.18
    s += min(0.08, max(0, swing_count) * 0.003)
    s -= min(0.20, len(conflicts) * 0.07)
    return round(max(0.0, min(1.0, s)), 4)


def _protected_levels(highs, lows):
    return {
        "protected_high": highs[-1] if highs else None,
        "protected_low": lows[-1] if lows else None,
    }


def _reason_codes(edef, idef, bos, internal_bos, failure, slope, conflicts, eh, el, ih, il):
    reasons = []
    if not bos.get("confirmed"):
        reasons.append("NO_CONFIRMED_EXTERNAL_BOS")
    if internal_bos.get("confirmed") and not bos.get("confirmed"):
        reasons.append("INTERNAL_BREAK_ONLY")
    if failure.get("confirmed"):
        reasons.append("FAILED_BREAK_DETECTED")
    if bos.get("event") == "CONFIRMED_CHOCH":
        reasons.append("CHANGE_OF_CHARACTER_DETECTED")
    if bos.get("event") == "CONFLICTING_BREAKS":
        reasons.append("CONFLICTING_EXTERNAL_BREAKS")
    if edef == MIXED or idef == MIXED:
        reasons.append("STRUCTURE_CONFLICT")
    if edef in {UP, DOWN} and idef not in {edef, NEUTRAL}:
        reasons.append("INTERNAL_EXTERNAL_DISAGREEMENT")
    if not eh or not el:
        reasons.append("LIMITED_EXTERNAL_SWINGS")
    if not ih or not il:
        reasons.append("LIMITED_INTERNAL_SWINGS")
    if slope in {UP, DOWN} and edef not in {slope, NEUTRAL}:
        reasons.append("SLOPE_NOT_STRUCTURAL_AUTHORITY")
    return list(dict.fromkeys(reasons + conflicts))


def _swing_map(highs, lows, limit=8):
    return {
        "highs": highs[-limit:],
        "lows": lows[-limit:],
        "external_highs": highs[-limit:],
        "external_lows": lows[-limit:],
    }


def analyze_e3(bars):
    clean, data_reasons = _clean_bars(bars)
    base = {
        "architecture": ARCHITECTURE,
        "reasoning_role": "MARKET_STRUCTURE_ANALYST",
        "question": QUESTION,
        "decision": None,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "gate": None,
        "sub_engines_active": False,
        "sub_engines_status": "PAUSED",
        "specialists_active": False,
        "specialists_status": "PAUSED",
        "upstream_direction_used": False,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
        "score_used": False,
    }
    if len(clean) < MIN_CANDLES:
        return {
            **base,
            "analysis_status": "INSUFFICIENT_DATA",
            "finding": "STRUCTURE_INSUFFICIENT_DATA",
            "structure": "UNKNOWN",
            "structure_state": "INSUFFICIENT_DATA",
            "direction": NEUTRAL,
            "directional_bias": NEUTRAL,
            "structural_bias": NEUTRAL,
            "swing_map": {"highs": [], "lows": []},
            "internal_structure": {},
            "external_structure": {},
            "bos": {"event": "NO_BOS", "direction": NEUTRAL, "confirmed": False},
            "BOS": "NONE",
            "BOS_type": "NONE",
            "structural_failure": "NONE",
            "failure_type": "NONE",
            "strength": 0.0,
            "structure_strength": 0.0,
            "confidence": 0.0,
            "evidence": [f"closed_candles={len(clean)}"],
            "observations": [f"closed_candles={len(clean)}"],
            "conflicts": [],
            "reason_codes": ["E3_INSUFFICIENT_DATA", *data_reasons[:4]],
            "reasons": ["E3_INSUFFICIENT_DATA", *data_reasons[:4]],
            "reasoning_trace": {"closed_candles": len(clean), "status": "INSUFFICIENT_DATA"},
        }

    atr = _atr(clean)
    ih = _label(_compress(_pivots(clean, "high", INTERNAL_RADIUS), atr, "high"), "HIGH", atr)
    il = _label(_compress(_pivots(clean, "low", INTERNAL_RADIUS), atr, "low"), "LOW", atr)
    eh = _label(_compress(_pivots(clean, "high", EXTERNAL_RADIUS), atr, "high"), "HIGH", atr)
    el = _label(_compress(_pivots(clean, "low", EXTERNAL_RADIUS), atr, "low"), "LOW", atr)

    idef = _structure_direction(ih, il)
    edef = _structure_direction(eh, el)
    internal_state, internal_counts = _structure_counts(ih, il)
    external_state, external_counts = _structure_counts(eh, el)
    slope, slope_q = _slope_direction(clean)

    # E3's structural authority is the confirmed swing map, never EMA/slope.
    external_bos = _bos(clean, eh, el, atr, edef, "EXTERNAL")
    internal_bos = _bos(clean, ih, il, atr, idef, "INTERNAL")
    failure = _sweep_failure(clean, eh, el)
    protected = _protected_levels(eh, el)

    conflicts = []
    if edef in {UP, DOWN} and idef in {UP, DOWN} and edef != idef:
        conflicts.append("INTERNAL_EXTERNAL_DIVERGENCE")
    if external_state != edef and external_state in {UP, DOWN}:
        conflicts.append("EXTERNAL_COUNT_STATE_DISAGREEMENT")
    if internal_state != idef and internal_state in {UP, DOWN}:
        conflicts.append("INTERNAL_COUNT_STATE_DISAGREEMENT")

    if failure.get("confirmed"):
        direction = failure["direction"]
        state = "STRUCTURE_FAILURE"
        finding = "FAILED_BREAK"
    elif external_bos.get("confirmed"):
        direction = external_bos["direction"]
        if external_bos["event"] == "CONFIRMED_CHOCH":
            state = "CHANGE_OF_CHARACTER"
            finding = "BULLISH_CHOCH" if direction == UP else "BEARISH_CHOCH"
        else:
            state = "BREAKOUT_CONFIRMED"
            finding = "BULLISH_BOS" if direction == UP else "BEARISH_BOS"
    elif edef in {UP, DOWN}:
        direction = edef
        if idef == edef:
            state = "CONTINUATION"
            finding = "BULLISH_STRUCTURE" if direction == UP else "BEARISH_STRUCTURE"
        elif idef == MIXED:
            state = "INTERNAL_CONFLICT"
            finding = "BULLISH_EXTERNAL_MIXED_INTERNAL" if direction == UP else "BEARISH_EXTERNAL_MIXED_INTERNAL"
        else:
            state = "INTERNAL_COUNTER_MOVE"
            finding = "BULLISH_EXTERNAL_COUNTERMOVE" if direction == UP else "BEARISH_EXTERNAL_COUNTERMOVE"
    elif idef in {UP, DOWN}:
        direction = idef
        state = "DEVELOPING_STRUCTURE"
        finding = "BULLISH_DEVELOPING_STRUCTURE" if direction == UP else "BEARISH_DEVELOPING_STRUCTURE"
    elif idef == MIXED or edef == MIXED:
        direction = MIXED
        state = "TRANSITION"
        finding = "MIXED_STRUCTURE"
    else:
        direction = MIXED if slope in {UP, DOWN} else NEUTRAL
        state = "DIRECTIONAL_CONTEXT_UNCONFIRMED" if slope in {UP, DOWN} else "RANGE_OR_UNCLEAR"
        finding = "DIRECTIONAL_CONTEXT_UNCONFIRMED" if slope in {UP, DOWN} else "NO_CONFIRMED_STRUCTURE_EVENT"

    # A slope may explain momentum but can never upgrade MIXED/NEUTRAL into a
    # structural trend. This is deliberately explicit in the trace.
    if slope in {UP, DOWN} and edef not in {slope, NEUTRAL}:
        conflicts.append("SLOPE_NOT_STRUCTURAL_AUTHORITY")

    reasons = _reason_codes(edef, idef, external_bos, internal_bos, failure, slope, list(dict.fromkeys(conflicts)), eh, el, ih, il)
    swing_count = len(ih) + len(il) + len(eh) + len(el)
    strength = _strength(edef, idef, external_bos, failure, swing_count, reasons)
    confidence = round(min(1.0, 0.28 + strength * 0.58 + (0.06 if edef == idef and edef in {UP, DOWN} else 0.0)), 4)

    structural_bias = direction if direction in {UP, DOWN} else NEUTRAL
    recent_high = max(b["high"] for b in clean[-30:])
    recent_low = min(b["low"] for b in clean[-30:])
    prior_window = clean[-60:-30] if len(clean) >= 60 else clean[:-30]
    prior_high = max((b["high"] for b in prior_window), default=recent_high)
    prior_low = min((b["low"] for b in prior_window), default=recent_low)

    observations = [
        f"closed_candles={len(clean)}",
        f"atr14={atr:.8f}",
        f"external_structure={edef}",
        f"internal_structure={idef}",
        f"external_state={external_state}",
        f"internal_state={internal_state}",
        f"slope_context={slope}",
        f"slope_quality={slope_q:.4f}",
        f"external_bos={external_bos['event']}",
        f"internal_bos={internal_bos['event']}",
        f"failure={failure['event']}",
        f"internal_swing_count={len(ih) + len(il)}",
        f"external_swing_count={len(eh) + len(el)}",
        f"structure_strength={strength:.4f}",
    ]
    if external_bos.get("confirmed"):
        observations.extend([
            f"bos_level={external_bos['level']}",
            f"bos_break_distance_atr={external_bos['break_distance_atr']}",
            f"bos_break_body_atr={external_bos['break_body_atr']}",
            f"bos_displacement_ok={external_bos['displacement_ok']}",
        ])
    if protected["protected_high"]:
        observations.append(f"protected_high={protected['protected_high']['price']}")
    if protected["protected_low"]:
        observations.append(f"protected_low={protected['protected_low']['price']}")

    reasoning_trace = {
        "closed_candles": len(clean),
        "atr_period": 14,
        "atr_normalization": True,
        "internal_pivot_window": INTERNAL_RADIUS,
        "external_pivot_window": EXTERNAL_RADIUS,
        "pivot_prominence_atr": PROMINENCE_ATR,
        "bos_close_distance_atr": BOS_DISTANCE_ATR,
        "bos_body_atr": BOS_BODY_ATR,
        "wick_only_break_is_bos": False,
        "external_structure_is_authority": True,
        "slope_is_structural_authority": False,
        "internal_structure": idef,
        "external_structure": edef,
        "internal_bos": internal_bos,
        "external_bos": external_bos,
        "failure": failure,
        "protected_levels": protected,
        "conflicts": list(dict.fromkeys(conflicts)),
        "upstream_data_consumed": False,
        "decision_authority": "E9_ONLY",
    }

    return {
        **base,
        "analysis_status": "COMPLETE",
        "finding": finding,
        "structure": direction if direction in {UP, DOWN} else (MIXED if state == "TRANSITION" else "NEUTRAL"),
        "structure_state": state,
        "direction": direction,
        "directional_bias": structural_bias,
        "structural_bias": structural_bias,
        "internal_structure": {"state": idef, "counts": internal_counts, "labels": ih[-8:] + il[-8:]},
        "external_structure": {"state": edef, "counts": external_counts, "labels": eh[-8:] + el[-8:]},
        "swing_map": _swing_map(eh + ih, el + il),
        "HH": external_counts["HH"],
        "HL": external_counts["HL"],
        "LH": external_counts["LH"],
        "LL": external_counts["LL"],
        "BOS": finding if external_bos.get("confirmed") else "NONE",
        "bos": external_bos,
        "BOS_type": external_bos.get("event", "NO_BOS"),
        "bos_type": external_bos.get("event", "NO_BOS"),
        "BOS_level": external_bos.get("level"),
        "bos_level": external_bos.get("level"),
        "BOS_candle_index": external_bos.get("break_candle_index"),
        "structural_failure": failure.get("event", "NO_FAILURE"),
        "failure_type": failure.get("event", "NO_FAILURE"),
        "failure_level": failure.get("level"),
        "strength": round(strength, 4),
        "structure_strength": round(strength, 4),
        "confidence": confidence,
        "recent_high": round(recent_high, 8),
        "recent_low": round(recent_low, 8),
        "prior_high": round(prior_high, 8),
        "prior_low": round(prior_low, 8),
        "atr": round(atr, 8),
        "protected_high": protected["protected_high"],
        "protected_low": protected["protected_low"],
        "conflicts": list(dict.fromkeys(conflicts)),
        "evidence": observations,
        "observations": observations,
        "reason_codes": reasons,
        "reasons": reasons,
        "reasoning_trace": reasoning_trace,
    }
