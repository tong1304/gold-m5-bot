from __future__ import annotations

from statistics import mean
from typing import Any

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_SINGLE_PROFESSIONAL_BRAIN_V61_CAUSAL_CONTRACT"
UP, DOWN, NEUTRAL, MIXED = "UP", "DOWN", "NEUTRAL", "MIXED"
MIN_CANDLES = 40
IR, ER = 2, 5
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
    out, reasons = [], []
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict):
            reasons.append(f"bar_{i}_not_mapping")
            continue
        vals = [_num(bar.get(k)) for k in ("open", "high", "low", "close")]
        if any(x is None for x in vals):
            reasons.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = vals
        if h < max(o, c) or l > min(o, c) or h < l:
            reasons.append(f"bar_{i}_ohlc_inconsistent")
            continue
        out.append({"open": o, "high": h, "low": l, "close": c})
    return out, reasons


def _tr(b, i):
    if i <= 0:
        return b[i]["high"] - b[i]["low"] if b else 0.0
    x, prev = b[i], b[i - 1]["close"]
    return max(x["high"] - x["low"], abs(x["high"] - prev), abs(x["low"] - prev))


def _atr(b, p=14, end=None):
    if not b:
        return 0.0
    end = len(b) - 1 if end is None else min(end, len(b) - 1)
    if end < 0:
        return 0.0
    start = max(1, end - p + 1)
    vals = [_tr(b, i) for i in range(start, end + 1)]
    return mean(vals) if vals else 0.0


def _pivots(b, side, radius):
    out = []
    for i in range(radius, len(b) - radius):
        x = b[i][side]
        left = [b[j][side] for j in range(i - radius, i)]
        right = [b[j][side] for j in range(i + 1, i + radius + 1)]
        prom = PROMINENCE_ATR * max(_atr(b, 14, i), 1e-12)
        if side == "high":
            ok = x >= max(left) and x > max(right) and min(x - max(left), x - max(right)) >= prom
        else:
            ok = x <= min(left) and x < min(right) and min(min(left) - x, min(right) - x) >= prom
        if ok:
            out.append((i, x, i + radius))
    return out


def _pivot_records(raw, current_index):
    out = []
    for item in raw or []:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            continue
        idx, price, confirmation_index = item
        try:
            idx, price, confirmation_index = int(idx), float(price), int(confirmation_index)
        except (TypeError, ValueError):
            continue
        if confirmation_index <= current_index:
            out.append({"index": idx, "price": round(price, 8), "confirmation_index": confirmation_index, "status": "CONFIRMED"})
    return out


def _compress(points, atr, spacing=2):
    out = []
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    for p in points:
        if not out or p["index"] - out[-1]["index"] >= spacing:
            out.append(p)
            continue
        if abs(p["price"] - out[-1]["price"]) <= tol and p["confirmation_index"] >= out[-1]["confirmation_index"]:
            out[-1] = p
    return out


def _label(highs, lows, atr):
    tol = max(atr * EQ_TOLERANCE_ATR, 1e-12)
    labeled_h, labeled_l = [], []
    prev = None
    for p in highs:
        label = "SWING_HIGH" if prev is None else "EQH" if abs(p["price"] - prev[1]) <= tol else "HH" if p["price"] > prev[1] else "LH"
        labeled_h.append({**p, "label": label})
        prev = (p["index"], p["price"])
    prev = None
    for p in lows:
        label = "SWING_LOW" if prev is None else "EQL" if abs(p["price"] - prev[1]) <= tol else "HL" if p["price"] > prev[1] else "LL"
        labeled_l.append({**p, "label": label})
        prev = (p["index"], p["price"])
    return labeled_h, labeled_l


def _latest(xs, labels):
    for x in reversed(xs or []):
        if x.get("label") in labels:
            return x
    return None


