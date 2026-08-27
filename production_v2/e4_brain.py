"""Production-V2 E4 professional liquidity/auction brain V12.

E4 is an independent market-evidence analyst. It maps swing/equal liquidity,
tracks consumption, evaluates only the latest closed candle for a current event,
and distinguishes rejection, acceptance, failed-break reclaim, and no event.
E4 never authorizes execution; E9 remains the sole decision authority.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V12"
_FORBIDDEN = {"decision", "trade_decision", "decision_score", "score", "gate", "gate_passed", "specialist_gate"}


def _f(x: Any):
    try:
        y = float(x)
        return y if isfinite(y) else None
    except (TypeError, ValueError):
        return None


def _bars(snapshot: Any):
    source = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    out = []
    for b in source:
        if not isinstance(b, dict):
            continue
        values = {k: _f(b.get(k)) for k in ("open", "high", "low", "close")}
        if all(v is not None for v in values.values()) and values["high"] >= values["low"]:
            out.append(values)
    return out


def _atr(bars, period: int = 14):
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        trs.append(max(b["high"] - b["low"], abs(b["high"] - p["close"]), abs(b["low"] - p["close"])))
    return sum(trs[-period:]) / min(len(trs), period)


def _pivots(bars, wing: int = 2):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, bars[i]["low"]))
    return highs, lows


def _clusters(levels, tolerance: float, current_index: int):
    groups = []
    for idx, price in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(price - sum(x[1] for x in groups[-1]) / len(groups[-1])) > tolerance:
            groups.append([(idx, price)])
        else:
            groups[-1].append((idx, price))
    zones = []
    for group in groups:
        prices = [x[1] for x in group]
        last_touch = max(x[0] for x in group)
        touches = len(group)
        age = max(0, current_index - last_touch)
        zones.append({
            "price": sum(prices) / len(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": touches,
            "last_touch_index": last_touch,
            "age_bars": age,
            "type": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "fresh": touches >= 2 or age <= 30,
        })
    return zones


def _zone_consumption(zone, bars, side, current_index, atr):
    z = dict(zone)
    taken_index = None
    prior_taken_index = None
    state = "FRESH" if zone["fresh"] else "AGED"
    for i in range(zone["last_touch_index"] + 1, len(bars)):
        b = bars[i]
        crossed = (b["high"] > z["upper"] + atr * 0.05) if side == "HIGH" else (b["low"] < z["lower"] - atr * 0.05)
        if crossed:
            taken_index = i
            if i < current_index:
                prior_taken_index = i
    if taken_index is not None:
        state = "TAKEN" if current_index - taken_index <= 1 else "CONSUMED"
    z["state"] = state
    z["consumed"] = taken_index is not None
    z["taken_index"] = taken_index
    z["prior_taken_index"] = prior_taken_index
    return z


def _event_at(bars, zones_hi, zones_lo, atr, index):
    b = bars[index]
    previous = bars[index - 1] if index else b
    tolerance = max(atr * 0.10, 1e-9)
    range_ = max(b["high"] - b["low"], 1e-9)
    body_ratio = abs(b["close"] - b["open"]) / range_
    upper_wick = b["high"] - max(b["open"], b["close"])
    lower_wick = min(b["open"], b["close"]) - b["low"]
    proximity = max(atr * 0.75, tolerance)
    highs = [z for z in zones_hi if z.get("prior_taken_index") is None and (abs(b["high"] - z["price"]) <= proximity or b["high"] > z["upper"] - tolerance)]
    lows = [z for z in zones_lo if z.get("prior_taken_index") is None and (abs(b["low"] - z["price"]) <= proximity or b["low"] < z["lower"] + tolerance)]
    high = min(highs, key=lambda z: abs(b["high"] - z["price"]), default=None)
    low = min(lows, key=lambda z: abs(b["low"] - z["price"]), default=None)
    if high:
        sweep = b["high"] > high["upper"] + tolerance * 0.05 and b["close"] <= high["upper"] + tolerance * 0.10
        failed = previous["close"] > high["upper"] + atr * 0.10 and b["close"] <= high["upper"]
        accept = b["close"] > high["upper"] + atr * 0.15 and body_ratio >= 0.55
        if failed:
            return {"type": "HIGH_FAILED_BREAK_RECLAIM", "liquidity_state": "RECLAIMED", "direction": "DOWN", "zone": high, "strength": 0.90, "index": index}
        if sweep and upper_wick / range_ >= 0.30:
            return {"type": "HIGH_SWEEP_REJECTION", "liquidity_state": "TAKEN", "direction": "DOWN", "zone": high, "strength": 0.93, "index": index}
        if accept:
            return {"type": "HIGH_ACCEPTANCE", "liquidity_state": "ACCEPTED", "direction": "UP", "zone": high, "strength": 0.88, "index": index}
    if low:
        sweep = b["low"] < low["lower"] - tolerance * 0.05 and b["close"] >= low["lower"] - tolerance * 0.10
        failed = previous["close"] < low["lower"] - atr * 0.10 and b["close"] >= low["lower"]
        accept = b["close"] < low["lower"] - atr * 0.15 and body_ratio >= 0.55
        if failed:
            return {"type": "LOW_FAILED_BREAK_RECLAIM", "liquidity_state": "RECLAIMED", "direction": "UP", "zone": low, "strength": 0.90, "index": index}
        if sweep and lower_wick / range_ >= 0.30:
            return {"type": "LOW_SWEEP_REJECTION", "liquidity_state": "TAKEN", "direction": "UP", "zone": low, "strength": 0.93, "index": index}
        if accept:
            return {"type": "LOW_ACCEPTANCE", "liquidity_state": "ACCEPTED", "direction": "DOWN", "zone": low, "strength": 0.88, "index": index}
    return None


def _event_quality(event, atr, current_index):
    if not event or not event.get("zone"):
        return {
            "event_recency": 0.0,
            "liquidity_quality": 0.0,
            "auction_quality": 0.0,
            "confirmation_quality": 0.0,
            "overall": 0.0,
        }
    zone = event["zone"]
    age = max(0, current_index - int(event.get("index", current_index)))
    recency = 1.0 if age == 0 else max(0.0, 1.0 - age / 3.0)
    touches = int(zone.get("touches", 1))
    liquidity_quality = min(1.0, 0.55 + min(touches, 4) * 0.10) if zone.get("fresh") else 0.35
    auction_quality = max(0.0, min(1.0, float(event.get("strength", 0.0))))
    confirmation_quality = 1.0 if event.get("type") in {
        "HIGH_SWEEP_REJECTION", "LOW_SWEEP_REJECTION",
        "HIGH_ACCEPTANCE", "LOW_ACCEPTANCE",
        "HIGH_FAILED_BREAK_RECLAIM", "LOW_FAILED_BREAK_RECLAIM",
    } and age == 0 else 0.0
    overall = round(0.25 * recency + 0.25 * liquidity_quality + 0.30 * auction_quality + 0.20 * confirmation_quality, 4)
    return {
        "event_recency": round(recency, 4),
        "liquidity_quality": round(liquidity_quality, 4),
        "auction_quality": round(auction_quality, 4),
        "confirmation_quality": round(confirmation_quality, 4),
        "overall": overall,
    }


def _context_hint(bus):
    votes = []
    for eid in ("E1", "E2", "E3"):
        package = (bus or {}).get(eid, {})
        evidence = package.get("evidence") if isinstance(package, dict) else None
        if isinstance(evidence, dict):
            evidence = evidence.get("output", evidence)
        text = str(evidence or "").upper()
        if any(t in text for t in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "UP_EVIDENCE")):
            votes.append("UP")
        if any(t in text for t in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DOWN_EVIDENCE")):
            votes.append("DOWN")
    if votes.count("UP") > votes.count("DOWN"):
        return "UP"
    if votes.count("DOWN") > votes.count("UP"):
        return "DOWN"
    return "NEUTRAL"


def analyze_e4(snapshot=None, evidence_bus=None):
    bars = _bars(snapshot)
    atr = _atr(bars)
    hint = _context_hint(evidence_bus)
    base = {
        "architecture": ARCHITECTURE,
        "question": QUESTION,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "decision": None,
        "gate": None,
        "score": None,
        "contextual_direction_hint": hint,
        "context_used": {e: bool((evidence_bus or {}).get(e)) for e in ("E1", "E2", "E3")},
        "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False},
    }
    if len(bars) < 20 or atr <= 0:
        return {**base, "state": "UNAVAILABLE", "analysis_status": "INCOMPLETE", "finding": "LIQUIDITY_DATA_INSUFFICIENT", "direction": "NEUTRAL", "directional_implication": "NEUTRAL", "confidence": 0.0, "evidence_strength": 0.0, "observations": [], "liquidity_map": {}, "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED", "age_bars": None, "confirmation_state": "NONE"}, "interaction": {}, "auction_state": "UNRESOLVED", "quality_components": _event_quality(None, atr, max(0, len(bars) - 1)), "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "conflicts": [], "missing_evidence": ["CLOSED_CANDLE_HISTORY"]}

    current_index = len(bars) - 1
    highs, lows = _pivots(bars)
    tolerance = max(atr * 0.15, 1e-9)
    high_zones = [_zone_consumption(z, bars, "HIGH", current_index, atr) for z in _clusters(highs[-50:], tolerance, current_index)]
    low_zones = [_zone_consumption(z, bars, "LOW", current_index, atr) for z in _clusters(lows[-50:], tolerance, current_index)]

    # Professional discipline: a current E4 event must be produced by the latest
    # closed candle. Older events remain in the liquidity map but cannot be
    # promoted to the current auction state.
    event = _event_at(bars, high_zones, low_zones, atr, current_index)
    if event is None:
        event = {
            "type": "NO_CONFIRMED_LIQUIDITY_EVENT",
            "liquidity_state": "UNRESOLVED",
            "direction": "NEUTRAL",
            "zone": None,
            "strength": 0.35,
            "index": current_index,
        }

    event["age_bars"] = max(0, current_index - int(event.get("index", current_index)))
    event["confirmation_state"] = "CONFIRMED" if event["type"] != "NO_CONFIRMED_LIQUIDITY_EVENT" and event["age_bars"] == 0 else "NONE" if event["type"] == "NO_CONFIRMED_LIQUIDITY_EVENT" else "UNCONFIRMED"
    event["current_closed_candle"] = event["age_bars"] == 0

    event_type = event["type"]
    auction = "REJECTION" if "REJECTION" in event_type or "FAILED_BREAK" in event_type else "ACCEPTANCE" if "ACCEPTANCE" in event_type else "UNRESOLVED"
    fresh_high = [z for z in high_zones if z["fresh"] and z["state"] in {"FRESH", "TAKEN"}]
    fresh_low = [z for z in low_zones if z["fresh"] and z["state"] in {"FRESH", "TAKEN"}]
    quality = _event_quality(event, atr, current_index)

    reasons = []
    if "SWEEP" in event_type:
        reasons += ["LIQUIDITY_TAKEN", "REJECTION_AFTER_SWEEP"]
    elif "FAILED_BREAK" in event_type:
        reasons += ["FAILED_BREAK_RECLAIM", "LIQUIDITY_RECLAIMED"]
    elif "ACCEPTANCE" in event_type:
        reasons.append("ACCEPTANCE_BEYOND_LIQUIDITY")
    else:
        reasons.append("NO_CONFIRMED_EVENT")
    if not fresh_high and not fresh_low:
        reasons.append("FRESH_LIQUIDITY_LIMITED")
    if event["age_bars"] > 0:
        reasons.append("EVENT_NOT_CURRENT_CLOSED_CANDLE")

    price = bars[-1]["close"]
    nearest_high = min((z for z in high_zones if z["price"] >= price), key=lambda z: z["price"] - price, default=None)
    nearest_low = min((z for z in low_zones if z["price"] <= price), key=lambda z: price - z["price"], default=None)
    return {**base,
        "state": "ANALYSIS_COMPLETE", "analysis_status": "COMPLETE", "finding": event_type,
        "direction": event["direction"], "directional_implication": event["direction"],
        "confidence": event["strength"], "evidence_strength": event["strength"],
        "observations": [f"closed_candles={len(bars)}", f"atr14={atr:.6f}", f"price={price:.6f}", f"high_liquidity_zones={len(high_zones)}", f"low_liquidity_zones={len(low_zones)}", f"event={event_type}", f"auction_state={auction}", f"event_age_bars={event['age_bars']}", f"confirmation={event['confirmation_state']}", f"contextual_direction={hint}"],
        "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones, "fresh_high_zones": len(fresh_high), "fresh_low_zones": len(fresh_low), "nearest_high": nearest_high["price"] if nearest_high else None, "nearest_low": nearest_low["price"] if nearest_low else None},
        "event": event,
        "interaction": {"rejection": auction == "REJECTION", "acceptance": auction == "ACCEPTANCE", "failed_break_reclaim": "FAILED_BREAK" in event_type},
        "auction_state": auction,
        "quality_components": quality,
        "reasons": reasons, "conflicts": [], "missing_evidence": [] if event["zone"] else ["CONFIRMED_AUCTION_EVENT"]}


__all__ = ["analyze_e4"]