"""Production-V2 E4 Professional Liquidity & Auction Brain.

E4 is an analysis-only specialist. It maps liquidity, identifies the actor
that was swept, distinguishes sweep/rejection from accepted breakout, and
requires closed-candle follow-through before calling an auction response
confirmed. E9 remains the sole execution decision authority.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V13_LIQUIDITY_AUCTION"
MIN_BARS = 30
FOLLOW_THROUGH_BARS = 3


def _num(x: Any) -> float | None:
    try:
        value = float(x)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _bars(snapshot: Any) -> list[dict[str, float]]:
    source = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    result: list[dict[str, float]] = []
    for raw in source:
        if not isinstance(raw, dict):
            continue
        values = {key: _num(raw.get(key)) for key in ("open", "high", "low", "close")}
        if not all(value is not None for value in values.values()):
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
    true_ranges: list[float] = []
    for index in range(1, len(bars)):
        current, previous = bars[index], bars[index - 1]
        true_ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    sample = true_ranges[-period:]
    return mean(sample) if sample else 0.0


def _pivots(bars: list[dict[str, float]], wing: int = 2):
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for index in range(wing, len(bars) - wing):
        window = bars[index - wing:index + wing + 1]
        if bars[index]["high"] >= max(item["high"] for item in window):
            highs.append((index, bars[index]["high"]))
        if bars[index]["low"] <= min(item["low"] for item in window):
            lows.append((index, bars[index]["low"]))
    return highs, lows


def _cluster(levels, tolerance: float, current: int, side: str):
    groups: list[list[tuple[int, float]]] = []
    for item in sorted(levels, key=lambda pair: pair[1]):
        if not groups or abs(item[1] - mean(price for _, price in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    zones = []
    for group in groups:
        prices = [price for _, price in group]
        last_touch = max(index for index, _ in group)
        touches = len(group)
        age = max(0, current - last_touch)
        zones.append({
            "price": mean(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": touches,
            "last_touch_index": last_touch,
            "age_bars": age,
            "type": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "side": side,
            "fresh": age <= 30,
        })
    return zones


def _zone_history(zone, bars, atr, current):
    zone = dict(zone)
    penetration = max(atr * 0.05, 1e-9)
    crossings = []
    start = zone["last_touch_index"] + 1
    for index in range(start, current + 1):
        bar = bars[index]
        if zone["side"] == "HIGH" and bar["high"] > zone["upper"] + penetration:
            crossings.append(index)
        elif zone["side"] == "LOW" and bar["low"] < zone["lower"] - penetration:
            crossings.append(index)
    zone["crossings"] = crossings
    zone["consumed"] = bool(crossings)
    zone["state"] = "TAKEN" if crossings and current - crossings[-1] <= FOLLOW_THROUGH_BARS else (
        "CONSUMED" if crossings else "FRESH" if zone["fresh"] else "AGED"
    )
    zone["last_crossing_index"] = crossings[-1] if crossings else None
    return zone


def _candle_quality(bar):
    range_ = max(bar["high"] - bar["low"], 1e-9)
    body = abs(bar["close"] - bar["open"]) / range_
    upper_wick = (bar["high"] - max(bar["open"], bar["close"])) / range_
    lower_wick = (min(bar["open"], bar["close"]) - bar["low"]) / range_
    return range_, body, upper_wick, lower_wick


def _event_for_zone(bars, zone, atr, index):
    if index <= 0:
        return None
    bar, previous = bars[index], bars[index - 1]
    range_, body, upper_wick, lower_wick = _candle_quality(bar)
    level = zone["upper"] if zone["side"] == "HIGH" else zone["lower"]
    tolerance = max(atr * 0.10, 1e-9)

    if zone["side"] == "HIGH":
        swept = bar["high"] > level + atr * 0.05
        rejected = swept and bar["close"] <= level + tolerance and upper_wick >= 0.25
        failed_reclaim = previous["close"] > level + atr * 0.10 and bar["close"] <= level + tolerance
        accepted = bar["close"] > level + atr * 0.15 and body >= 0.50
        if failed_reclaim:
            kind, direction, taker, state, strength = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "BUYERS", "RECLAIMED", 0.92
        elif rejected:
            kind, direction, taker, state, strength = "HIGH_SWEEP_REJECTION", "DOWN", "BUYERS", "TAKEN", 0.90
        elif accepted:
            kind, direction, taker, state, strength = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "BUYERS", "ACCEPTANCE_CANDIDATE", 0.82
        elif swept:
            kind, direction, taker, state, strength = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "BUYERS", "TAKEN", 0.55
        else:
            return None
    else:
        swept = bar["low"] < level - atr * 0.05
        rejected = swept and bar["close"] >= level - tolerance and lower_wick >= 0.25
        failed_reclaim = previous["close"] < level - atr * 0.10 and bar["close"] >= level - tolerance
        accepted = bar["close"] < level - atr * 0.15 and body >= 0.50
        if failed_reclaim:
            kind, direction, taker, state, strength = "LOW_FAILED_BREAK_RECLAIM", "UP", "SELLERS", "RECLAIMED", 0.92
        elif rejected:
            kind, direction, taker, state, strength = "LOW_SWEEP_REJECTION", "UP", "SELLERS", "TAKEN", 0.90
        elif accepted:
            kind, direction, taker, state, strength = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "SELLERS", "ACCEPTANCE_CANDIDATE", 0.82
        elif swept:
            kind, direction, taker, state, strength = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "SELLERS", "TAKEN", 0.55
        else:
            return None

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


def _find_recent_event(bars, high_zones, low_zones, atr):
    current = len(bars) - 1
    candidates = []
    # The newest closed candle gets priority, but the previous two closed
    # candles remain eligible so an auction response can mature naturally.
    for index in range(max(1, current - 2), current + 1):
        for zone in high_zones + low_zones:
            event = _event_for_zone(bars, zone, atr, index)
            if event:
                priority = (index, event["strength"])
                candidates.append((priority, event))
    if not candidates:
        return {"type": "NO_CONFIRMED_LIQUIDITY_EVENT", "direction": "NEUTRAL", "taker": "UNCLEAR", "liquidity_state": "UNRESOLVED", "zone": None, "index": current, "strength": 0.25}
    return max(candidates, key=lambda item: item[0])[1]


def _classify_auction_response(event, bars, atr, event_index=None):
    """Classify an event only after closed-candle response is observable.

    A wick is an event, not confirmation. Acceptance needs continuation beyond
    the liquidity level. Rejection needs directional follow-through away from
    the level. Failed-break/reclaim is always treated as rejection evidence.
    """
    if not event or not event.get("zone"):
        return {"response": "UNRESOLVED", "confirmed": False, "follow_through_bars": 0, "quality": "UNRESOLVED", "reason": "NO_LIQUIDITY_EVENT"}

    index = event.get("index") if event_index is None else event_index
    zone = event["zone"]
    direction = event.get("direction", "NEUTRAL")
    level = zone["upper"] if zone.get("side") == "HIGH" else zone["lower"]
    start = int(index) + 1
    end = min(len(bars), start + FOLLOW_THROUGH_BARS)
    follow = 0
    invalidating = 0
    closes_beyond = 0

    for bar in bars[start:end]:
        if direction == "UP":
            beyond = bar["close"] > level + atr * 0.05
            opposite = bar["close"] < level - atr * 0.05
        elif direction == "DOWN":
            beyond = bar["close"] < level - atr * 0.05
            opposite = bar["close"] > level + atr * 0.05
        else:
            beyond = opposite = False
        if beyond:
            closes_beyond += 1
            follow += 1
        if opposite:
            invalidating += 1

    event_type = str(event.get("type", ""))
    rejection_event = "REJECTION" in event_type or "FAILED_BREAK" in event_type
    acceptance_event = "ACCEPTANCE_CANDIDATE" in event_type

    if rejection_event:
        confirmed = follow >= 1 and invalidating == 0
        return {
            "response": "REJECTION_CONFIRMED" if confirmed else "REJECTION_PENDING",
            "confirmed": confirmed,
            "follow_through_bars": follow,
            "quality": "CONFIRMED" if confirmed else "PENDING",
            "reason": "DIRECTIONAL_FOLLOW_THROUGH" if confirmed else "WAIT_FOR_DIRECTIONAL_FOLLOW_THROUGH",
        }
    if acceptance_event:
        confirmed = closes_beyond >= 1 and invalidating == 0
        return {
            "response": "ACCEPTANCE_CONFIRMED" if confirmed else "ACCEPTANCE_PENDING",
            "confirmed": confirmed,
            "follow_through_bars": follow,
            "quality": "CONFIRMED" if confirmed else "PENDING",
            "reason": "CLOSE_HOLD_BEYOND_LIQUIDITY" if confirmed else "WAIT_FOR_ACCEPTANCE_HOLD",
        }
    return {
        "response": "UNRESOLVED",
        "confirmed": False,
        "follow_through_bars": follow,
        "quality": "UNRESOLVED",
        "reason": "LIQUIDITY_INTERACTION_WITHOUT_AUCTION_PROOF",
    }


def _context_hint(bus):
    votes: list[str] = []
    for engine_id in ("E1", "E2", "E3"):
        package = (bus or {}).get(engine_id, {})
        evidence = package.get("evidence") if isinstance(package, dict) else None
        text = str(evidence.get("output", evidence) if isinstance(evidence, dict) else evidence or "").upper()
        if any(token in text for token in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "UP_EVIDENCE")):
            votes.append("UP")
        if any(token in text for token in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DOWN_EVIDENCE")):
            votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


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
        "context_used": {engine_id: bool((evidence_bus or {}).get(engine_id)) for engine_id in ("E1", "E2", "E3")},
        "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False},
    }
    if len(bars) < MIN_BARS or atr <= 0:
        return {**base, "state": "UNAVAILABLE", "analysis_status": "INCOMPLETE", "finding": "LIQUIDITY_DATA_INSUFFICIENT", "direction": "NEUTRAL", "directional_implication": "NEUTRAL", "confidence": 0.0, "evidence_strength": 0.0, "observations": [], "liquidity_map": {}, "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"}, "auction": {"response": "UNRESOLVED", "confirmed": False, "follow_through_bars": 0, "quality": "UNRESOLVED"}, "interaction": {}, "auction_state": "UNRESOLVED", "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "conflicts": [], "missing_evidence": ["CLOSED_CANDLE_HISTORY"]}

    current = len(bars) - 1
    high_pivots, low_pivots = _pivots(bars)
    tolerance = max(atr * 0.15, 1e-9)
    high_zones = [_zone_history(z, bars, atr, current) for z in _cluster(high_pivots[-60:], tolerance, current, "HIGH")]
    low_zones = [_zone_history(z, bars, atr, current) for z in _cluster(low_pivots[-60:], tolerance, current, "LOW")]
    event = _find_recent_event(bars, high_zones, low_zones, atr)
    auction = _classify_auction_response(event, bars, atr)
    confirmed = auction["confirmed"]
    direction = event["direction"] if confirmed else "NEUTRAL"

    reasons = []
    if event.get("zone"):
        reasons.extend(["LIQUIDITY_EVENT_DETECTED", f"TAKER={event['taker']}", f"AUCTION_{auction['response']}"])
        if not confirmed:
            reasons.append("AUCTION_RESPONSE_NOT_CONFIRMED")
    else:
        reasons.append("NO_CONFIRMED_EVENT")

    fresh_high = sum(1 for zone in high_zones if zone["fresh"] and not zone["consumed"])
    fresh_low = sum(1 for zone in low_zones if zone["fresh"] and not zone["consumed"])
    missing = [] if confirmed else ["CONFIRMED_AUCTION_RESPONSE"]

    observations = [
        f"closed_candles={len(bars)}",
        f"atr14={atr:.6f}",
        f"high_liquidity_zones={len(high_zones)}",
        f"low_liquidity_zones={len(low_zones)}",
        f"fresh_high_zones={fresh_high}",
        f"fresh_low_zones={fresh_low}",
        f"event={event['type']}",
        f"taker={event.get('taker', 'UNCLEAR')}",
        f"auction={auction['response']}",
        f"follow_through_bars={auction['follow_through_bars']}",
        f"contextual_direction={context}",
    ]

    return {
        **base,
        "state": "ANALYSIS_COMPLETE",
        "analysis_status": "COMPLETE",
        "finding": event["type"],
        "direction": direction,
        "directional_implication": direction,
        "confidence": round(event["strength"] if confirmed else min(event["strength"], 0.45), 3),
        "evidence_strength": round(event["strength"], 3),
        "observations": observations,
        "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones, "fresh_high_zones": fresh_high, "fresh_low_zones": fresh_low},
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
        "missing_evidence": missing,
    }


__all__ = ["analyze_e4"]
