"""E4 Professional Liquidity & Auction Brain v14.

E4 is evidence-only. It answers where liquidity is, who interacted with it,
and whether the auction was accepted or rejected. It never makes an execution
decision. E9 remains the sole decision authority.

Important invariant: liquidity levels used to classify an event may only come
from pivots confirmed BEFORE that event candle. This prevents look-ahead bias.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V14_LIQUIDITY_AUCTION"
MIN_BARS = 30
WING = 2
FOLLOW_THROUGH_BARS = 3


def _num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _bars(snapshot: Any) -> list[dict[str, float]]:
    source = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    result = []
    for raw in source:
        if not isinstance(raw, dict):
            continue
        values = {k: _num(raw.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            continue
        bar = values  # type: ignore[assignment]
        if bar["high"] < max(bar["open"], bar["close"]):
            continue
        if bar["low"] > min(bar["open"], bar["close"]):
            continue
        if bar["high"] < bar["low"]:
            continue
        result.append(bar)
    return result


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        c, p = bars[i], bars[i - 1]
        trs.append(max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"])))
    return mean(trs[-period:]) if trs else 0.0


def _confirmed_pivots(bars: list[dict[str, float]], end_exclusive: int, wing: int = WING):
    """Return only pivots fully confirmed by bars strictly before end_exclusive."""
    highs, lows = [], []
    last_pivot_index = end_exclusive - wing - 1
    for i in range(wing, max(wing, last_pivot_index + 1)):
        window = bars[i - wing:i + wing + 1]
        if len(window) != wing * 2 + 1:
            continue
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, bars[i]["low"]))
    return highs, lows


def _cluster(levels, tolerance: float, current_index: int, side: str):
    groups = []
    for item in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(item[1] - mean(v for _, v in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    zones = []
    for group in groups:
        prices = [v for _, v in group]
        last_touch = max(i for i, _ in group)
        touches = len(group)
        zones.append({
            "price": mean(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": touches,
            "last_touch_index": last_touch,
            "age_bars": max(0, current_index - last_touch),
            "type": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "side": side,
            "fresh": current_index - last_touch <= 30,
        })
    return zones


def _candle_quality(bar):
    range_ = max(bar["high"] - bar["low"], 1e-9)
    body = abs(bar["close"] - bar["open"]) / range_
    upper = (bar["high"] - max(bar["open"], bar["close"])) / range_
    lower = (min(bar["open"], bar["close"]) - bar["low"]) / range_
    return body, upper, lower


def _event_for_zone(bars, zone, atr, index):
    if index <= 0 or not zone:
        return None
    bar, previous = bars[index], bars[index - 1]
    body, upper_wick, lower_wick = _candle_quality(bar)
    level = zone["upper"] if zone["side"] == "HIGH" else zone["lower"]
    if zone["side"] == "HIGH":
        swept = bar["high"] > level + atr * 0.05
        rejection = swept and bar["close"] <= level + atr * 0.10 and upper_wick >= 0.25
        failed_break = previous["close"] > level + atr * 0.10 and bar["close"] <= level + atr * 0.10
        accepted = bar["close"] > level + atr * 0.15 and body >= 0.50
        if failed_break:
            kind, direction, state, strength = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "RECLAIMED", 0.92
        elif rejection:
            kind, direction, state, strength = "HIGH_SWEEP_REJECTION", "DOWN", "TAKEN", 0.90
        elif accepted:
            kind, direction, state, strength = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "ACCEPTANCE_CANDIDATE", 0.82
        elif swept:
            kind, direction, state, strength = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "TAKEN", 0.55
        else:
            return None
        taker = "BUYERS"
    else:
        swept = bar["low"] < level - atr * 0.05
        rejection = swept and bar["close"] >= level - atr * 0.10 and lower_wick >= 0.25
        failed_break = previous["close"] < level - atr * 0.10 and bar["close"] >= level - atr * 0.10
        accepted = bar["close"] < level - atr * 0.15 and body >= 0.50
        if failed_break:
            kind, direction, state, strength = "LOW_FAILED_BREAK_RECLAIM", "UP", "RECLAIMED", 0.92
        elif rejection:
            kind, direction, state, strength = "LOW_SWEEP_REJECTION", "UP", "TAKEN", 0.90
        elif accepted:
            kind, direction, state, strength = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "ACCEPTANCE_CANDIDATE", 0.82
        elif swept:
            kind, direction, state, strength = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "TAKEN", 0.55
        else:
            return None
        taker = "SELLERS"
    return {
        "type": kind,
        "direction": direction,
        "taker": taker,
        "liquidity_state": state,
        "zone": zone,
        "index": index,
        "strength": strength,
        "event_candle": {"high": bar["high"], "low": bar["low"], "close": bar["close"]},
    }


def _zones_before_event(bars, event_index, atr):
    highs, lows = _confirmed_pivots(bars, event_index)
    tolerance = max(atr * 0.15, 1e-9)
    return (
        _cluster(highs[-60:], tolerance, event_index, "HIGH"),
        _cluster(lows[-60:], tolerance, event_index, "LOW"),
    )


def _find_recent_event(bars, atr):
    current = len(bars) - 1
    candidates = []
    for index in range(max(1, current - 2), current + 1):
        highs, lows = _zones_before_event(bars, index, atr)
        for zone in highs + lows:
            event = _event_for_zone(bars, zone, atr, index)
            if event:
                # Newer event wins; strength breaks ties only.
                candidates.append(((index, event["strength"]), event))
    if not candidates:
        return {
            "type": "NO_CONFIRMED_LIQUIDITY_EVENT",
            "direction": "NEUTRAL",
            "taker": "UNCLEAR",
            "liquidity_state": "UNRESOLVED",
            "zone": None,
            "index": current,
            "strength": 0.25,
        }
    return max(candidates, key=lambda x: x[0])[1]


def _auction_response(event, bars, atr):
    if not event or not event.get("zone"):
        return {"response": "UNRESOLVED", "confirmed": False, "follow_through_bars": 0, "quality": "UNRESOLVED", "reason": "NO_LIQUIDITY_EVENT"}
    index = int(event["index"])
    zone = event["zone"]
    level = zone["upper"] if zone["side"] == "HIGH" else zone["lower"]
    direction = event["direction"]
    response_bars = bars[index + 1:min(len(bars), index + 1 + FOLLOW_THROUGH_BARS)]
    beyond = 0
    opposite = 0
    for bar in response_bars:
        if direction == "UP":
            if bar["close"] > level + atr * 0.05:
                beyond += 1
            if bar["close"] < level - atr * 0.05:
                opposite += 1
        elif direction == "DOWN":
            if bar["close"] < level - atr * 0.05:
                beyond += 1
            if bar["close"] > level + atr * 0.05:
                opposite += 1
    event_type = event["type"]
    rejection_event = "REJECTION" in event_type or "FAILED_BREAK" in event_type
    acceptance_event = "ACCEPTANCE_CANDIDATE" in event_type
    if rejection_event:
        confirmed = beyond >= 1 and opposite == 0
        return {
            "response": "REJECTION_CONFIRMED" if confirmed else "REJECTION_PENDING",
            "confirmed": confirmed,
            "follow_through_bars": beyond,
            "quality": "CONFIRMED" if confirmed else "PENDING",
            "reason": "DIRECTIONAL_FOLLOW_THROUGH" if confirmed else "WAIT_FOR_DIRECTIONAL_FOLLOW_THROUGH",
        }
    if acceptance_event:
        confirmed = beyond >= 1 and opposite == 0
        return {
            "response": "ACCEPTANCE_CONFIRMED" if confirmed else "ACCEPTANCE_PENDING",
            "confirmed": confirmed,
            "follow_through_bars": beyond,
            "quality": "CONFIRMED" if confirmed else "PENDING",
            "reason": "CLOSE_HOLD_BEYOND_LIQUIDITY" if confirmed else "WAIT_FOR_ACCEPTANCE_HOLD",
        }
    return {
        "response": "UNRESOLVED",
        "confirmed": False,
        "follow_through_bars": beyond,
        "quality": "UNRESOLVED",
        "reason": "LIQUIDITY_INTERACTION_WITHOUT_AUCTION_PROOF",
    }


def _context_hint(bus):
    votes = []
    for engine_id in ("E1", "E2", "E3"):
        package = (bus or {}).get(engine_id, {})
        evidence = package.get("evidence") if isinstance(package, dict) else None
        text = str(evidence.get("output", evidence) if isinstance(evidence, dict) else evidence or "").upper()
        if any(x in text for x in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "UP_EVIDENCE")):
            votes.append("UP")
        if any(x in text for x in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DOWN_EVIDENCE")):
            votes.append("DOWN")
    if votes.count("UP") > votes.count("DOWN"):
        return "UP"
    if votes.count("DOWN") > votes.count("UP"):
        return "DOWN"
    return "NEUTRAL"


def analyze_e4(snapshot=None, evidence_bus=None):
    bars = _bars(snapshot)
    atr = _atr(bars)
    context = _context_hint(evidence_bus)
    base = {
        "architecture": ARCHITECTURE,
        "question": QUESTION,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "decision": None,
        "gate": None,
        "score": None,
        "contextual_direction_hint": context,
        "context_used": {x: bool((evidence_bus or {}).get(x)) for x in ("E1", "E2", "E3")},
        "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False},
    }
    if len(bars) < MIN_BARS or atr <= 0:
        return {**base,
            "state": "UNAVAILABLE", "analysis_status": "INCOMPLETE",
            "finding": "LIQUIDITY_DATA_INSUFFICIENT", "direction": "NEUTRAL",
            "directional_implication": "NEUTRAL", "confidence": 0.0, "evidence_strength": 0.0,
            "observations": [], "liquidity_map": {},
            "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"},
            "auction": {"response": "UNRESOLVED", "confirmed": False, "follow_through_bars": 0, "quality": "UNRESOLVED"},
            "interaction": {}, "auction_state": "UNRESOLVED",
            "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "conflicts": [],
            "missing_evidence": ["CLOSED_CANDLE_HISTORY"]}

    current = len(bars) - 1
    current_highs, current_lows = _zones_before_event(bars, current + 1, atr)
    event = _find_recent_event(bars, atr)
    auction = _auction_response(event, bars, atr)
    confirmed = auction["confirmed"]
    direction = event["direction"] if confirmed else "NEUTRAL"
    fresh_high = sum(1 for z in current_highs if z["fresh"])
    fresh_low = sum(1 for z in current_lows if z["fresh"])
    reasons = ["LIQUIDITY_EVENT_DETECTED"] if event.get("zone") else ["NO_CONFIRMED_EVENT"]
    if event.get("zone"):
        reasons += [f"TAKER={event['taker']}", f"AUCTION_{auction['response']}"]
        if not confirmed:
            reasons.append("AUCTION_RESPONSE_NOT_CONFIRMED")
    return {
        **base,
        "state": "ANALYSIS_COMPLETE",
        "analysis_status": "COMPLETE",
        "finding": event["type"],
        "direction": direction,
        "directional_implication": direction,
        "confidence": round(event["strength"] if confirmed else min(event["strength"], 0.45), 3),
        "evidence_strength": round(event["strength"], 3),
        "observations": [
            f"closed_candles={len(bars)}", f"atr14={atr:.6f}",
            f"high_liquidity_zones={len(current_highs)}", f"low_liquidity_zones={len(current_lows)}",
            f"fresh_high_zones={fresh_high}", f"fresh_low_zones={fresh_low}",
            f"event={event['type']}", f"taker={event.get('taker', 'UNCLEAR')}",
            f"auction={auction['response']}", f"follow_through_bars={auction['follow_through_bars']}",
            f"contextual_direction={context}",
        ],
        "liquidity_map": {"high_zones": current_highs, "low_zones": current_lows,
                          "fresh_high_zones": fresh_high, "fresh_low_zones": fresh_low},
        "event": event,
        "auction": auction,
        "interaction": {
            "rejection": auction["response"].startswith("REJECTION"),
            "acceptance": auction["response"].startswith("ACCEPTANCE"),
            "failed_break_reclaim": "FAILED_BREAK" in event["type"],
            "taker": event.get("taker", "UNCLEAR"),
        },
        "auction_state": auction["response"],
        "reasons": reasons,
        "conflicts": [],
        "missing_evidence": [] if confirmed else ["CONFIRMED_AUCTION_RESPONSE"],
    }


__all__ = ["analyze_e4"]
