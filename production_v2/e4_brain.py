from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V23"

MIN_BARS = 30
PIVOT_WING = 2
LOOKBACK_PIVOTS = 80
EVENT_LOOKBACK = 8
MAX_EVENT_AGE = 8
MAX_CONFIRM_BARS = 5

ZONE_TOLERANCE_ATR = 0.15
INTERACTION_ATR = 0.05
REJECTION_CLOSE_ATR = 0.10
ACCEPTANCE_ATR = 0.15
MIN_BODY_RATIO = 0.55
MIN_WICK_RATIO = 0.30

MIN_CONFIRM_BARS = 2
MIN_ACCEPT_DISPLACEMENT_ATR = 0.35
MIN_ACCEPT_BODY_RATIO = 0.55
MIN_FOLLOW_DISPLACEMENT_ATR = 0.20
MIN_FOLLOW_BODY_RATIO = 0.45
MIN_PIVOT_SEPARATION = 3


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _bars(source: Any) -> list[dict[str, Any]]:
    raw = source.get("bars") if isinstance(source, dict) else source
    out: list[dict[str, Any]] = []
    for b in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(b, dict):
            continue
        if b.get("closed") is False or b.get("is_closed") is False:
            continue
        v = {k: _num(b.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            continue
        if v["high"] < max(v["open"], v["close"]):
            continue
        if v["low"] > min(v["open"], v["close"]):
            continue
        if v["high"] < v["low"]:
            continue
        out.append({**b, **v})
    return out


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr: list[float] = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(tr[-period:]) if tr else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = PIVOT_WING):
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing : i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, float(bars[i]["high"])))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, float(bars[i]["low"])))
    return highs, lows


def _cluster(levels, tolerance: float, side: str, current: int):
    groups: list[list[tuple[int, float]]] = []
    for item in sorted(levels, key=lambda x: x[1]):
        if not groups:
            groups.append([item])
            continue
        center = mean(p for _, p in groups[-1])
        if abs(item[1] - center) <= tolerance:
            groups[-1].append(item)
        else:
            groups.append([item])

    zones = []
    for group in groups:
        indices = sorted(i for i, _ in group)
        prices = [p for _, p in group]
        last = max(indices)
        age = max(0, current - last)
        separated = sum(1 for a, b in zip(indices, indices[1:]) if b - a >= MIN_PIVOT_SEPARATION)
        if separated >= 2:
            kind = "CLUSTER_LIQUIDITY"
            hierarchy = "CLUSTER_LEVEL"
        elif len(indices) >= 2:
            kind = "EQUAL_LIQUIDITY"
            hierarchy = "EQUAL_LEVEL"
        else:
            kind = "SWING_LIQUIDITY"
            hierarchy = "SWING_LEVEL"
        zones.append(
            {
                "side": side,
                "price": mean(prices),
                "lower": min(prices),
                "upper": max(prices),
                "touches": len(indices),
                "distinct_touches": len(indices),
                "separated_touches": separated,
                "pivot_indices": indices,
                "last_touch_index": last,
                "age_bars": age,
                "kind": kind,
                "hierarchy": hierarchy,
                "freshness": "FRESH" if age <= 24 else "AGED",
            }
        )
    return zones


def _consume(zones, bars, atr: float):
    threshold = max(atr * INTERACTION_ATR, 1e-9)
    current = len(bars) - 1
    out = []
    for zone in zones:
        z = dict(zone)
        takes: list[int] = []
        for i in range(int(zone["last_touch_index"]) + 1, len(bars)):
            b = bars[i]
            crossed = (
                b["high"] > zone["upper"] + threshold
                if zone["side"] == "HIGH"
                else b["low"] < zone["lower"] - threshold
            )
            if crossed:
                takes.append(i)
        latest = takes[-1] if takes else None
        recent = latest is not None and current - latest <= MAX_EVENT_AGE
        z.update(
            {
                "liquidity_taken": latest is not None,
                "taken_index": latest,
                "take_count": len(takes),
                "recently_taken": recent,
                "state": "TAKEN" if recent else "CONSUMED" if latest is not None else zone["freshness"],
            }
        )
        out.append(z)
    return out


def _geometry(b):
    span = max(float(b["high"]) - float(b["low"]), 1e-12)
    body = abs(float(b["close"]) - float(b["open"])) / span
    return {
        "body_ratio": round(body, 4),
        "upper_wick_ratio": round((float(b["high"]) - max(float(b["open"]), float(b["close"]))) / span, 4),
        "lower_wick_ratio": round((min(float(b["open"]), float(b["close"])) - float(b["low"])) / span, 4),
        "range": round(span, 6),
    }


