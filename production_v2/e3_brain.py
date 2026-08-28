from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V3"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 40
INTERNAL_RADIUS, EXTERNAL_RADIUS = 2, 5
PROMINENCE_ATR = 0.10
EQ_TOLERANCE_ATR = 0.08
SWEEP_MIN_ATR = 0.10
RECLAIM_MIN_ATR = 0.05


def _num(v: Any):
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _clean(bars):
    clean, rejected = [], []
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict):
            rejected.append(f"bar_{i}_not_mapping")
            continue
        vals = [_num(bar.get(k)) for k in ("open", "high", "low", "close")]
        if any(x is None for x in vals):
            rejected.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = vals
        if h < max(o, c) or l > min(o, c) or h < l:
            rejected.append(f"bar_{i}_ohlc_inconsistent")
            continue
        clean.append({"open": o, "high": h, "low": l, "close": c})
    return clean, rejected


def _tr(bars, i):
    if i <= 0:
        return bars[i]["high"] - bars[i]["low"]
    b, prev = bars[i], bars[i - 1]["close"]
    return max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev))


def _atr(bars, period=14, end=None):
    if not bars:
        return 0.0
    end = len(bars) - 1 if end is None else min(end, len(bars) - 1)
    if end < 1:
        return max(bars[0]["high"] - bars[0]["low"], 0.0)
    return mean(_tr(bars, i) for i in range(max(1, end - period + 1), end + 1))


def _raw_pivots(bars, side, radius):
    out = []
    for i in range(radius, len(bars) - radius):
        price = bars[i][side]
        left = [bars[j][side] for j in range(i - radius, i)]
        right = [bars[j][side] for j in range(i + 1, i + radius + 1)]
        prominence = PROMINENCE_ATR * max(_atr(bars, 14, i), 1e-12)
        if side == "high":
            valid = price >= max(left) and price > max(right)
            valid = valid and min(price - max(left), price - max(right)) >= prominence
        else:
            valid = price <= min(left) and price < min(right)
            valid = valid and min(min(left) - price, min(right) - price) >= prominence
        if valid:
            out.append((i, price, i + radius))
    return out


def _confirmed(raw, current_index):
    out = []
    for item in raw:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            continue
        try:
            idx, price, confirmation = int(item[0]), float(item[1]), int(item[2])
        except (TypeError, ValueError):
            continue
        if confirmation <= current_index:
            out.append({"index": idx, "price": round(price, 8), "confirmation_index": confirmation, "status": "CONFIRMED"})
    return out


def _dedupe(points, atr):
    out, tol = [], max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p["index"] - out[-1]["index"] >= 2:
            out.append(p)
        elif abs(p["price"] - out[-1]["price"]) > tol:
            out.append(p)
        elif p["confirmation_index"] >= out[-1]["confirmation_index"]:
            out[-1] = p
    return out


