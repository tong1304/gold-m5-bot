from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_PROFESSIONAL_MARKET_STRUCTURE_CAUSAL_V6"
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
        return max(bars[i]["high"] - bars[i]["low"], 0.0)
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
    return [
        {"index": int(i), "price": round(float(p), 8), "confirmation_index": int(c), "status": "CONFIRMED"}
        for i, p, c in raw if int(c) <= current_index
    ]


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
    H, L = [], []
    previous = None
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
    events = sorted(
        [p for p in highs + lows if p.get("label") in {"HH", "HL", "LH", "LL"}],
        key=lambda p: (p["index"], 0 if p["label"] in {"HH", "LH"} else 1),
    )
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
        "structural_sequence": "→".join(x["label"] for x in events[-12:]),
        "transitions": transitions[-12:],
        "basis": "ORDERED_CONFIRMED_SWINGS",
        "counts_used_as_authority": False,
    }


def _protected(highs, lows):
    """Return causal protected levels, not merely the latest swing of each type.

    A bullish protected low is the latest confirmed HL that existed before the
    impulse HH which established the current bullish leg.  Bearish protection is
    symmetric.  This prevents an unrelated later pivot from silently replacing
    the level that actually carries structural invalidation authority.
    """
    hh = _latest(highs, {"HH"})
    lh = _latest(highs, {"LH"})
    ll = _latest(lows, {"LL"})

    bullish_low = None
    bullish_anchor = None
    if hh:
        candidates = [
            p for p in lows
            if p.get("label") == "HL"
            and p["index"] < hh["index"]
            and p["confirmation_index"] <= hh["confirmation_index"]
        ]
        if candidates:
            bullish_low = candidates[-1]
            bullish_anchor = hh

    bearish_high = None
    bearish_anchor = None
    if ll:
        candidates = [
            p for p in highs
            if p.get("label") == "LH"
            and p["index"] < ll["index"]
            and p["confirmation_index"] <= ll["confirmation_index"]
        ]
        if candidates:
            bearish_high = candidates[-1]
            bearish_anchor = ll

    return {
        "protected_high": bearish_high,
        "protected_low": bullish_low,
        "bullish_anchor": bullish_anchor,
        "bearish_anchor": bearish_anchor,
        "bullish_basis": "HL_PROTECTED_BY_CONFIRMED_HH" if bullish_low else "NONE",
        "bearish_basis": "LH_PROTECTED_BY_CONFIRMED_LL" if bearish_high else "NONE",
        "authority_rule": "CAUSAL_ANCHOR_REQUIRED",
    }


def _crossed_up(bars, current, level):
    return current > 0 and bars[current - 1]["close"] <= level < bars[current]["close"]


def _crossed_down(bars, current, level):
    return current > 0 and bars[current - 1]["close"] >= level > bars[current]["close"]


def _break_event(bars, protected, external, current, atr):
    candidates = []
    ph, pl = protected.get("protected_high"), protected.get("protected_low")
    if ph and _crossed_up(bars, current, ph["price"]):
        candidates.append((abs(bars[current]["close"] - ph["price"]), {"event": "BOS_UP", "direction": UP, "level": ph["price"], "structure_index": ph["index"], "broken_role": "PROTECTED_HIGH"}))
    if pl and _crossed_down(bars, current, pl["price"]):
        candidates.append((abs(bars[current]["close"] - pl["price"]), {"event": "BOS_DOWN", "direction": DOWN, "level": pl["price"], "structure_index": pl["index"], "broken_role": "PROTECTED_LOW"}))
    if not candidates:
        return {"event": "NO_BREAK", "direction": NEUTRAL, "confirmed": False, "closed_candle_confirmed": True, "scope": "EXTERNAL"}
    _, event = max(candidates, key=lambda x: x[0])
    old = external["state"]
    choch = (old == DOWN and event["direction"] == UP) or (old == UP and event["direction"] == DOWN)
    return {
        **event,
        "event": "CHOCH" if choch else event["event"],
        "confirmed": True,
        "closed_candle_confirmed": True,
        "break_candle_index": current,
        "distance_atr": round(abs(bars[current]["close"] - event["level"]) / max(atr, 1e-12), 4),
        "scope": "EXTERNAL",
        "previous_structure": old,
    }