def _event_for_zone(bars, zone, atr: float, i: int):
    if i <= int(zone.get("last_touch_index", -1)):
        return None
    b = bars[i]
    prev = bars[i - 1]
    level = float(zone["upper"] if zone["side"] == "HIGH" else zone["lower"])
    g = _geometry(b)
    sweep = max(atr * INTERACTION_ATR, 1e-9)
    band = max(atr * REJECTION_CLOSE_ATR, 1e-9)
    ext = max(atr * ACCEPTANCE_ATR, 1e-9)

    if zone["side"] == "HIGH":
        swept = b["high"] > level + sweep
        rejection = swept and b["close"] <= level + band and g["upper_wick_ratio"] >= MIN_WICK_RATIO
        failed = prev["close"] > level + ext and b["close"] <= level + band
        acceptance = prev["close"] <= level + band and b["close"] > level + ext and g["body_ratio"] >= MIN_BODY_RATIO
        if failed:
            kind, direction, state = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "FAILED_BREAK_RECLAIM"
        elif rejection:
            kind, direction, state = "HIGH_SWEEP_REJECTION", "DOWN", "REJECTION"
        elif acceptance:
            kind, direction, state = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "ACCEPTANCE"
        elif swept:
            kind, direction, state = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "INTERACTION"
        else:
            return None
        taker = "BUY_SIDE_PRESSURE_INFERENCE"
        response = (
            "SELL_SIDE_RESPONSE_INFERENCE" if direction == "DOWN" else
            "BUY_SIDE_CONTINUATION_INFERENCE" if direction == "UP" else
            "UNRESOLVED_PRICE_RESPONSE"
        )
    else:
        swept = b["low"] < level - sweep
        rejection = swept and b["close"] >= level - band and g["lower_wick_ratio"] >= MIN_WICK_RATIO
        failed = prev["close"] < level - ext and b["close"] >= level - band
        acceptance = prev["close"] >= level - band and b["close"] < level - ext and g["body_ratio"] >= MIN_BODY_RATIO
        if failed:
            kind, direction, state = "LOW_FAILED_BREAK_RECLAIM", "UP", "FAILED_BREAK_RECLAIM"
        elif rejection:
            kind, direction, state = "LOW_SWEEP_REJECTION", "UP", "REJECTION"
        elif acceptance:
            kind, direction, state = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "ACCEPTANCE"
        elif swept:
            kind, direction, state = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "INTERACTION"
        else:
            return None
        taker = "SELL_SIDE_PRESSURE_INFERENCE"
        response = (
            "BUY_SIDE_RESPONSE_INFERENCE" if direction == "UP" else
            "SELL_SIDE_CONTINUATION_INFERENCE" if direction == "DOWN" else
            "UNRESOLVED_PRICE_RESPONSE"
        )

    return {
        "type": kind,
        "auction_state": state,
        "directional_implication": direction,
        "liquidity_state": (
            "REJECTED" if state == "REJECTION" else
            "RECLAIMED" if state == "FAILED_BREAK_RECLAIM" else
            "ACCEPTANCE_CANDIDATE" if state == "ACCEPTANCE" else
            "TAKEN"
        ),
        "liquidity_taker": taker,
        "response_actor": response,
        "actor_evidence_type": "PRICE_ACTION_INFERENCE_ONLY",
        "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW",
        "strength": 0.95 if state == "REJECTION" else 0.94 if state == "FAILED_BREAK_RECLAIM" else 0.88 if state == "ACCEPTANCE" else 0.55,
        "zone": zone,
        "index": i,
        "age_bars": len(bars) - 1 - i,
        "level": level,
        "event_candle": {k: float(b[k]) for k in ("open", "high", "low", "close")},
        "candle_geometry": g,
    }


def _find_recent_event(bars, highs, lows, atr: float):
    current = len(bars) - 1
    candidates = []
    for i in range(max(1, current - EVENT_LOOKBACK), current + 1):
        for zone in highs + lows:
            event = _event_for_zone(bars, zone, atr, i)
            if event and event["age_bars"] <= MAX_EVENT_AGE:
                candidates.append(event)
    if not candidates:
        return {
            "type": "NO_LIQUIDITY_EVENT",
            "auction_state": "UNRESOLVED",
            "directional_implication": "NEUTRAL",
            "liquidity_state": "UNRESOLVED",
            "liquidity_taker": "NONE",
            "response_actor": "NONE",
            "actor_evidence_type": "NONE",
            "strength": 0.30,
            "zone": None,
            "index": current,
            "age_bars": 0,
        }
    return max(
        candidates,
        key=lambda e: (
            int(e["index"]),
            int(e.get("zone", {}).get("separated_touches", 0)),
            int(e.get("zone", {}).get("touches", 1)),
            float(e.get("strength", 0)),
        ),
    )