def _semantic_structure_state(highs, lows):
    events = sorted([x for x in highs + lows if x.get("label") in {"HH", "HL", "LH", "LL"}], key=lambda x: (x["index"], 0 if x["label"] in {"HH", "LH"} else 1))
    state = NEUTRAL
    last_high = last_low = None
    transitions = []
    for x in events:
        if x["label"] in {"HH", "LH"}:
            last_high = x
        else:
            last_low = x
        if last_high and last_low:
            if last_high["label"] == "HH" and last_low["label"] == "HL":
                state = UP
            elif last_high["label"] == "LH" and last_low["label"] == "LL":
                state = DOWN
            else:
                state = MIXED
        transitions.append({"index": x["index"], "label": x["label"], "state_after": state})
    return {
        "state": state,
        "basis": "ORDERED_CAUSAL_SWING_RELATIONSHIPS",
        "counts_used_as_authority": False,
        "latest_directional_event": events[-1] if events else None,
        "latest_hh": _latest(highs, {"HH"}), "latest_hl": _latest(lows, {"HL"}),
        "latest_lh": _latest(highs, {"LH"}), "latest_ll": _latest(lows, {"LL"}),
        "bullish_pair": bool(last_high and last_low and last_high["label"] == "HH" and last_low["label"] == "HL"),
        "bearish_pair": bool(last_high and last_low and last_high["label"] == "LH" and last_low["label"] == "LL"),
        "structural_sequence": "→".join(x["label"] for x in events[-12:]),
        "transitions": transitions[-12:],
        "semantic_rule": "ORDERED_SWINGS_ONLY;CONFIRMED_PIVOTS_ONLY;COUNTS_DESCRIPTIVE_ONLY;NEWER_CONFIRMED_LEG_HAS_AUTHORITY",
    }


def _protected_structure(highs, lows, state):
    if state == UP:
        return {"protected_high": _latest(highs, {"HH"}), "protected_low": _latest(lows, {"HL"}), "logic": "latest_confirmed_HL_protects_bullish_structure"}
    if state == DOWN:
        return {"protected_high": _latest(highs, {"LH"}), "protected_low": _latest(lows, {"LL"}), "logic": "latest_confirmed_LH_protects_bearish_structure"}
    return {"protected_high": None, "protected_low": None, "logic": "NO_CLEAR_DIRECTIONAL_PROTECTED_PAIR"}


