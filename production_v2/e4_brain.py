from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V19"
MIN_BARS = 30
PIVOT_WING = 2
LOOKBACK_PIVOTS = 80
FOLLOW_WINDOW = 3
ZONE_TOLERANCE_ATR = 0.15
INTERACTION_ATR = 0.05
REJECTION_CLOSE_ATR = 0.10
ACCEPTANCE_ATR = 0.15
MIN_BODY_RATIO = 0.55
MIN_WICK_RATIO = 0.30


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _bars(source: Any) -> list[dict[str, Any]]:
    raw = source.get("bars") if isinstance(source, dict) else source
    result = []
    for raw_bar in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(raw_bar, dict):
            continue
        if raw_bar.get("closed") is False or raw_bar.get("is_closed") is False:
            continue
        values = {key: _num(raw_bar.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            continue
        if values["high"] < max(values["open"], values["close"]):
            continue
        if values["low"] > min(values["open"], values["close"]):
            continue
        if values["high"] < values["low"]:
            continue
        result.append({**raw_bar, **values})
    return result


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr = []
    for index in range(1, len(bars)):
        high = float(bars[index]["high"])
        low = float(bars[index]["low"])
        previous_close = float(bars[index - 1]["close"])
        tr.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(tr[-period:]) if tr else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = PIVOT_WING):
    highs, lows = [], []
    for index in range(wing, len(bars) - wing):
        window = bars[index - wing:index + wing + 1]
        if bars[index]["high"] >= max(item["high"] for item in window):
            highs.append((index, float(bars[index]["high"])))
        if bars[index]["low"] <= min(item["low"] for item in window):
            lows.append((index, float(bars[index]["low"])))
    return highs, lows


def _cluster(levels, tolerance: float, side: str, current: int):
    groups = []
    for item in sorted(levels, key=lambda pair: pair[1]):
        if not groups or abs(item[1] - mean(price for _, price in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    zones = []
    for group in groups:
        prices = [price for _, price in group]
        last = max(index for index, _ in group)
        touches = len(group)
        age = max(0, current - last)
        zones.append({
            "side": side,
            "price": mean(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": touches,
            "last_touch_index": last,
            "age_bars": age,
            "kind": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "hierarchy": "EQUAL_LEVEL" if touches >= 2 else "SWING_LEVEL",
            "freshness": "FRESH" if age <= 24 else "AGED",
        })
    return zones


def _consume(zones, bars, atr):
    threshold = max(atr * INTERACTION_ATR, 1e-9)
    result = []
    current = len(bars) - 1
    for zone in zones:
        z = dict(zone)
        takes = []
        for index in range(zone["last_touch_index"] + 1, len(bars)):
            bar = bars[index]
            crossed = (bar["high"] > zone["upper"] + threshold if zone["side"] == "HIGH" else bar["low"] < zone["lower"] - threshold)
            if crossed:
                takes.append(index)
        latest = takes[-1] if takes else None
        z.update({
            "liquidity_taken": latest is not None,
            "taken_index": latest,
            "take_count": len(takes),
            "recently_taken": latest is not None and current - latest <= FOLLOW_WINDOW,
            "state": "TAKEN" if latest is not None and current - latest <= FOLLOW_WINDOW else "CONSUMED" if latest is not None else zone["freshness"],
        })
        result.append(z)
    return result


def _body_ratio(bar):
    return abs(float(bar["close"]) - float(bar["open"])) / max(float(bar["high"]) - float(bar["low"]), 1e-12)


def _event_for_zone(bars, zone, atr, index):
    if index <= int(zone.get("last_touch_index", -1)):
        return None
    taken_index = zone.get("taken_index")
    if taken_index is not None and index > int(taken_index):
        return None
    bar = bars[index]
    previous = bars[index - 1]
    level = float(zone["upper"] if zone["side"] == "HIGH" else zone["lower"])
    span = max(float(bar["high"]) - float(bar["low"]), 1e-12)
    upper_wick = (float(bar["high"]) - max(float(bar["open"]), float(bar["close"]))) / span
    lower_wick = (min(float(bar["open"]), float(bar["close"])) - float(bar["low"])) / span
    sweep = max(atr * INTERACTION_ATR, 1e-9)
    close_band = max(atr * REJECTION_CLOSE_ATR, 1e-9)
    extension = max(atr * ACCEPTANCE_ATR, 1e-9)
    if zone["side"] == "HIGH":
        swept = bar["high"] > level + sweep
        rejection = swept and bar["close"] <= level + close_band and upper_wick >= MIN_WICK_RATIO
        failed = previous["close"] > level + extension and bar["close"] <= level + close_band
        acceptance = previous["close"] <= level + close_band and bar["close"] > level + extension and _body_ratio(bar) >= MIN_BODY_RATIO
        if failed:
            kind, direction, taker, actor, strength, state = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "BUYERS", "SELLERS", 0.94, "FAILED_BREAK_RECLAIM"
        elif rejection:
            kind, direction, taker, actor, strength, state = "HIGH_SWEEP_REJECTION", "DOWN", "BUYERS", "SELLERS", 0.95, "REJECTION"
        elif acceptance:
            kind, direction, taker, actor, strength, state = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "BUYERS", "BUYERS", 0.88, "ACCEPTANCE"
        elif swept:
            kind, direction, taker, actor, strength, state = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "BUYERS", "UNCLEAR", 0.55, "INTERACTION"
        else:
            return None
    else:
        swept = bar["low"] < level - sweep
        rejection = swept and bar["close"] >= level - close_band and lower_wick >= MIN_WICK_RATIO
        failed = previous["close"] < level - extension and bar["close"] >= level - close_band
        acceptance = previous["close"] >= level - close_band and bar["close"] < level - extension and _body_ratio(bar) >= MIN_BODY_RATIO
        if failed:
            kind, direction, taker, actor, strength, state = "LOW_FAILED_BREAK_RECLAIM", "UP", "SELLERS", "BUYERS", 0.94, "FAILED_BREAK_RECLAIM"
        elif rejection:
            kind, direction, taker, actor, strength, state = "LOW_SWEEP_REJECTION", "UP", "SELLERS", "BUYERS", 0.95, "REJECTION"
        elif acceptance:
            kind, direction, taker, actor, strength, state = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "SELLERS", "SELLERS", 0.88, "ACCEPTANCE"
        elif swept:
            kind, direction, taker, actor, strength, state = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "SELLERS", "UNCLEAR", 0.55, "INTERACTION"
        else:
            return None
    return {
        "type": kind,
        "auction_state": state,
        "directional_implication": direction,
        "liquidity_state": "REJECTED" if state == "REJECTION" else "RECLAIMED" if state == "FAILED_BREAK_RECLAIM" else "ACCEPTANCE_CANDIDATE" if state == "ACCEPTANCE" else "TAKEN",
        "liquidity_taker": taker,
        "response_actor": actor,
        "strength": strength,
        "zone": zone,
        "index": index,
        "event_candle": {key: float(bar[key]) for key in ("open", "high", "low", "close")},
    }


def _find_recent_event(bars, high_zones, low_zones, atr):
    current = len(bars) - 1
    candidates = []
    for index in range(max(1, current - FOLLOW_WINDOW), current + 1):
        for zone in high_zones + low_zones:
            event = _event_for_zone(bars, zone, atr, index)
            if event:
                candidates.append((index, int(zone.get("touches", 1)), event))
    if not candidates:
        return {"type": "NO_CONFIRMED_LIQUIDITY_EVENT", "auction_state": "UNRESOLVED", "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "liquidity_taker": "NONE", "response_actor": "NONE", "strength": 0.30, "zone": None, "index": current}
    def priority(item):
        state = item[2].get("auction_state")
        event_quality = 2 if state in {"REJECTION", "ACCEPTANCE", "FAILED_BREAK_RECLAIM"} else 1
        return event_quality, item[0], item[1], item[2]["strength"]
    return max(candidates, key=priority)[2]


def _follow_through(event, bars, atr):
    index = int(event.get("index", -1))
    zone = event.get("zone") or {}
    if index < 0 or index >= len(bars) - 1 or not zone:
        return {"present": False, "bars": 0, "reason": "NO_POST_EVENT_CANDLE", "invalidated": False, "checks": []}
    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    origin = float(bars[index]["close"])
    upper = float(zone.get("upper", origin))
    lower = float(zone.get("lower", origin))
    distance = max(atr * INTERACTION_ATR, 1e-9)
    count = 0
    invalidated = False
    checks = []
    for current_index in range(index + 1, min(len(bars), index + FOLLOW_WINDOW + 1)):
        close = float(bars[current_index]["close"])
        if direction == "DOWN":
            away, held, reclaimed = close < origin - distance, close < upper - distance, close > upper + distance
        elif direction == "UP":
            away, held, reclaimed = close > origin + distance, close > lower + distance, close < lower - distance
        else:
            away = held = reclaimed = False
        if reclaimed:
            invalidated = True
        confirmed = away and held and not reclaimed
        if confirmed:
            count += 1
        checks.append({"index": current_index, "close": close, "confirmed": confirmed, "reclaimed": reclaimed})
    return {"present": count >= 1 and not invalidated, "bars": count, "reason": "FOLLOW_THROUGH_OBSERVED" if count >= 1 and not invalidated else "FOLLOW_THROUGH_ABSENT", "invalidated": invalidated, "checks": checks}


def _auction_confirmation(event, bars, atr):
    if not event.get("zone"):
        return {"state": "UNRESOLVED", "confirmed": False, "follow_through": False, "follow_through_bars": 0, "reason": "NO_EVENT"}
    follow = _follow_through(event, bars, atr)
    base = event.get("auction_state")
    if follow["invalidated"]:
        state, confirmed = "INVALIDATED", False
    elif follow["present"]:
        state = {"REJECTION": "REJECTION_CONFIRMED", "ACCEPTANCE": "ACCEPTANCE_CONFIRMED", "FAILED_BREAK_RECLAIM": "REJECTION_CONFIRMED"}.get(base, "UNRESOLVED")
        confirmed = state != "UNRESOLVED"
    else:
        state = {"REJECTION": "REJECTION_PENDING", "ACCEPTANCE": "ACCEPTANCE_PENDING", "FAILED_BREAK_RECLAIM": "REJECTION_PENDING"}.get(base, "UNRESOLVED")
        confirmed = False
    return {"state": state, "confirmed": confirmed, "follow_through": follow["present"], "follow_through_bars": follow["bars"], "reason": "POST_EVENT_RECLAMATION" if follow["invalidated"] else "FOLLOW_THROUGH_OBSERVED" if follow["present"] else follow["reason"], "detail": follow}


def _context_hint(evidence_bus):
    votes = []
    for engine_id in ("E1", "E2", "E3"):
        package = (evidence_bus or {}).get(engine_id, {})
        evidence = package.get("evidence", package) if isinstance(package, dict) else {}
        output = evidence.get("output", evidence) if isinstance(evidence, dict) else evidence
        text = str(output).upper()
        if any(token in text for token in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "DIRECTION: UP", "DIRECTION\": \"UP")):
            votes.append("UP")
        if any(token in text for token in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DIRECTION: DOWN", "DIRECTION\": \"DOWN")):
            votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


def analyze_e4(snapshot=None, evidence_bus=None):
    bars = _bars(snapshot)
    atr = _atr(bars)
    context = _context_hint(evidence_bus)
    base = {
        "architecture": ARCHITECTURE,
        "professional_brain": True,
        "role": E4_ROLE,
        "question": PROFESSIONAL_QUESTION,
        "specialists_active": False,
        "specialists_status": "PAUSED",
        "decision": None,
        "gate": None,
        "score": None,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "reasoning_role": E4_ROLE,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
        "scores_used": False,
        "score_used": False,
        "contextual_direction_hint": context,
        "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False},
    }
    if len(bars) < MIN_BARS or atr <= 0:
        return {**base, "state": "UNAVAILABLE", "analysis_status": "INCOMPLETE", "finding": "LIQUIDITY_DATA_INSUFFICIENT", "direction": "NEUTRAL", "directional_implication": "NEUTRAL", "direction_confirmed": False, "confidence": 0.0, "evidence_strength": 0.0, "observations": [], "liquidity_map": {}, "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"}, "auction": {"state": "UNRESOLVED", "confirmed": False, "follow_through": False, "follow_through_bars": 0}, "auction_state": "UNRESOLVED", "follow_through": {"present": False, "bars": 0}, "follow_through_bars": 0, "auction_confirmation": {"confirmed": False}, "auction_confirmation_state": "UNRESOLVED", "auction_quality": "UNRESOLVED", "counter_evidence": ["INSUFFICIENT_DATA"], "invalidation": ["new closed-candle data"], "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"]}

    current = len(bars) - 1
    pivot_highs, pivot_lows = _pivots(bars)
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    high_zones = _consume(_cluster(pivot_highs[-LOOKBACK_PIVOTS:], tolerance, "HIGH", current), bars, atr)
    low_zones = _consume(_cluster(pivot_lows[-LOOKBACK_PIVOTS:], tolerance, "LOW", current), bars, atr)
    event = _find_recent_event(bars, high_zones, low_zones, atr)
    auction = _auction_confirmation(event, bars, atr)
    confirmed = bool(auction["confirmed"])
    direction = event["directional_implication"] if confirmed else "NEUTRAL"
    follow = auction.get("detail") or {"present": False, "bars": 0}

    if auction["state"] == "INVALIDATED":
        counter = ["POST_EVENT_RECLAMATION", "ORIGINAL_AUCTION_THESIS_REJECTED"]
    elif not event.get("zone"):
        counter = ["NO_LIQUIDITY_EVENT"]
    elif not confirmed:
        counter = ["NO_FOLLOW_THROUGH", "AUCTION_DIRECTION_REMAINS_UNRESOLVED"]
    elif direction == "UP":
        counter = ["RECLAIM_BELOW_LIQUIDITY_LEVEL", "OPPOSITE_LOW_LIQUIDITY_TAKEN_WOULD_CHALLENGE_BULLISH_THESIS"]
    else:
        counter = ["RECLAIM_ABOVE_LIQUIDITY_LEVEL", "OPPOSITE_HIGH_LIQUIDITY_TAKEN_WOULD_CHALLENGE_BEARISH_THESIS"]

    if confirmed:
        finding = f"{event['type']}_CONFIRMED"
        quality = "HIGH_CONVICTION" if event.get("zone", {}).get("touches", 1) >= 2 and event.get("strength", 0) >= 0.9 and auction["follow_through_bars"] >= 2 else "CONFIRMED"
    elif event.get("zone"):
        finding = event["type"]
        quality = "PENDING" if auction["state"] not in {"INVALIDATED"} else "INVALIDATED"
    else:
        finding = "NO_CONFIRMED_LIQUIDITY_EVENT"
        quality = "UNRESOLVED"

    observations = [
        f"closed_candles={len(bars)}",
        f"atr14={atr:.6f}",
        f"high_liquidity_zones={len(high_zones)}",
        f"low_liquidity_zones={len(low_zones)}",
        f"event={event['type']}",
        f"liquidity_taker={event.get('liquidity_taker', 'NONE')}",
        f"auction_state={auction['state']}",
        f"follow_through_bars={auction['follow_through_bars']}",
        f"contextual_direction_hint={context}",
    ]
    return {**base, "state": "ANALYSIS_COMPLETE", "analysis_status": "COMPLETE", "finding": finding, "direction": direction, "directional_implication": direction, "direction_confirmed": confirmed, "confidence": round(event.get("strength", 0.30) if confirmed else min(event.get("strength", 0.30), 0.45), 3), "evidence_strength": round(event.get("strength", 0.30), 3), "observations": observations, "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones}, "event": event, "auction": auction, "auction_state": auction["state"], "follow_through": follow, "follow_through_bars": auction["follow_through_bars"], "auction_confirmation": {"confirmed": confirmed, "state": auction["state"]}, "auction_confirmation_state": auction["state"], "auction_quality": quality, "counter_evidence": counter, "invalidation": ["newer confirmed liquidity event supersedes current event", "post-event close through the defended liquidity level invalidates the thesis"], "reasons": [] if confirmed else ["AUCTION_RESPONSE_NOT_CONFIRMED"]}


__all__ = ["analyze_e4"]