def _adaptive_horizon(event, atr: float) -> int:
    g = event.get("candle_geometry") or {}
    c = event.get("event_candle") or {}
    level = float(event.get("level", 0.0))
    displacement = abs(float(c.get("close", level)) - level) / max(atr, 1e-9)
    body = float(g.get("body_ratio", 0.0))
    if displacement >= 1.0 or body >= 0.80:
        return 2
    if displacement >= 0.50 or body >= 0.65:
        return 3
    if displacement >= 0.25:
        return 4
    return 5


def _response_quality(event, bar, atr: float):
    direction = event.get("directional_implication", "NEUTRAL")
    level = float(event.get("level", 0.0))
    close = float(bar["close"])
    g = _geometry(bar)
    if direction == "UP":
        hold = close > level + atr * INTERACTION_ATR
        displacement = (close - level) / max(atr, 1e-9)
    elif direction == "DOWN":
        hold = close < level - atr * INTERACTION_ATR
        displacement = (level - close) / max(atr, 1e-9)
    else:
        hold = False
        displacement = 0.0
    meaningful = hold and displacement >= MIN_FOLLOW_DISPLACEMENT_ATR and g["body_ratio"] >= MIN_FOLLOW_BODY_RATIO
    return {
        "hold": hold,
        "displacement_atr": round(displacement, 4),
        "body_ratio": g["body_ratio"],
        "meaningful": meaningful,
        "geometry": g,
    }


def _follow_through(event, bars, atr: float):
    index = int(event.get("index", -1))
    zone = event.get("zone") or {}
    if index < 0 or index >= len(bars) - 1 or not zone:
        return {
            "present": False,
            "bars": 0,
            "available_bars": 0,
            "required_bars": MIN_CONFIRM_BARS,
            "consecutive_bars": 0,
            "horizon_bars": 0,
            "reason": "NO_POST_EVENT_CANDLE",
            "invalidated": False,
            "expired": False,
            "checks": [],
            "decisive_single": False,
            "acceptance_quality": event.get("auction_state") != "ACCEPTANCE",
        }

    horizon = min(MAX_CONFIRM_BARS, _adaptive_horizon(event, atr))
    direction = event.get("directional_implication", "NEUTRAL")
    level = float(event.get("level", zone.get("price", 0.0)))
    checks = []
    support = 0
    consecutive = 0
    invalidated = False

    for j in range(index + 1, min(len(bars), index + horizon + 1)):
        b = bars[j]
        q = _response_quality(event, b, atr)
        close = float(b["close"])
        opposite = (
            close < level - atr * INTERACTION_ATR if direction == "UP" else
            close > level + atr * INTERACTION_ATR if direction == "DOWN" else
            False
        )
        q.update({"index": j, "close": close, "opposite_reclaim": opposite})
        invalidated = invalidated or opposite
        if q["meaningful"] and not opposite:
            support += 1
            consecutive += 1
        else:
            consecutive = 0
        checks.append(q)

    available = len(checks)
    acceptance_quality = True
    if event.get("auction_state") == "ACCEPTANCE":
        meaningful = [x for x in checks if x.get("meaningful") and not x.get("opposite_reclaim")]
        strong = [
            x for x in meaningful
            if float(x.get("displacement_atr", 0.0)) >= MIN_ACCEPT_DISPLACEMENT_ATR
            and float(x.get("body_ratio", 0.0)) >= MIN_ACCEPT_BODY_RATIO
        ]
        acceptance_quality = consecutive >= MIN_CONFIRM_BARS and bool(strong)

    present = not invalidated and consecutive >= MIN_CONFIRM_BARS and acceptance_quality
    expired = not present and not invalidated and available >= horizon
    if present:
        reason = "FOLLOW_THROUGH_CONFIRMED"
    elif event.get("auction_state") == "ACCEPTANCE" and not expired:
        reason = "TRUE_ACCEPTANCE_NOT_PROVEN"
    elif expired:
        reason = "EVENT_EXPIRED"
    else:
        reason = "FOLLOW_THROUGH_ABSENT"

    return {
        "present": present,
        "bars": support,
        "available_bars": available,
        "required_bars": MIN_CONFIRM_BARS,
        "consecutive_bars": consecutive,
        "horizon_bars": horizon,
        "reason": reason,
        "invalidated": invalidated,
        "expired": expired,
        "checks": checks,
        "decisive_single": False,
        "acceptance_quality": acceptance_quality,
    }