def _current_break(bars, highs, lows, atr, structure, scope="EXTERNAL", idx=None):
    if not bars:
        return {"event": "NO_BREAK", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    i = len(bars) - 1 if idx is None else idx
    if i < 0 or i >= len(bars):
        return {"event": "NO_BREAK", "direction": NEUTRAL, "confirmed": False, "scope": scope}
    candidates = []
    high = _latest([x for x in highs if x["confirmation_index"] <= i - 1], {"HH", "LH"})
    low = _latest([x for x in lows if x["confirmation_index"] <= i - 1], {"HL", "LL"})
    if high and bars[i]["close"] > high["price"]:
        candidates.append({"event": "BOS_UP", "direction": UP, "level": high["price"], "structure_index": high["index"]})
    if low and bars[i]["close"] < low["price"]:
        candidates.append({"event": "BOS_DOWN", "direction": DOWN, "level": low["price"], "structure_index": low["index"]})
    if not candidates:
        return {"event": "NO_BREAK", "direction": NEUTRAL, "confirmed": False, "closed_candle_confirmed": True, "scope": scope}
    x = max(candidates, key=lambda z: abs(bars[i]["close"] - z["level"]))
    prior = structure.get("state", NEUTRAL)
    choch = (prior == DOWN and x["direction"] == UP) or (prior == UP and x["direction"] == DOWN)
    return {**x, "event": "CHOCH" if choch else x["event"], "confirmed": True, "closed_candle_confirmed": True, "break_candle_index": i, "distance_atr": round(abs(bars[i]["close"] - x["level"]) / max(atr, 1e-12), 4), "scope": scope}


def _failure_from_break(break_event, bars, atr):
    if not break_event.get("confirmed"):
        return {"event": "NO_FAILURE", "confirmed": False, "current": False}
    i, level, direction = break_event["break_candle_index"], break_event["level"], break_event["direction"]
    failed = i + 1 < len(bars) and ((direction == UP and bars[i + 1]["close"] < level) or (direction == DOWN and bars[i + 1]["close"] > level))
    return {"event": "FAILED_BOS" if failed else "NO_FAILURE", "direction": DOWN if direction == UP else UP, "confirmed": bool(failed), "current": bool(failed and i + 1 == len(bars) - 1), "closed_candle_confirmed": True, "level": level, "break_candle_index": i, "failure_candle_index": i + 1 if failed else None, "scope": break_event.get("scope", "EXTERNAL"), "distance_atr": round(abs(bars[i + 1]["close"] - level) / max(atr, 1e-12), 4) if failed else 0.0}


def _sweep_reclaim(bars, highs, lows, atr):
    if not bars or atr <= 0:
        return {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE", "current": False}
    i = len(bars) - 1
    found = []
    for p, direction, side in [(_latest(highs, {"HH", "LH", "EQH"}), DOWN, "high"), (_latest(lows, {"HL", "LL", "EQL"}), UP, "low")]:
        if not p or p["confirmation_index"] > i - 1:
            continue
        sweep = (bars[i]["high"] - p["price"]) / atr if side == "high" else (p["price"] - bars[i]["low"]) / atr
        reclaim = (p["price"] - bars[i]["close"]) / atr if side == "high" else (bars[i]["close"] - p["price"]) / atr
        if sweep >= SWEEP_MIN_ATR:
            stage = "RECLAIM" if reclaim >= RECLAIM_MIN_ATR else "SWEEP"
            found.append((max(0.0, reclaim), {"event": "SWEEP_RECLAIM" if stage == "RECLAIM" else "SWEEP", "direction": direction, "confirmed": True, "closed_candle_confirmed": True, "current": True, "level": p["price"], "swing_index": p["index"], "sweep_candle_index": i, "sweep_distance_atr": round(sweep, 4), "reclaim_distance_atr": round(max(0.0, reclaim), 4), "scope": "EXTERNAL", "liquidity_type": "EQUAL_HIGH" if p["label"] == "EQH" else "EQUAL_LOW" if p["label"] == "EQL" else "STRUCTURAL_SWING", "lifecycle": stage}))
    return max(found, key=lambda x: x[0])[1] if found else {"event": "NO_SWEEP_RECLAIM", "direction": NEUTRAL, "confirmed": False, "lifecycle": "NONE", "current": False}


def analyze_e3(bars):
    """Professional causal market-structure brain. No trade decision."""
    clean, reasons = _clean(bars)
    if len(clean) < MIN_CANDLES:
        return {"engine": "E3", "architecture": ARCHITECTURE, "question": QUESTION, "status": "INSUFFICIENT_DATA", "decision_authority": "E9_ONLY", "trade_decision": None, "data_quality": {"valid_bars": len(clean), "rejected": reasons}}
    current = len(clean) - 1
    atr = _atr(clean)
    highs = _compress(_pivot_records(_pivots(clean, "high", ER), current), atr)
    lows = _compress(_pivot_records(_pivots(clean, "low", ER), current), atr)
    highs, lows = _label(highs, lows, atr)
    ih = _compress(_pivot_records(_pivots(clean, "high", IR), current), atr)
    il = _compress(_pivot_records(_pivots(clean, "low", IR), current), atr)
    ih, il = _label(ih, il, atr)
    external = _semantic_structure_state(highs, lows)
    internal = _semantic_structure_state(ih, il)
    protected = _protected_structure(highs, lows, external["state"])
    bos = _current_break(clean, highs, lows, atr, external, "EXTERNAL", current)
    failure = _failure_from_break(bos, clean, atr)
    sweep = _sweep_reclaim(clean, highs, lows, atr)
    lifecycle = {"current_structure": external["state"], "bos_stage": "CONFIRMED" if bos.get("confirmed") else "NONE", "failure_stage": "FAILED" if failure.get("confirmed") else "NONE", "liquidity_stage": sweep.get("lifecycle", "NONE"), "last_confirmed_pivot_index": max([x["confirmation_index"] for x in highs + lows], default=None), "as_of_closed_candle": current}
    narrative = {UP: "Bullish external structure is currently dominant; internal structure is context, not authority.", DOWN: "Bearish external structure is currently dominant; internal structure is context, not authority.", MIXED: "External structure is mixed; directional commitment is not structurally clean.", NEUTRAL: "No sufficiently clear directional external structure is confirmed."}[external["state"]]
    return {"engine": "E3", "architecture": ARCHITECTURE, "question": QUESTION, "status": "OK", "decision_authority": "E9_ONLY", "trade_decision": None, "as_of_closed_candle": current, "causal": {"lookahead_allowed": False, "future_data_used": False, "confirmation_cutoff": current}, "data_quality": {"valid_bars": len(clean), "rejected": reasons, "atr": round(atr, 8)}, "external_structure": external, "internal_structure": internal, "protected_structure": protected, "bos_choch": bos, "failed_break": failure, "liquidity": sweep, "structure_lifecycle": lifecycle, "narrative": narrative, "contract": {"return_type": "dict", "tuple_normalized": True, "decision_owner": "E9"}}
