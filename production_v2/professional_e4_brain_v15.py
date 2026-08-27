"""Production-V2 E4 Professional Liquidity & Auction Brain.

E4 is an analysis-only market specialist. It answers one professional question:
where liquidity is, who took it, what auction event occurred, whether price was
accepted or rejected, and whether post-event follow-through actually confirms
that interpretation. E4 never issues a trade decision; E9 remains authoritative.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V17"
MIN_BARS = 30
PIVOT_WING = 2
LOOKBACK_PIVOTS = 60
FOLLOW_WINDOW = 3
ZONE_TOLERANCE_ATR = 0.15
SWEEP_ATR = 0.05
CLOSE_TOLERANCE_ATR = 0.10
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
    if isinstance(source, dict):
        source = source.get("bars") or []
    result: list[dict[str, Any]] = []
    for raw in source if isinstance(source, (list, tuple)) else []:
        if not isinstance(raw, dict):
            continue
        values = {key: _num(raw.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            continue
        if values["high"] < max(values["open"], values["close"]):
            continue
        if values["low"] > min(values["open"], values["close"]):
            continue
        if values["high"] < values["low"]:
            continue
        result.append({**raw, **values})
    return result


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    true_ranges = []
    for index in range(1, len(bars)):
        high = float(bars[index]["high"])
        low = float(bars[index]["low"])
        previous_close = float(bars[index - 1]["close"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(true_ranges[-period:]) if true_ranges else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = PIVOT_WING):
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for index in range(wing, len(bars) - wing):
        window = bars[index - wing:index + wing + 1]
        high = float(bars[index]["high"])
        low = float(bars[index]["low"])
        if high >= max(float(item["high"]) for item in window):
            highs.append((index, high))
        if low <= min(float(item["low"]) for item in window):
            lows.append((index, low))
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
        last_touch = max(index for index, _ in group)
        age = max(0, current - last_touch)
        touches = len(group)
        zones.append({
            "side": side,
            "price": mean(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": touches,
            "last_touch_index": last_touch,
            "age_bars": age,
            "kind": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "hierarchy": "EQUAL_LEVEL" if touches >= 2 else "SWING_LEVEL",
            "freshness": "FRESH" if age <= 24 else "AGED",
        })
    return zones


def _zone_history(zone, bars, atr):
    z = dict(zone)
    threshold = max(atr * SWEEP_ATR, 1e-9)
    takes = []
    start = int(zone.get("last_touch_index", -1)) + 1
    for index in range(start, len(bars)):
        bar = bars[index]
        crossed = (
            float(bar["high"]) > float(zone["upper"]) + threshold
            if zone["side"] == "HIGH"
            else float(bar["low"]) < float(zone["lower"]) - threshold
        )
        if crossed:
            takes.append(index)
    latest = takes[-1] if takes else None
    current = len(bars) - 1
    z.update({
        "liquidity_taken": latest is not None,
        "taken_index": latest,
        "take_count": len(takes),
        "recently_taken": latest is not None and current - latest <= FOLLOW_WINDOW,
        "state": (
            "TAKEN" if latest is not None and current - latest <= FOLLOW_WINDOW
            else "CONSUMED" if latest is not None
            else zone["freshness"]
        ),
    })
    return z


def _body_ratio(bar) -> float:
    return abs(float(bar["close"]) - float(bar["open"])) / max(float(bar["high"]) - float(bar["low"]), 1e-12)


def _event_for_zone(bars, zone, atr, index):
    if index <= int(zone.get("last_touch_index", -1)):
        return None
    taken = zone.get("taken_index")
    if (zone.get("state") == "CONSUMED" or zone.get("consumed") is True) and taken is not None and index > int(taken):
        return None

    bar = bars[index]
    previous = bars[index - 1]
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    previous_close = float(previous["close"])
    span = max(high - low, 1e-12)
    upper_wick = (high - max(float(bar["open"]), close)) / span
    lower_wick = (min(float(bar["open"]), close) - low) / span
    sweep = max(atr * SWEEP_ATR, 1e-9)
    band = max(atr * CLOSE_TOLERANCE_ATR, 1e-9)
    extension = max(atr * ACCEPTANCE_ATR, 1e-9)
    level = float(zone["upper"] if zone["side"] == "HIGH" else zone["lower"])

    if zone["side"] == "HIGH":
        swept = high > level + sweep
        rejection = swept and close <= level + band and upper_wick >= MIN_WICK_RATIO
        failed_break = previous_close > level + extension and close <= level + band
        acceptance = close > level + extension and _body_ratio(bar) >= MIN_BODY_RATIO
        if failed_break:
            kind, implication, taker, actor, strength = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "BUYERS", "SELLERS", 0.94
        elif rejection:
            kind, implication, taker, actor, strength = "HIGH_SWEEP_REJECTION", "DOWN", "BUYERS", "SELLERS", 0.95
        elif acceptance:
            kind, implication, taker, actor, strength = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "BUYERS", "BUYERS", 0.88
        elif swept:
            kind, implication, taker, actor, strength = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "BUYERS", "UNCLEAR", 0.55
        else:
            return None
    else:
        swept = low < level - sweep
        rejection = swept and close >= level - band and lower_wick >= MIN_WICK_RATIO
        failed_break = previous_close < level - extension and close >= level - band
        acceptance = close < level - extension and _body_ratio(bar) >= MIN_BODY_RATIO
        if failed_break:
            kind, implication, taker, actor, strength = "LOW_FAILED_BREAK_RECLAIM", "UP", "SELLERS", "BUYERS", 0.94
        elif rejection:
            kind, implication, taker, actor, strength = "LOW_SWEEP_REJECTION", "UP", "SELLERS", "BUYERS", 0.95
        elif acceptance:
            kind, implication, taker, actor, strength = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "SELLERS", "SELLERS", 0.88
        elif swept:
            kind, implication, taker, actor, strength = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "SELLERS", "UNCLEAR", 0.55
        else:
            return None

    event_state = (
        "REJECTION_CANDIDATE" if "REJECTION" in kind
        else "FAILED_BREAK_RECLAIM_CANDIDATE" if "FAILED_BREAK" in kind
        else "ACCEPTANCE_CANDIDATE" if "ACCEPTANCE_CANDIDATE" in kind
        else "TAKEN"
    )
    return {
        "type": kind,
        "auction_state": event_state,
        "directional_implication": implication,
        "liquidity_state": "REJECTED" if "REJECTION" in kind else "RECLAIMED" if "FAILED_BREAK" in kind else "ACCEPTANCE_CANDIDATE" if "ACCEPTANCE_CANDIDATE" in kind else "TAKEN",
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
                candidates.append(((index, float(event["strength"]), int(zone.get("touches", 1))), event))
    if not candidates:
        return {
            "type": "NO_CONFIRMED_LIQUIDITY_EVENT",
            "auction_state": "UNRESOLVED",
            "directional_implication": "NEUTRAL",
            "liquidity_state": "UNRESOLVED",
            "liquidity_taker": "NONE",
            "response_actor": "NONE",
            "strength": 0.30,
            "zone": None,
            "index": current,
        }
    return max(candidates, key=lambda item: item[0])[1]


def _follow_through(event, bars, atr):
    index = int(event.get("index", -1))
    zone = event.get("zone") or {}
    if index < 0 or index >= len(bars) - 1 or not zone:
        return {"present": False, "bars": 0, "reason": "NO_POST_EVENT_CANDLE", "invalidated": False, "checks": []}

    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    event_close = float(bars[index]["close"])
    upper = float(zone.get("upper", event_close))
    lower = float(zone.get("lower", event_close))
    distance = max(atr * SWEEP_ATR, 1e-9)
    count = 0
    invalidated = False
    checks = []

    for current_index in range(index + 1, min(len(bars), index + FOLLOW_WINDOW + 1)):
        close = float(bars[current_index]["close"])
        if direction == "DOWN":
            away = close < event_close - distance
            held = close < upper - distance
            reclaimed = close > upper + distance
        elif direction == "UP":
            away = close > event_close + distance
            held = close > lower + distance
            reclaimed = close < lower - distance
        else:
            away = held = reclaimed = False
        if reclaimed:
            invalidated = True
        confirmed = away and held and not reclaimed
        if confirmed:
            count += 1
        checks.append({"index": current_index, "close": close, "confirmed": confirmed, "reclaimed": reclaimed})

    present = count >= 1 and not invalidated
    return {
        "present": present,
        "bars": count,
        "reason": "FOLLOW_THROUGH_OBSERVED" if present else "FOLLOW_THROUGH_ABSENT",
        "invalidated": invalidated,
        "checks": checks,
    }


def _auction_confirmation(event, bars, atr):
    if not event or not event.get("zone"):
        return {"state": "UNRESOLVED", "confirmed": False, "follow_through": False, "follow_through_bars": 0, "reason": "NO_EVENT"}

    follow = _follow_through(event, bars, atr)
    kind = str(event.get("type") or "")
    event_state = (
        "FAILED_BREAK_RECLAIM" if "FAILED_BREAK" in kind
        else "REJECTION" if "REJECTION" in kind
        else "ACCEPTANCE" if "ACCEPTANCE_CANDIDATE" in kind
        else "UNRESOLVED"
    )

    if follow["invalidated"]:
        return {
            "state": "INVALIDATED",
            "confirmed": False,
            "follow_through": False,
            "follow_through_bars": follow["bars"],
            "reason": "POST_EVENT_RECLAMATION",
            "detail": follow,
        }
    if follow["present"]:
        final = (
            "REJECTION_CONFIRMED" if event_state in {"REJECTION", "FAILED_BREAK_RECLAIM"}
            else "ACCEPTANCE_CONFIRMED" if event_state == "ACCEPTANCE"
            else "UNRESOLVED"
        )
        return {
            "state": final,
            "confirmed": final != "UNRESOLVED",
            "follow_through": True,
            "follow_through_bars": follow["bars"],
            "reason": "FOLLOW_THROUGH_OBSERVED",
            "detail": follow,
        }

    pending = (
        "REJECTION_PENDING" if event_state in {"REJECTION", "FAILED_BREAK_RECLAIM"}
        else "ACCEPTANCE_PENDING" if event_state == "ACCEPTANCE"
        else "UNRESOLVED"
    )
    return {
        "state": pending,
        "confirmed": False,
        "follow_through": False,
        "follow_through_bars": follow["bars"],
        "reason": follow["reason"],
        "detail": follow,
    }


def _context_hint(bus):
    votes = []
    for engine_id in ("E1", "E2", "E3"):
        package = (bus or {}).get(engine_id, {})
        evidence = package.get("evidence", package) if isinstance(package, dict) else {}
        output = evidence.get("output", evidence) if isinstance(evidence, dict) else evidence
        text = str(output).upper()
        if any(token in text for token in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "UP_EVIDENCE")):
            votes.append("UP")
        if any(token in text for token in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DOWN_EVIDENCE")):
            votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


def _finding_for(event, confirmation):
    kind = str(event.get("type") or "NO_CONFIRMED_LIQUIDITY_EVENT")
    state = str(confirmation.get("state") or "UNRESOLVED")
    if "ACCEPTANCE_CANDIDATE" in kind:
        return "HIGH_ACCEPTANCE_CONFIRMED" if state == "ACCEPTANCE_CONFIRMED" else "HIGH_ACCEPTANCE_PENDING" if kind.startswith("HIGH") else "LOW_ACCEPTANCE_CONFIRMED" if state == "ACCEPTANCE_CONFIRMED" else "LOW_ACCEPTANCE_PENDING"
    if "SWEEP_REJECTION" in kind:
        return "HIGH_SWEEP_REJECTION_CONFIRMED" if state == "REJECTION_CONFIRMED" else "HIGH_SWEEP_REJECTION_PENDING" if kind.startswith("HIGH") else "LOW_SWEEP_REJECTION_CONFIRMED" if state == "REJECTION_CONFIRMED" else "LOW_SWEEP_REJECTION_PENDING"
    if "FAILED_BREAK_RECLAIM" in kind:
        return "HIGH_FAILED_BREAK_RECLAIM_CONFIRMED" if state == "REJECTION_CONFIRMED" else "HIGH_FAILED_BREAK_RECLAIM_PENDING" if kind.startswith("HIGH") else "LOW_FAILED_BREAK_RECLAIM_CONFIRMED" if state == "REJECTION_CONFIRMED" else "LOW_FAILED_BREAK_RECLAIM_PENDING"
    return kind


def analyze_e4(snapshot=None, evidence_bus=None):
    bars = _bars(snapshot)
    atr = _atr(bars)
    context = _context_hint(evidence_bus)
    base = {
        "architecture": ARCHITECTURE,
        "professional_brain": True,
        "role": E4_ROLE,
        "question": PROFESSIONAL_QUESTION,
        "specialists": {},
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
        "evidence": {
            "raw_market_data_used": True,
            "decisions_used": False,
            "gates_used": False,
            "scores_used": False,
        },
    }
    context_used = {engine_id: bool((evidence_bus or {}).get(engine_id)) for engine_id in ("E1", "E2", "E3")}

    if len(bars) < MIN_BARS or atr <= 0:
        return {
            **base,
            "state": "UNAVAILABLE",
            "analysis_status": "INCOMPLETE",
            "finding": "LIQUIDITY_DATA_INSUFFICIENT",
            "direction": "NEUTRAL",
            "directional_implication": "NEUTRAL",
            "direction_confirmed": False,
            "confidence": 0.0,
            "evidence_strength": 0.0,
            "observations": [],
            "liquidity_map": {},
            "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"},
            "auction": {"state": "UNRESOLVED", "confirmed": False, "follow_through": False, "follow_through_bars": 0},
            "auction_state": "UNRESOLVED",
            "follow_through": {"present": False, "bars": 0},
            "follow_through_bars": 0,
            "auction_confirmation": {"confirmed": False},
            "auction_confirmation_state": "UNRESOLVED",
            "interaction": {},
            "context_used": context_used,
            "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"],
            "conflicts": [],
            "missing_evidence": ["CLOSED_CANDLE_HISTORY"],
        }

    current = len(bars) - 1
    high_pivots, low_pivots = _pivots(bars)
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    high_zones = [_zone_history(zone, bars, atr) for zone in _cluster(high_pivots[-LOOKBACK_PIVOTS:], tolerance, "HIGH", current)]
    low_zones = [_zone_history(zone, bars, atr) for zone in _cluster(low_pivots[-LOOKBACK_PIVOTS:], tolerance, "LOW", current)]
    event = _find_recent_event(bars, high_zones, low_zones, atr)
    confirmation = _auction_confirmation(event, bars, atr)
    confirmed = bool(confirmation["confirmed"])
    implication = str(event.get("directional_implication") or "NEUTRAL")
    direction = implication if confirmed else "NEUTRAL"
    finding = _finding_for(event, confirmation)
    follow = confirmation.get("detail") or _follow_through(event, bars, atr)

    fresh_high = sum(1 for zone in high_zones if zone["freshness"] == "FRESH" and not zone["liquidity_taken"])
    fresh_low = sum(1 for zone in low_zones if zone["freshness"] == "FRESH" and not zone["liquidity_taken"])
    price = float(bars[-1]["close"])
    nearest_high = min((zone for zone in high_zones if zone["price"] >= price), key=lambda zone: zone["price"], default=None)
    nearest_low = max((zone for zone in low_zones if zone["price"] <= price), key=lambda zone: zone["price"], default=None)

    reasons = (
        ["LIQUIDITY_EVENT_DETECTED", f"LIQUIDITY_TAKER={event.get('liquidity_taker', 'NONE')}", f"AUCTION_{confirmation['state']}"]
        if event.get("zone") else ["NO_CONFIRMED_LIQUIDITY_EVENT"]
    )
    if event.get("zone") and not confirmed:
        reasons.append("AUCTION_RESPONSE_NOT_CONFIRMED")
    if confirmed:
        reasons.append("AUCTION_RESPONSE_CONFIRMED")
    if confirmation["state"] == "INVALIDATED":
        reasons.append("POST_EVENT_RECLAMATION")

    missing = []
    if not event.get("zone"):
        missing.append("LIQUIDITY_EVENT")
    if not confirmed:
        missing.append("CONFIRMED_AUCTION_RESPONSE")

    observations = [
        f"closed_candles={len(bars)}",
        f"atr14={atr:.6f}",
        f"high_liquidity_zones={len(high_zones)}",
        f"low_liquidity_zones={len(low_zones)}",
        f"fresh_high_zones={fresh_high}",
        f"fresh_low_zones={fresh_low}",
        f"nearest_high={nearest_high['price']:.6f}" if nearest_high else "nearest_high=NONE",
        f"nearest_low={nearest_low['price']:.6f}" if nearest_low else "nearest_low=NONE",
        f"event={event['type']}",
        f"liquidity_taker={event.get('liquidity_taker', 'NONE')}",
        f"response_actor={event.get('response_actor', 'NONE')}",
        f"auction_state={confirmation['state']}",
        f"follow_through_bars={confirmation['follow_through_bars']}",
        f"contextual_direction={context}",
    ]

    return {
        **base,
        "state": "ANALYSIS_COMPLETE",
        "analysis_status": "COMPLETE",
        "finding": finding,
        "direction": direction,
        "directional_implication": implication,
        "direction_confirmed": confirmed,
        "confidence": round(event["strength"] if confirmed else min(event["strength"], 0.45), 3),
        "evidence_strength": round(event["strength"], 3),
        "observations": observations,
        "liquidity_map": {
            "high_zones": high_zones,
            "low_zones": low_zones,
            "fresh_high_zones": fresh_high,
            "fresh_low_zones": fresh_low,
        },
        "event": event,
        "auction": confirmation,
        "auction_state": confirmation["state"],
        "follow_through": follow,
        "follow_through_bars": confirmation["follow_through_bars"],
        "auction_confirmation": confirmation,
        "auction_confirmation_state": confirmation["state"],
        "interaction": {
            "liquidity_event": bool(event.get("zone")),
            "liquidity_taker": event.get("liquidity_taker", "NONE"),
            "response_actor": event.get("response_actor", "NONE"),
            "rejection": confirmation["state"].startswith("REJECTION"),
            "acceptance": confirmation["state"].startswith("ACCEPTANCE"),
            "failed_break_reclaim": "FAILED_BREAK" in event["type"],
            "confirmation_required": not confirmed,
        },
        "context_used": context_used,
        "reasons": reasons,
        "conflicts": [],
        "missing_evidence": missing,
        "professional_reasoning": {
            "question": PROFESSIONAL_QUESTION,
            "conclusion": finding,
            "liquidity_taker": event.get("liquidity_taker", "NONE"),
            "response_actor": event.get("response_actor", "NONE"),
            "auction_state": confirmation["state"],
            "directional_implication": implication,
            "direction_confirmed": confirmed,
            "follow_through_bars": confirmation["follow_through_bars"],
            "contextual_direction_hint": context,
            "upstream_decisions_used": False,
            "upstream_gates_used": False,
            "scores_used": False,
        },
    }


__all__ = ["analyze_e4", "_find_recent_event", "_follow_through"]