def _auction_confirmation(event, bars, atr: float):
    if not event.get("zone"):
        return {
            "state": "UNRESOLVED",
            "confirmed": False,
            "follow_through": False,
            "follow_through_bars": 0,
            "reason": "NO_EVENT",
            "lifecycle": "NO_EVENT",
            "detail": {},
        }
    follow = _follow_through(event, bars, atr)
    base = event.get("auction_state")
    if follow["invalidated"]:
        state, confirmed, lifecycle = "INVALIDATED", False, "INVALIDATED"
    elif follow["expired"]:
        state, confirmed, lifecycle = "EXPIRED", False, "EXPIRED"
    elif follow["present"] and base in {"REJECTION", "ACCEPTANCE", "FAILED_BREAK_RECLAIM"}:
        state = "ACCEPTANCE_CONFIRMED" if base == "ACCEPTANCE" else "REJECTION_CONFIRMED"
        confirmed, lifecycle = True, "CONFIRMED"
    else:
        state = {
            "REJECTION": "REJECTION_PENDING",
            "ACCEPTANCE": "ACCEPTANCE_PENDING",
            "FAILED_BREAK_RECLAIM": "REJECTION_PENDING",
        }.get(base, "INTERACTION_PENDING")
        confirmed, lifecycle = False, "PENDING"
    return {
        "state": state,
        "confirmed": confirmed,
        "follow_through": follow["present"],
        "follow_through_bars": follow["bars"],
        "reason": follow["reason"] if not follow["invalidated"] else "POST_EVENT_RECLAMATION",
        "lifecycle": lifecycle,
        "detail": follow,
    }


