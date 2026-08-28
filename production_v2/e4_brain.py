from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V20"
MIN_BARS = 30
PIVOT_WING = 2
LOOKBACK_PIVOTS = 80
MIN_EVENT_LOOKBACK = 6
MAX_EVENT_AGE = 8
MIN_CONFIRM_BARS = 1
MAX_CONFIRM_BARS = 6
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
    result: list[dict[str, Any]] = []
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
    tr: list[float] = []
    for i in range(1, len(bars)):
        h, low, pc = float(bars[i]["high"]), float(bars[i]["low"]), float(bars[i - 1]["close"])
        tr.append(max(h - low, abs(h - pc), abs(low - pc)))
    return mean(tr[-period:]) if tr else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = PIVOT_WING):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, float(bars[i]["high"])))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, float(bars[i]["low"])))
    return highs, lows


def _cluster(levels, tolerance: float, side: str, current: int):
    groups: list[list[tuple[int, float]]] = []
    for item in sorted(levels, key=lambda pair: pair[1]):
        if not groups or abs(item[1] - mean(price for _, price in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    zones = []
    for group in groups:
        prices = [price for _, price in group]
        last = max(i for i, _ in group)
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
        for i in range(zone["last_touch_index"] + 1, len(bars)):
            bar = bars[i]
            crossed = (bar["high"] > zone["upper"] + threshold if zone["side"] == "HIGH" else bar["low"] < zone["lower"] - threshold)
            if crossed:
                takes.append(i)
        latest = takes[-1] if takes else None
        z.update({
            "liquidity_taken": latest is not None,
            "taken_index": latest,
            "take_count": len(takes),
            "recently_taken": latest is not None and current - latest <= MAX_EVENT_AGE,
            "state": "TAKEN" if latest is not None and current - latest <= MAX_EVENT_AGE else "CONSUMED" if latest is not None else zone["freshness"],
        })
        result.append(z)
    return result


def _body_ratio(bar):
    return abs(float(bar["close"]) - float(bar["open"])) / max(float(bar["high"]) - float(bar["low"]), 1e-12)


def _candle_geometry(bar):
    span = max(float(bar["high"]) - float(bar["low"]), 1e-12)
    body = _body_ratio(bar)
    upper = (float(bar["high"]) - max(float(bar["open"]), float(bar["close"]))) / span
    lower = (min(float(bar["open"]), float(bar["close"])) - float(bar["low"])) / span
    return {"body_ratio": round(body, 4), "upper_wick_ratio": round(upper, 4), "lower_wick_ratio": round(lower, 4), "range": span}


def _event_for_zone(bars, zone, atr, index):
    if index <= int(zone.get("last_touch_index", -1)):
        return None
    bar = bars[index]
    previous = bars[index - 1]
    level = float(zone["upper"] if zone["side"] == "HIGH" else zone["lower"])
    geometry = _candle_geometry(bar)
    sweep = max(atr * INTERACTION_ATR, 1e-9)
    close_band = max(atr * REJECTION_CLOSE_ATR, 1e-9)
    extension = max(atr * ACCEPTANCE_ATR, 1e-9)

    if zone["side"] == "HIGH":
        swept = bar["high"] > level + sweep
        rejection = swept and bar["close"] <= level + close_band and geometry["upper_wick_ratio"] >= MIN_WICK_RATIO
        failed = previous["close"] > level + extension and bar["close"] <= level + close_band
        acceptance = previous["close"] <= level + close_band and bar["close"] > level + extension and geometry["body_ratio"] >= MIN_BODY_RATIO
        if failed:
            kind, direction, strength, state = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", 0.94, "FAILED_BREAK_RECLAIM"
        elif rejection:
            kind, direction, strength, state = "HIGH_SWEEP_REJECTION", "DOWN", 0.95, "REJECTION"
        elif acceptance:
            kind, direction, strength, state = "HIGH_ACCEPTANCE_CANDIDATE", "UP", 0.88, "ACCEPTANCE"
        elif swept:
            kind, direction, strength, state = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", 0.55, "INTERACTION"
        else:
            return None
        taker = "BUY_SIDE_PRESSURE_INFERENCE"
        response = "SELL_SIDE_RESPONSE_INFERENCE" if direction == "DOWN" else "BUY_SIDE_CONTINUATION_INFERENCE" if direction == "UP" else "UNRESOLVED_PRICE_RESPONSE"
    else:
        swept = bar["low"] < level - sweep
        rejection = swept and bar["close"] >= level - close_band and geometry["lower_wick_ratio"] >= MIN_WICK_RATIO
        failed = previous["close"] < level - extension and bar["close"] >= level - close_band
        acceptance = previous["close"] >= level - close_band and bar["close"] < level - extension and geometry["body_ratio"] >= MIN_BODY_RATIO
        if failed:
            kind, direction, strength, state = "LOW_FAILED_BREAK_RECLAIM", "UP", 0.94, "FAILED_BREAK_RECLAIM"
        elif rejection:
            kind, direction, strength, state = "LOW_SWEEP_REJECTION", "UP", 0.95, "REJECTION"
        elif acceptance:
            kind, direction, strength, state = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", 0.88, "ACCEPTANCE"
        elif swept:
            kind, direction, strength, state = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", 0.55, "INTERACTION"
        else:
            return None
        taker = "SELL_SIDE_PRESSURE_INFERENCE"
        response = "BUY_SIDE_RESPONSE_INFERENCE" if direction == "UP" else "SELL_SIDE_CONTINUATION_INFERENCE" if direction == "DOWN" else "UNRESOLVED_PRICE_RESPONSE"

    return {
        "type": kind,
        "auction_state": state,
        "directional_implication": direction,
        "liquidity_state": "REJECTED" if state == "REJECTION" else "RECLAIMED" if state == "FAILED_BREAK_RECLAIM" else "ACCEPTANCE_CANDIDATE" if state == "ACCEPTANCE" else "TAKEN",
        "liquidity_taker": taker,
        "response_actor": response,
        "actor_evidence_type": "PRICE_ACTION_INFERENCE_ONLY",
        "strength": strength,
        "zone": zone,
        "index": index,
        "level": level,
        "event_candle": {key: float(bar[key]) for key in ("open", "high", "low", "close")},
        "candle_geometry": geometry,
    }


def _find_recent_event(bars, high_zones, low_zones, atr):
    current = len(bars) - 1
    candidates = []
    start = max(1, current - MIN_EVENT_LOOKBACK)
    for index in range(start, current + 1):
        for zone in high_zones + low_zones:
            event = _event_for_zone(bars, zone, atr, index)
            if event:
                candidates.append((index, int(zone.get("touches", 1)), event))
    if not candidates:
        return {"type": "NO_LIQUIDITY_EVENT", "auction_state": "UNRESOLVED", "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "liquidity_taker": "NONE", "response_actor": "NONE", "actor_evidence_type": "NONE", "strength": 0.30, "zone": None, "index": current}
    def priority(item):
        event = item[2]
        state = event.get("auction_state")
        quality = 3 if state in {"REJECTION", "ACCEPTANCE", "FAILED_BREAK_RECLAIM"} else 1
        return quality, item[0], item[1], event["strength"]
    return max(candidates, key=priority)[2]


def _adaptive_horizon(event, bars, atr):
    geometry = event.get("candle_geometry") or {}
    body = float(geometry.get("body_ratio", 0.0))
    level = float(event.get("level", 0.0))
    candle = event.get("event_candle") or {}
    displacement = abs(float(candle.get("close", level)) - level) / max(atr, 1e-9)
    if displacement >= 1.0 or body >= 0.80:
        return 2
    if displacement >= 0.50 or body >= 0.65:
        return 3
    if displacement >= 0.25:
        return 4
    return 5


def _follow_through(event, bars, atr):
    index = int(event.get("index", -1))
    zone = event.get("zone") or {}
    if index < 0 or index >= len(bars) - 1 or not zone:
        return {"present": False, "bars": 0, "reason": "NO_POST_EVENT_CANDLE", "invalidated": False, "expired": False, "checks": [], "required_bars": 0}
    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    level = float(event.get("level", zone.get("price", 0.0)))
    origin = float(bars[index]["close"])
    horizon = min(MAX_CONFIRM_BARS, _adaptive_horizon(event, bars, atr))
    distance = max(atr * INTERACTION_ATR, 1e-9)
    checks = []
    supportive = 0
    invalidated = False
    for j in range(index + 1, min(len(bars), index + horizon + 1)):
        bar = bars[j]
        close = float(bar["close"])
        geometry = _candle_geometry(bar)
        if direction == "DOWN":
            held = close < level - distance
            away = close < origin - distance
            opposite_reclaim = close > level + distance
            meaningful = held and (away or geometry["body_ratio"] >= 0.45)
        elif direction == "UP":
            held = close > level + distance
            away = close > origin + distance
            opposite_reclaim = close < level - distance
            meaningful = held and (away or geometry["body_ratio"] >= 0.45)
        else:
            held = away = opposite_reclaim = meaningful = False
        if opposite_reclaim:
            invalidated = True
        if meaningful and not opposite_reclaim:
            supportive += 1
        checks.append({"index": j, "close": close, "body_ratio": geometry["body_ratio"], "held": held, "meaningful": meaningful, "opposite_reclaim": opposite_reclaim})
    available = len(checks)
    required = MIN_CONFIRM_BARS
    present = supportive >= required and not invalidated
    expired = not present and not invalidated and available >= horizon
    return {"present": present, "bars": supportive, "available_bars": available, "required_bars": required, "horizon_bars": horizon, "reason": "FOLLOW_THROUGH_OBSERVED" if present else "EVENT_EXPIRED" if expired else "FOLLOW_THROUGH_ABSENT", "invalidated": invalidated, "expired": expired, "checks": checks}


def _auction_confirmation(event, bars, atr):
    if not event.get("zone"):
        return {"state": "UNRESOLVED", "confirmed": False, "follow_through": False, "follow_through_bars": 0, "reason": "NO_EVENT", "lifecycle": "NO_EVENT"}
    follow = _follow_through(event, bars, atr)
    base = event.get("auction_state")
    if follow["invalidated"]:
        state, confirmed, lifecycle = "INVALIDATED", False, "INVALIDATED"
    elif follow["expired"]:
        state, confirmed, lifecycle = "EXPIRED", False, "EXPIRED"
    elif follow["present"]:
        state = {"REJECTION": "REJECTION_CONFIRMED", "ACCEPTANCE": "ACCEPTANCE_CONFIRMED", "FAILED_BREAK_RECLAIM": "REJECTION_CONFIRMED"}.get(base, "UNRESOLVED")
        confirmed, lifecycle = state != "UNRESOLVED", "CONFIRMED" if state != "UNRESOLVED" else "PENDING"
    else:
        state = {"REJECTION": "REJECTION_PENDING", "ACCEPTANCE": "ACCEPTANCE_PENDING", "FAILED_BREAK_RECLAIM": "REJECTION_PENDING"}.get(base, "UNRESOLVED")
        confirmed, lifecycle = False, "PENDING"
    return {"state": state, "confirmed": confirmed, "follow_through": follow["present"], "follow_through_bars": follow["bars"], "reason": "POST_EVENT_RECLAMATION" if follow["invalidated"] else follow["reason"], "lifecycle": lifecycle, "detail": follow}


def _context_hint(evidence_bus):
    # E1-E3 are contextual hints only; they never determine E4's thesis.
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


def _audit(event, auction, bars, atr, context, high_zones, low_zones):
    zone = event.get("zone") or {}
    candle = event.get("event_candle") or {}
    return [
        f"closed_candles={len(bars)}",
        f"atr14={atr:.6f}",
        f"liquidity_map_high_zones={len(high_zones)}",
        f"liquidity_map_low_zones={len(low_zones)}",
        f"liquidity_side={zone.get('side', 'NONE')}",
        f"liquidity_level={event.get('level', zone.get('price', 0.0)):.6f}" if zone else "liquidity_level=NONE",
        f"liquidity_kind={zone.get('kind', 'NONE')}",
        f"touches={zone.get('touches', 0)}",
        f"age_bars={zone.get('age_bars', 0)}",
        f"freshness={zone.get('freshness', 'NONE')}",
        f"event_index={event.get('index', len(bars) - 1)}",
        f"event={event.get('type', 'NONE')}",
        f"event_close={float(candle.get('close', 0.0)):.6f}",
        f"actor_evidence={event.get('actor_evidence_type', 'NONE')}",
        f"liquidity_taker_inference={event.get('liquidity_taker', 'NONE')}",
        f"response_inference={event.get('response_actor', 'NONE')}",
        f"auction_state={auction.get('state', 'UNRESOLVED')}",
        f"lifecycle={auction.get('lifecycle', 'UNRESOLVED')}",
        f"follow_through_bars={auction.get('follow_through_bars', 0)}",
        f"follow_through_horizon={((auction.get('detail') or {}).get('horizon_bars', 0))}",
        f"contextual_hint={context}",
    ]


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
        return {**base, "state": "UNAVAILABLE", "analysis_status": "INCOMPLETE", "finding": "LIQUIDITY_DATA_INSUFFICIENT", "direction": "NEUTRAL", "directional_implication": "NEUTRAL", "direction_confirmed": False, "confidence": 0.0, "evidence_strength": 0.0, "observations": [f"closed_candles={len(bars)}", f"atr14={atr:.6f}"], "liquidity_map": {}, "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"}, "auction": {"state": "UNRESOLVED", "confirmed": False}, "auction_state": "UNRESOLVED", "follow_through": {"present": False}, "follow_through_bars": 0, "auction_confirmation": {"confirmed": False}, "auction_confirmation_state": "UNRESOLVED", "auction_quality": "UNRESOLVED", "counter_evidence": ["INSUFFICIENT_DATA"], "invalidation": ["new closed-candle data"], "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"]}

    current = len(bars) - 1
    pivot_highs, pivot_lows = _pivots(bars)
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    high_zones = _consume(_cluster(pivot_highs[-LOOKBACK_PIVOTS:], tolerance, "HIGH", current), bars, atr)
    low_zones = _consume(_cluster(pivot_lows[-LOOKBACK_PIVOTS:], tolerance, "LOW", current), bars, atr)
    event = _find_recent_event(bars, high_zones, low_zones, atr)
    auction = _auction_confirmation(event, bars, atr)
    confirmed = bool(auction["confirmed"])
    direction = event.get("directional_implication", "NEUTRAL") if confirmed else "NEUTRAL"
    follow = auction.get("detail") or {"present": False, "bars": 0}

    if auction["state"] == "INVALIDATED":
        counter = ["POST_EVENT_RECLAMATION", "ORIGINAL_AUCTION_THESIS_REJECTED"]
    elif auction["state"] == "EXPIRED":
        counter = ["NO_SUFFICIENT_FOLLOW_THROUGH_BEFORE_EVENT_EXPIRY", "THESIS_EXPIRED"]
    elif not event.get("zone"):
        counter = ["NO_LIQUIDITY_EVENT"]
    elif not confirmed:
        counter = ["NO_FOLLOW_THROUGH", "AUCTION_DIRECTION_REMAINS_UNRESOLVED"]
    elif direction == "UP":
        counter = ["RECLAIM_BELOW_LIQUIDITY_LEVEL", "OPPOSITE_HIGHER_QUALITY_LOW_EVENT_CHALLENGES_BULLISH_THESIS"]
    else:
        counter = ["RECLAIM_ABOVE_LIQUIDITY_LEVEL", "OPPOSITE_HIGHER_QUALITY_HIGH_EVENT_CHALLENGES_BEARISH_THESIS"]

    if confirmed:
        finding = f"{event['type']}_CONFIRMED"
        quality = "HIGH_CONVICTION" if event.get("zone", {}).get("touches", 1) >= 2 and event.get("strength", 0) >= 0.9 and auction["follow_through_bars"] >= 2 else "CONFIRMED"
    elif event.get("zone"):
        finding = event["type"]
        quality = "INVALIDATED" if auction["state"] == "INVALIDATED" else "EXPIRED" if auction["state"] == "EXPIRED" else "PENDING"
    else:
        finding, quality = "NO_LIQUIDITY_EVENT", "UNRESOLVED"

    observations = _audit(event, auction, bars, atr, context, high_zones, low_zones)
    observations.extend([
        f"event_directional_implication={event.get('directional_implication', 'NEUTRAL')}",
        f"direction_confirmed={confirmed}",
        f"counter_evidence_count={len(counter)}",
        "actor_identification=INFERENCE_FROM_PRICE_ACTION_NOT_ORDER_FLOW",
    ])
    return {
        **base,
        "state": "ANALYSIS_COMPLETE",
        "analysis_status": "COMPLETE",
        "finding": finding,
        "direction": direction,
        "directional_implication": direction,
        "direction_confirmed": confirmed,
        "confidence": round(event.get("strength", 0.30) if confirmed else min(event.get("strength", 0.30), 0.45), 3),
        "evidence_strength": round(event.get("strength", 0.30), 3),
        "observations": observations,
        "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones},
        "event": event,
        "auction": auction,
        "auction_state": auction["state"],
        "follow_through": follow,
        "follow_through_bars": auction["follow_through_bars"],
        "auction_confirmation": {"confirmed": confirmed, "state": auction["state"]},
        "auction_confirmation_state": auction["state"],
        "auction_quality": quality,
        "counter_evidence": counter,
        "invalidation": ["newer confirmed liquidity event supersedes current event", "post-event close through defended liquidity level invalidates the thesis", "event expiry without sufficient follow-through invalidates confirmation"],
        "reasons": [] if confirmed else ["AUCTION_RESPONSE_NOT_CONFIRMED" if auction["state"] not in {"INVALIDATED", "EXPIRED"} else auction["state"]],
    }


__all__ = ["analyze_e4"]