def _label(highs, lows, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    H, L, previous = [], [], None
    for p in highs:
        label = "SWING_HIGH" if previous is None else ("EQH" if abs(p["price"] - previous[1]) <= tol else "HH" if p["price"] > previous[1] else "LH")
        H.append({**p, "label": label})
        previous = (p["index"], p["price"])
    previous = None
    for p in lows:
        label = "SWING_LOW" if previous is None else ("EQL" if abs(p["price"] - previous[1]) <= tol else "HL" if p["price"] > previous[1] else "LL")
        L.append({**p, "label": label})
        previous = (p["index"], p["price"])
    return H, L


def _latest(points, labels):
    for p in reversed(points or []):
        if p.get("label") in labels:
            return p
    return None


def _semantic(highs, lows):
    events = sorted([p for p in highs + lows if p.get("label") in {"HH", "HL", "LH", "LL"}], key=lambda p: (p["index"], 0 if p["label"] in {"HH", "LH"} else 1))
    state, latest_high, latest_low = NEUTRAL, None, None
    transitions = []
    for event in events:
        if event["label"] in {"HH", "LH"}:
            latest_high = event
        else:
            latest_low = event
        if latest_high and latest_low:
            if latest_high["label"] == "HH" and latest_low["label"] == "HL":
                state = UP
            elif latest_high["label"] == "LH" and latest_low["label"] == "LL":
                state = DOWN
            else:
                state = MIXED
        transitions.append({"index": event["index"], "label": event["label"], "state_after": state})
    return {
        "state": state,
        "latest_directional_event": events[-1] if events else None,
        "latest_hh": _latest(highs, {"HH"}), "latest_hl": _latest(lows, {"HL"}),
        "latest_lh": _latest(highs, {"LH"}), "latest_ll": _latest(lows, {"LL"}),
        "bullish_pair": bool(latest_high and latest_low and latest_high["label"] == "HH" and latest_low["label"] == "HL"),
        "bearish_pair": bool(latest_high and latest_low and latest_high["label"] == "LH" and latest_low["label"] == "LL"),
        "structural_sequence": "→".join(x["label"] for x in events[-12:]),
        "transitions": transitions[-12:],
        "basis": "ORDERED_CONFIRMED_SWINGS",
        "counts_used_as_authority": False,
    }


def _protected(highs, lows, state):
    if state == UP:
        return {"protected_high": _latest(highs, {"HH"}), "protected_low": _latest(lows, {"HL"}), "logic": "HL_protects_bullish_structure"}
    if state == DOWN:
        return {"protected_high": _latest(highs, {"LH"}), "protected_low": _latest(lows, {"LL"}), "logic": "LH_protects_bearish_structure"}
    return {"protected_high": None, "protected_low": None, "logic": "NO_DIRECTIONAL_PROTECTED_PAIR"}


def _break_event(bars, highs, lows, atr, external, current):
    usable_h = [p for p in highs if p["confirmation_index"] <= current - 1]
    usable_l = [p for p in lows if p["confirmation_index"] <= current - 1]
    high, low, candidates = _latest(usable_h, {"HH", "LH"}), _latest(usable_l, {"HL", "LL"}), []
    if high and bars[current]["close"] > high["price"]:
        candidates.append((abs(bars[current]["close"] - high["price"]), {"event": "BOS_UP", "direction": UP, "level": high["price"], "structure_index": high["index"]}))
    if low and bars[current]["close"] < low["price"]:
        candidates.append((abs(bars[current]["close"] - low["price"]), {"event": "BOS_DOWN", "direction": DOWN, "level": low["price"], "structure_index": low["index"]}))
    if not candidates:
        return {"event": "NO_BREAK", "direction": NEUTRAL, "confirmed": False, "closed_candle_confirmed": True, "scope": "EXTERNAL"}
    _, event = max(candidates, key=lambda x: x[0])
    old = external["state"]
    choch = (old == DOWN and event["direction"] == UP) or (old == UP and event["direction"] == DOWN)
    return {**event, "event": "CHOCH" if choch else event["event"], "confirmed": True, "closed_candle_confirmed": True, "break_candle_index": current, "distance_atr": round(abs(bars[current]["close"] - event["level"]) / max(atr, 1e-12), 4), "scope": "EXTERNAL", "previous_structure": old}


def _failed_break(bars, highs, lows, current, atr):
    """Detect a break on the immediately preceding closed candle followed by a closed rejection now."""
    if current < 1:
        return {"event": "NO_FAILURE", "confirmed": False, "current": False}
    prev = current - 1
    candidates = []
    for points, direction, side in ((highs, UP, "high"), (lows, DOWN, "low")):
        for p in reversed(points):
            if p["confirmation_index"] > prev - 1 or p.get("label") not in {"HH", "LH", "HL", "LL", "EQH", "EQL"}:
                continue
            level = p["price"]
            if direction == UP and bars[prev]["close"] > level and bars[current]["close"] < level:
                candidates.append({"event": "FAILED_BOS", "direction": DOWN, "level": level, "break_candle_index": prev, "failure_candle_index": current, "current": True})
            elif direction == DOWN and bars[prev]["close"] < level and bars[current]["close"] > level:
                candidates.append({"event": "FAILED_BOS", "direction": UP, "level": level, "break_candle_index": prev, "failure_candle_index": current, "current": True})
            if candidates:
                break
    if not candidates:
        return {"event": "NO_FAILURE", "confirmed": False, "current": False}
    event = candidates[-1]
    event.update({"confirmed": True, "closed_candle_confirmed": True, "distance_atr": round(abs(bars[current]["close"] - event["level"]) / max(atr, 1e-12), 4)})
    return event


def _sweep_reclaim(bars, highs, lows, atr):
    if not bars or atr <= 0:
        return {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE", "current": False}
    current = len(bars) - 1
    found = []
    for pivot, direction, side in [(_latest(highs, {"HH", "LH", "EQH"}), DOWN, "high"), (_latest(lows, {"HL", "LL", "EQL"}), UP, "low")]:
        if not pivot or pivot["confirmation_index"] > current - 1:
            continue
        if side == "high":
            sweep = (bars[current]["high"] - pivot["price"]) / atr
            reclaimed = bars[current]["close"] < pivot["price"]
            reclaim_distance = (pivot["price"] - bars[current]["close"]) / atr
        else:
            sweep = (pivot["price"] - bars[current]["low"]) / atr
            reclaimed = bars[current]["close"] > pivot["price"]
            reclaim_distance = (bars[current]["close"] - pivot["price"]) / atr
        # A wick through a level is NOT a sweep until the closed candle reclaims the level.
        if sweep >= SWEEP_MIN_ATR and reclaimed and reclaim_distance >= RECLAIM_MIN_ATR:
            found.append((reclaim_distance, {"event": "SWEEP_RECLAIM", "direction": direction, "confirmed": True, "closed_candle_confirmed": True, "current": True, "level": pivot["price"], "swing_index": pivot["index"], "sweep_candle_index": current, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim_distance, 4), "liquidity_type": "EQUAL_HIGH" if pivot["label"] == "EQH" else "EQUAL_LOW" if pivot["label"] == "EQL" else "STRUCTURAL_SWING", "lifecycle": "RECLAIM"}))
    return max(found, key=lambda x: x[0])[1] if found else {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE", "current": False}


def _invalidation(bars, protected, state):
    close = bars[-1]["close"]
    ph, pl = protected.get("protected_high"), protected.get("protected_low")
    if state == UP and pl and close < pl["price"]:
        return {"event": "BULLISH_STRUCTURE_INVALIDATED", "invalidated": True, "direction": UP, "level": pl["price"], "basis": "CLOSED_CANDLE_BELOW_PROTECTED_LOW"}
    if state == DOWN and ph and close > ph["price"]:
        return {"event": "BEARISH_STRUCTURE_INVALIDATED", "invalidated": True, "direction": DOWN, "level": ph["price"], "basis": "CLOSED_CANDLE_ABOVE_PROTECTED_HIGH"}
    return {"event": "NO_INVALIDATION", "invalidated": False, "direction": state, "level": None, "basis": "PROTECTED_LEVEL_HOLDS" if state in {UP, DOWN} else "NO_DIRECTIONAL_STRUCTURE"}


def analyze_e3(bars):
    clean, rejected = _clean(bars)
    if len(clean) < MIN_CANDLES:
        return {"engine": "E3", "role": "MARKET_STRUCTURE_ANALYST", "architecture": ARCHITECTURE, "question": QUESTION, "status": "INSUFFICIENT_DATA", "finding": "INSUFFICIENT_DATA", "observations": [], "reasons": ["INSUFFICIENT_CANDLES"], "decision_authority": "E9_ONLY", "trade_decision": None, "data_quality": {"valid_bars": len(clean), "rejected": rejected}}

    current, atr = len(clean) - 1, _atr(clean)
    ext_h = _dedupe(_confirmed(_raw_pivots(clean, "high", EXTERNAL_RADIUS), current), atr)
    ext_l = _dedupe(_confirmed(_raw_pivots(clean, "low", EXTERNAL_RADIUS), current), atr)
    int_h = _dedupe(_confirmed(_raw_pivots(clean, "high", INTERNAL_RADIUS), current), atr)
    int_l = _dedupe(_confirmed(_raw_pivots(clean, "low", INTERNAL_RADIUS), current), atr)
    external_h, external_l = _label(ext_h, ext_l, atr)
    internal_h, internal_l = _label(int_h, int_l, atr)
    external, internal = _semantic(external_h, external_l), _semantic(internal_h, internal_l)
    protected = _protected(external_h, external_l, external["state"])
    bos_choch = _break_event(clean, external_h, external_l, atr, external, current)
    failed = _failed_break(clean, external_h, external_l, current, atr)
    liquidity = _sweep_reclaim(clean, external_h, external_l, atr)
    invalidation = _invalidation(clean, protected, external["state"])
    state = external["state"]

    if invalidation["invalidated"]:
        lifecycle_state, finding = "INVALIDATED", invalidation["event"]
    elif failed.get("confirmed"):
        lifecycle_state, finding = "FAILED_BREAK", "FAILED_BOS"
    elif bos_choch.get("event") == "CHOCH":
        lifecycle_state, finding = "CHOCH_CONFIRMED", "CHOCH"
    elif bos_choch.get("confirmed"):
        lifecycle_state, finding = "BOS_CONFIRMED", bos_choch["event"]
    elif liquidity.get("event") == "SWEEP_RECLAIM":
        lifecycle_state, finding = "SWEEP_RECLAIM", "SWEEP_RECLAIM"
    elif state == UP:
        lifecycle_state, finding = "STRUCTURE_ACTIVE", "BULLISH_STRUCTURE"
    elif state == DOWN:
        lifecycle_state, finding = "STRUCTURE_ACTIVE", "BEARISH_STRUCTURE"
    elif state == MIXED:
        lifecycle_state, finding = "STRUCTURE_TRANSITION", "STRUCTURE_TRANSITION"
    else:
        lifecycle_state, finding = "STRUCTURE_FORMING", "STRUCTURE_FORMING"

    observations = [
        f"external_state={state}", f"internal_state={internal['state']}",
        f"sequence={external['structural_sequence'] or 'NONE'}",
        f"protected_high={protected['protected_high']['price'] if protected['protected_high'] else 'NONE'}",
        f"protected_low={protected['protected_low']['price'] if protected['protected_low'] else 'NONE'}",
        f"bos={bos_choch.get('event')}", f"choch={'CONFIRMED' if bos_choch.get('event') == 'CHOCH' else 'NO'}",
        f"failed_break={failed.get('event')}", f"liquidity={liquidity.get('event')}", f"invalidation={invalidation.get('event')}",
    ]

    return {
        "engine": "E3", "role": "MARKET_STRUCTURE_ANALYST", "architecture": ARCHITECTURE, "question": QUESTION,
        "status": "OK", "finding": finding, "observations": observations,
        "reasons": ["CAUSAL_STRUCTURE_ANALYSIS", "CONFIRMED_PIVOTS_ONLY", "CLOSED_CANDLE_ONLY", "NO_LOOKAHEAD"],
        "decision_authority": "E9_ONLY", "trade_decision": None,
        "structure_state": state, "structure_direction": state if state in {UP, DOWN} else NEUTRAL,
        "internal_state": internal["state"], "external_state": external["state"],
        "hh": external["latest_hh"], "hl": external["latest_hl"], "lh": external["latest_lh"], "ll": external["latest_ll"],
        "protected_high": protected["protected_high"], "protected_low": protected["protected_low"],
        "bos": bos_choch if bos_choch.get("event", "").startswith("BOS") else {"event": "NO_BOS", "confirmed": False},
        "choch": bos_choch if bos_choch.get("event") == "CHOCH" else {"event": "NO_CHOCH", "confirmed": False},
        "failed_break": failed,
        "liquidity_sweep": liquidity,
        "reclaim": liquidity if liquidity.get("event") == "SWEEP_RECLAIM" else {"event": "NO_RECLAIM", "confirmed": False},
        "invalidation": invalidation,
        "structure_lifecycle": {"state": lifecycle_state, "current_structure": state, "last_confirmed_pivot_index": max((p["confirmation_index"] for p in external_h + external_l), default=None), "as_of_closed_candle": current},
        "external_structure": external, "internal_structure": internal, "protected_structure": protected,
        "bos_choch": bos_choch, "liquidity": liquidity,
        "causal": {"lookahead_allowed": False, "future_data_used": False, "current_candle_index": current, "confirmation_cutoff": current, "pivot_confirmation_required": True, "break_requires_closed_candle": True},
        "data_quality": {"valid_bars": len(clean), "rejected": rejected, "atr": round(atr, 8)},
        "contract": {"return_type": "dict", "stable_semantic_fields": True, "tuple_normalized": True, "decision_owner": "E9"},
    }