def _context_hint(bus):
    votes = []
    for eid in ("E1", "E2", "E3"):
        p = (bus or {}).get(eid, {})
        e = p.get("evidence", p) if isinstance(p, dict) else {}
        o = e.get("output", e) if isinstance(e, dict) else e
        text = str(o).upper()
        if any(x in text for x in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "DIRECTION: UP", 'DIRECTION\": \"UP')):
            votes.append("UP")
        if any(x in text for x in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DIRECTION: DOWN", 'DIRECTION\": \"DOWN')):
            votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


def _audit(event, auction, bars, atr, context, highs, lows):
    zone = event.get("zone") or {}
    candle = event.get("event_candle") or {}
    detail = auction.get("detail") or {}
    checks = detail.get("checks") or []
    last = checks[-1] if checks else {}
    return {
        "closed_candle_only": True,
        "no_lookahead": True,
        "actor_identification": "PRICE_ACTION_INFERENCE_ONLY",
        "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW",
        "liquidity_map_high_zones": len(highs),
        "liquidity_map_low_zones": len(lows),
        "liquidity_side": zone.get("side", "NONE"),
        "liquidity_level": float(event.get("level", 0.0)) if zone else None,
        "liquidity_kind": zone.get("kind", "NONE"),
        "touches": zone.get("touches", 0),
        "separated_touches": zone.get("separated_touches", 0),
        "age_bars": zone.get("age_bars", 0),
        "freshness": zone.get("freshness", "NONE"),
        "event_index": event.get("index", len(bars) - 1),
        "event_age_bars": event.get("age_bars", 0),
        "event": event.get("type", "NONE"),
        "event_close": float(candle.get("close", 0.0)),
        "event_body_ratio": float((event.get("candle_geometry") or {}).get("body_ratio", 0.0)),
        "auction_state": auction.get("state", "UNRESOLVED"),
        "lifecycle": auction.get("lifecycle", "UNRESOLVED"),
        "follow_through_bars": auction.get("follow_through_bars", 0),
        "consecutive_confirmation_bars": detail.get("consecutive_bars", 0),
        "required_confirmation_bars": detail.get("required_bars", 0),
        "confirmation_horizon": detail.get("horizon_bars", 0),
        "meaningful_response_checks": len([x for x in checks if x.get("meaningful")]),
        "last_response_hold": last.get("hold", False),
        "last_response_displacement_atr": last.get("displacement_atr", 0.0),
        "counter_evidence_basis": (
            "POST_EVENT_RECLAMATION" if detail.get("invalidated") else
            "NO_FOLLOW_THROUGH" if not auction.get("confirmed") else
            "MONITORED_RECLAIM"
        ),
        "contextual_hint_not_authority": context,
        "atr14": round(atr, 6),
    }


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
        thesis = "INSUFFICIENT_DATA -> NO_DIRECTIONAL_THESIS"
        observations = [f"closed_candles={len(bars)}", f"atr14={atr:.6f}", "actor_identification=INFERENCE_ONLY"]
        return {
            **base,
            "state": "UNAVAILABLE",
            "analysis_status": "INCOMPLETE",
            "finding": "LIQUIDITY_DATA_INSUFFICIENT",
            "analyst_conclusion": "LIQUIDITY_DATA_INSUFFICIENT",
            "direction": "NEUTRAL",
            "directional_implication": "NEUTRAL",
            "direction_confirmed": False,
            "confidence": 0.0,
            "evidence_strength": 0.0,
            "observations": observations,
            "liquidity_map": {},
            "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED", "actor_evidence_type": "NONE"},
            "auction": {"state": "UNRESOLVED", "confirmed": False},
            "auction_state": "UNRESOLVED",
            "follow_through": {"present": False},
            "follow_through_bars": 0,
            "auction_confirmation": {"confirmed": False},
            "auction_confirmation_state": "UNRESOLVED",
            "auction_quality": "UNRESOLVED",
            "counter_evidence": ["INSUFFICIENT_DATA"],
            "invalidation": ["new closed-candle data"],
            "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"],
            "independent_thesis": thesis,
            "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "independent_thesis": thesis, "conclusion": "LIQUIDITY_DATA_INSUFFICIENT", "evidence": observations},
            "audit": {"closed_candle_only": True, "no_lookahead": True, "actor_identification": "PRICE_ACTION_INFERENCE_ONLY"},
        }

    current = len(bars) - 1
    pivot_highs, pivot_lows = _pivots(bars)
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    highs = _consume(_cluster(pivot_highs[-LOOKBACK_PIVOTS:], tolerance, "HIGH", current), bars, atr)
    lows = _consume(_cluster(pivot_lows[-LOOKBACK_PIVOTS:], tolerance, "LOW", current), bars, atr)
    event = _find_recent_event(bars, highs, lows, atr)
    auction = _auction_confirmation(event, bars, atr)
    confirmed = bool(auction["confirmed"])
    direction = event.get("directional_implication", "NEUTRAL") if confirmed else "NEUTRAL"
    detail = auction.get("detail") or {}

    if auction["state"] == "INVALIDATED":
        counter = ["POST_EVENT_RECLAMATION", "ORIGINAL_AUCTION_THESIS_REJECTED"]
    elif auction["state"] == "EXPIRED":
        counter = ["NO_SUFFICIENT_FOLLOW_THROUGH_BEFORE_EVENT_EXPIRY", "THESIS_EXPIRED"]
    elif not event.get("zone"):
        counter = ["NO_LIQUIDITY_EVENT"]
    elif not confirmed:
        counter = ["NO_FOLLOW_THROUGH", "AUCTION_DIRECTION_REMAINS_UNRESOLVED"]
    elif direction == "UP":
        counter = ["RECLAIM_BELOW_LIQUIDITY_LEVEL", "OPPOSITE_LOWER_EVENT_CHALLENGES_BULLISH_THESIS"]
    else:
        counter = ["RECLAIM_ABOVE_LIQUIDITY_LEVEL", "OPPOSITE_HIGHER_EVENT_CHALLENGES_BEARISH_THESIS"]

    if confirmed:
        finding = (
            "LOW_ACCEPTANCE_CONFIRMED" if event.get("type") == "LOW_ACCEPTANCE_CANDIDATE" else
            "HIGH_ACCEPTANCE_CONFIRMED" if event.get("type") == "HIGH_ACCEPTANCE_CANDIDATE" else
            event["type"] + "_CONFIRMED"
        )
        quality = "HIGH_CONVICTION" if event.get("zone", {}).get("touches", 1) >= 2 and auction["follow_through_bars"] >= 2 else "CONFIRMED"
    elif event.get("zone"):
        finding = event["type"]
        quality = "INVALIDATED" if auction["state"] == "INVALIDATED" else "EXPIRED" if auction["state"] == "EXPIRED" else "PENDING"
    else:
        finding, quality = "NO_LIQUIDITY_EVENT", "UNRESOLVED"

    independent_thesis = (
        f"LIQUIDITY={event.get('type', 'NONE')}; "
        f"AUCTION={auction.get('state', 'UNRESOLVED')}; "
        f"DIRECTION={direction}; "
        f"CONFIRMED={confirmed}"
    )
    observations = [
        f"closed_candles={len(bars)}",
        f"atr14={atr:.6f}",
        f"liquidity_map_high_zones={len(highs)}",
        f"liquidity_map_low_zones={len(lows)}",
        f"liquidity_side={(event.get('zone') or {}).get('side', 'NONE')}",
        f"liquidity_kind={(event.get('zone') or {}).get('kind', 'NONE')}",
        f"touches={(event.get('zone') or {}).get('touches', 0)}",
        f"separated_touches={(event.get('zone') or {}).get('separated_touches', 0)}",
        f"freshness={(event.get('zone') or {}).get('freshness', 'NONE')}",
        f"event={event.get('type', 'NONE')}",
        f"event_age_bars={event.get('age_bars', 0)}",
        f"actor_identification={event.get('actor_evidence_type', 'NONE')}",
        f"actor_limit={event.get('actor_identification_limit', 'NONE')}",
        f"auction_state={auction.get('state', 'UNRESOLVED')}",
        f"lifecycle={auction.get('lifecycle', 'UNRESOLVED')}",
        f"follow_through_bars={auction.get('follow_through_bars', 0)}",
        f"consecutive_confirmation_bars={detail.get('consecutive_bars', 0)}",
        f"required_confirmation_bars={detail.get('required_bars', 0)}",
        f"confirmation_horizon={detail.get('horizon_bars', 0)}",
        f"true_acceptance_gate={'PASS' if detail.get('acceptance_quality', True) and confirmed else 'FAIL'}",
        "direction_authority=E4_AUCTION_EVIDENCE_ONLY",
        "upstream_direction_used_as_context_only=True",
        "confirmation_requires_consecutive_closed_candles=True",
        "newer_causal_event_supersedes_older_event=True",
    ]
    audit = _audit(event, auction, bars, atr, context, highs, lows)
    professional_reasoning = {
        "question": PROFESSIONAL_QUESTION,
        "independent_thesis": independent_thesis,
        "conclusion": finding,
        "liquidity_state": event.get("liquidity_state", "UNRESOLVED"),
        "auction_state": auction.get("state", "UNRESOLVED"),
        "direction": direction,
        "confirmation": {
            "confirmed": confirmed,
            "required_consecutive_bars": detail.get("required_bars", 0),
            "observed_consecutive_bars": detail.get("consecutive_bars", 0),
            "acceptance_quality": detail.get("acceptance_quality", True),
        },
        "actor_identification": "INFERENCE_FROM_OHLC_ONLY",
        "counter_evidence": counter,
        "invalidation": [
            "newer confirmed liquidity event supersedes current event",
            "post-event close through defended liquidity level invalidates the thesis",
            "event expiry without sufficient follow-through invalidates confirmation",
        ],
    }
    return {
        **base,
        "state": "ANALYSIS_COMPLETE",
        "analysis_status": "COMPLETE",
        "finding": finding,
        "analyst_conclusion": finding,
        "direction": direction,
        "directional_implication": direction,
        "direction_confirmed": confirmed,
        "confidence": round(event.get("strength", 0.30) if confirmed else min(event.get("strength", 0.30), 0.45), 3),
        "evidence_strength": round(event.get("strength", 0.30), 3),
        "observations": observations,
        "liquidity_map": {"high_zones": highs, "low_zones": lows},
        "event": event,
        "auction": auction,
        "auction_state": auction["state"],
        "follow_through": detail,
        "follow_through_bars": auction["follow_through_bars"],
        "auction_confirmation": {"confirmed": confirmed, "state": auction["state"]},
        "auction_confirmation_state": auction["state"],
        "auction_quality": quality,
        "counter_evidence": counter,
        "invalidation": professional_reasoning["invalidation"],
        "reasons": [] if confirmed else ["TRUE_ACCEPTANCE_NOT_PROVEN" if event.get("auction_state") == "ACCEPTANCE" else "AUCTION_RESPONSE_NOT_CONFIRMED" if auction["state"] not in {"INVALIDATED", "EXPIRED"} else auction["state"]],
        "independent_thesis": independent_thesis,
        "professional_reasoning": professional_reasoning,
        "audit": audit,
    }


__all__ = ["analyze_e4"]