def _failed_break(bars, highs, lows, current, atr):
    if current < 1:
        return {"event": "NO_FAILURE", "confirmed": False, "current": False}
    prev = current - 1
    candidates = []
    for points, direction in ((highs, UP), (lows, DOWN)):
        for p in reversed(points):
            if p["confirmation_index"] > prev or p.get("label") not in {"HH", "HL", "LH", "LL", "EQH", "EQL"}:
                continue
            level = p["price"]
            if direction == UP and bars[prev]["close"] > level and bars[current]["close"] < level:
                candidates.append({"event": "FAILED_BOS", "direction": DOWN, "level": level, "break_candle_index": prev, "failure_candle_index": current})
            elif direction == DOWN and bars[prev]["close"] < level and bars[current]["close"] > level:
                candidates.append({"event": "FAILED_BOS", "direction": UP, "level": level, "break_candle_index": prev, "failure_candle_index": current})
            if candidates:
                break
    if not candidates:
        return {"event": "NO_FAILURE", "confirmed": False, "current": False}
    event = candidates[-1]
    event.update({"confirmed": True, "closed_candle_confirmed": True, "current": True, "distance_atr": round(abs(bars[current]["close"] - event["level"]) / max(atr, 1e-12), 4)})
    return event


def _sweep_reclaim(bars, highs, lows, atr):
    """Detect a sweep/reclaim on the current closed candle using the nearest
    causally relevant confirmed liquidity pool on each side, rather than only
    the latest pivot. The event is valid only when the same candle both sweeps
    and closes back through the level by the minimum reclaim distance.
    """
    if not bars or atr <= 0:
        return {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE", "current": False}
    current = len(bars) - 1
    found = []

    high_candidates = [p for p in highs if p["confirmation_index"] <= current - 1 and p.get("label") in {"HH", "LH", "EQH"}]
    low_candidates = [p for p in lows if p["confirmation_index"] <= current - 1 and p.get("label") in {"HL", "LL", "EQL"}]

    # Prefer the nearest level actually touched by the current candle.  This
    # avoids letting a distant old swing outrank a fresh, relevant liquidity pool.
    for pivot in high_candidates:
        sweep = (bars[current]["high"] - pivot["price"]) / atr
        reclaimed = bars[current]["close"] < pivot["price"]
        reclaim_distance = (pivot["price"] - bars[current]["close"]) / atr
        if sweep >= SWEEP_MIN_ATR and reclaimed and reclaim_distance >= RECLAIM_MIN_ATR:
            proximity = abs(bars[current]["close"] - pivot["price"]) / atr
            quality = (reclaim_distance, -proximity, pivot["index"])
            found.append((quality, {"event": "SWEEP_RECLAIM", "direction": DOWN, "confirmed": True, "closed_candle_confirmed": True, "current": True, "level": pivot["price"], "swing_index": pivot["index"], "sweep_candle_index": current, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim_distance, 4), "liquidity_type": "EQUAL_HIGH" if pivot["label"] == "EQH" else "STRUCTURAL_SWING", "lifecycle": "RECLAIM"}))

    for pivot in low_candidates:
        sweep = (pivot["price"] - bars[current]["low"]) / atr
        reclaimed = bars[current]["close"] > pivot["price"]
        reclaim_distance = (bars[current]["close"] - pivot["price"]) / atr
        if sweep >= SWEEP_MIN_ATR and reclaimed and reclaim_distance >= RECLAIM_MIN_ATR:
            proximity = abs(bars[current]["close"] - pivot["price"]) / atr
            quality = (reclaim_distance, -proximity, pivot["index"])
            found.append((quality, {"event": "SWEEP_RECLAIM", "direction": UP, "confirmed": True, "closed_candle_confirmed": True, "current": True, "level": pivot["price"], "swing_index": pivot["index"], "sweep_candle_index": current, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(reclaim_distance, 4), "liquidity_type": "EQUAL_LOW" if pivot["label"] == "EQL" else "STRUCTURAL_SWING", "lifecycle": "RECLAIM"}))

    return max(found, key=lambda x: x[0])[1] if found else {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE", "current": False}


def _invalidation(bars, protected, state):
    if len(bars) < 2:
        return {"event": "NO_INVALIDATION", "invalidated": False, "direction": state, "level": None, "basis": "INSUFFICIENT_CLOSED_BARS"}
    close = bars[-1]["close"]
    previous_close = bars[-2]["close"]
    ph, pl = protected.get("protected_high"), protected.get("protected_low")
    if state == UP and pl and previous_close >= pl["price"] and close < pl["price"]:
        return {"event": "BULLISH_STRUCTURE_INVALIDATED", "invalidated": True, "direction": UP, "level": pl["price"], "basis": "CLOSED_CANDLE_CROSSED_BELOW_PROTECTED_LOW"}
    if state == DOWN and ph and previous_close <= ph["price"] and close > ph["price"]:
        return {"event": "BEARISH_STRUCTURE_INVALIDATED", "invalidated": True, "direction": DOWN, "level": ph["price"], "basis": "CLOSED_CANDLE_CROSSED_ABOVE_PROTECTED_HIGH"}
    return {"event": "NO_INVALIDATION", "invalidated": False, "direction": state, "level": None, "basis": "PROTECTED_LEVEL_HOLDS" if state in {UP, DOWN} else "NO_DIRECTIONAL_STRUCTURE"}


def _lifecycle(external, internal, bos, failed, sweep, invalidation):
    if invalidation.get("invalidated"):
        return "INVALIDATED"
    if sweep.get("confirmed"):
        return "SWEEP_RECLAIM"
    if failed.get("confirmed"):
        return "FAILED_BREAK"
    if bos.get("confirmed"):
        return "CHOCH" if bos.get("event") == "CHOCH" else bos.get("event")
    if external["state"] in {UP, DOWN}:
        return "ESTABLISHED"
    if internal["state"] in {UP, DOWN}:
        return "FORMING"
    return "TRANSITION"


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
    protected = _protected(external_h, external_l)
    bos = _break_event(clean, protected, external, current, atr)
    failed = _failed_break(clean, external_h, external_l, current, atr)
    sweep = _sweep_reclaim(clean, external_h, external_l, atr)
    invalidation = _invalidation(clean, protected, external["state"])
    lifecycle = _lifecycle(external, internal, bos, failed, sweep, invalidation)

    if invalidation["invalidated"]:
        finding = invalidation["event"]
    elif sweep["confirmed"]:
        finding = "SWEEP_RECLAIM"
    elif failed["confirmed"]:
        finding = "FAILED_BOS"
    elif bos["confirmed"]:
        finding = bos["event"]
    elif external["state"] == UP:
        finding = "BULLISH_STRUCTURE"
    elif external["state"] == DOWN:
        finding = "BEARISH_STRUCTURE"
    elif internal["state"] in {UP, DOWN}:
        finding = "STRUCTURE_FORMING"
    else:
        finding = "STRUCTURE_TRANSITION"

    direction = bos.get("direction") if bos.get("confirmed") else external["state"]
    observations = [
        f"external_state={external['state']}", f"internal_state={internal['state']}",
        f"sequence={external['structural_sequence'] or 'NONE'}",
        f"protected_high={protected['protected_high']['price'] if protected['protected_high'] else 'NONE'}",
        f"protected_low={protected['protected_low']['price'] if protected['protected_low'] else 'NONE'}",
        f"bos={bos['event']}", f"choch={'CHOCH' if bos.get('event') == 'CHOCH' else 'NO'}",
        f"failed_break={failed['event']}", f"liquidity={sweep['event']}",
        f"lifecycle={lifecycle}", f"invalidation={invalidation['event']}",
    ]
    reasons = ["CAUSAL_STRUCTURE_ANALYSIS", "CLOSED_CANDLE_ONLY", "CONFIRMED_PIVOTS_ONLY", "NO_LOOKAHEAD", "PROTECTED_LEVEL_CAUSALITY", "STRUCTURE_LIFECYCLE_EXPLICIT", "EVENT_MUST_OCCUR_ON_CURRENT_CLOSED_CANDLE"]
    if bos.get("confirmed"):
        reasons.append("BREAK_REQUIRES_PROTECTED_LEVEL_CROSS")
    if sweep.get("confirmed"):
        reasons.append("SWEEP_REQUIRES_CLOSED_RECLAIM")
    if invalidation.get("invalidated"):
        reasons.append(invalidation["basis"])

    return {
        "engine": "E3", "role": "MARKET_STRUCTURE_ANALYST", "architecture": ARCHITECTURE,
        "question": QUESTION, "status": "OK", "finding": finding,
        "direction": direction, "observations": observations, "reasons": reasons,
        "decision_authority": "E9_ONLY", "trade_decision": None,
        "data_quality": {"valid_bars": len(clean), "rejected": rejected, "current_index": current},
        "structure_state": external["state"], "internal_state": internal["state"],
        "external_structure": external, "internal_structure": internal,
        "protected_structure": protected, "bos": bos, "choch": bos if bos.get("event") == "CHOCH" else {"event": "NO_CHOCH", "confirmed": False},
        "failed_break": failed, "liquidity": sweep, "invalidation": invalidation,
        "structure_lifecycle": lifecycle,
        "pivots": {"external_highs": external_h[-12:], "external_lows": external_l[-12:], "internal_highs": internal_h[-12:], "internal_lows": internal_l[-12:]},
    }
