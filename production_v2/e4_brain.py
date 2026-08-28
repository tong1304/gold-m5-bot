from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V21"
MIN_BARS = 30
PIVOT_WING = 2
LOOKBACK_PIVOTS = 80
EVENT_LOOKBACK = 6
MAX_EVENT_AGE = 8
MAX_CONFIRM_BARS = 6
ZONE_TOLERANCE_ATR = 0.15
INTERACTION_ATR = 0.05
REJECTION_CLOSE_ATR = 0.10
ACCEPTANCE_ATR = 0.15
MIN_BODY_RATIO = 0.55
MIN_WICK_RATIO = 0.30


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
        if not isinstance(b, dict) or b.get("closed") is False or b.get("is_closed") is False:
            continue
        v = {k: _num(b.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            continue
        if v["high"] < max(v["open"], v["close"]) or v["low"] > min(v["open"], v["close"]) or v["high"] < v["low"]:
            continue
        out.append({**b, **v})
    return out


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr = []
    for i in range(1, len(bars)):
        h, l, pc = float(bars[i]["high"]), float(bars[i]["low"]), float(bars[i - 1]["close"])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(tr[-period:]) if tr else 0.0


def _pivots(bars, wing=PIVOT_WING):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        w = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in w):
            highs.append((i, float(bars[i]["high"])))
        if bars[i]["low"] <= min(x["low"] for x in w):
            lows.append((i, float(bars[i]["low"])))
    return highs, lows


def _cluster(levels, tolerance, side, current):
    groups = []
    for item in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(item[1] - mean(p for _, p in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    zones = []
    for g in groups:
        prices = [p for _, p in g]
        last = max(i for i, _ in g)
        touches = len(g)
        age = max(0, current - last)
        zones.append({
            "side": side, "price": mean(prices), "lower": min(prices), "upper": max(prices),
            "touches": touches, "last_touch_index": last, "age_bars": age,
            "kind": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "hierarchy": "EQUAL_LEVEL" if touches >= 2 else "SWING_LEVEL",
            "freshness": "FRESH" if age <= 24 else "AGED",
        })
    return zones


def _consume(zones, bars, atr):
    threshold = max(atr * INTERACTION_ATR, 1e-9)
    current = len(bars) - 1
    out = []
    for zone in zones:
        z = dict(zone)
        takes = []
        for i in range(zone["last_touch_index"] + 1, len(bars)):
            b = bars[i]
            crossed = b["high"] > zone["upper"] + threshold if zone["side"] == "HIGH" else b["low"] < zone["lower"] - threshold
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


def _event_for_zone(bars, zone, atr, i):
    if i <= int(zone.get("last_touch_index", -1)):
        return None
    b, prev = bars[i], bars[i - 1]
    level = float(zone["upper"] if zone["side"] == "HIGH" else zone["lower"])
    g = _geometry(b)
    sweep = max(atr * INTERACTION_ATR, 1e-9)
    close_band = max(atr * REJECTION_CLOSE_ATR, 1e-9)
    extension = max(atr * ACCEPTANCE_ATR, 1e-9)
    if zone["side"] == "HIGH":
        swept = b["high"] > level + sweep
        rejection = swept and b["close"] <= level + close_band and g["upper_wick_ratio"] >= MIN_WICK_RATIO
        failed = prev["close"] > level + extension and b["close"] <= level + close_band
        acceptance = prev["close"] <= level + close_band and b["close"] > level + extension and g["body_ratio"] >= MIN_BODY_RATIO
        if failed: kind, direction, state = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "FAILED_BREAK_RECLAIM"
        elif rejection: kind, direction, state = "HIGH_SWEEP_REJECTION", "DOWN", "REJECTION"
        elif acceptance: kind, direction, state = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "ACCEPTANCE"
        elif swept: kind, direction, state = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "INTERACTION"
        else: return None
        taker = "BUY_SIDE_PRESSURE_INFERENCE"
        response = "SELL_SIDE_RESPONSE_INFERENCE" if direction == "DOWN" else "BUY_SIDE_CONTINUATION_INFERENCE" if direction == "UP" else "UNRESOLVED_PRICE_RESPONSE"
    else:
        swept = b["low"] < level - sweep
        rejection = swept and b["close"] >= level - close_band and g["lower_wick_ratio"] >= MIN_WICK_RATIO
        failed = prev["close"] < level - extension and b["close"] >= level - close_band
        acceptance = prev["close"] >= level - close_band and b["close"] < level - extension and g["body_ratio"] >= MIN_BODY_RATIO
        if failed: kind, direction, state = "LOW_FAILED_BREAK_RECLAIM", "UP", "FAILED_BREAK_RECLAIM"
        elif rejection: kind, direction, state = "LOW_SWEEP_REJECTION", "UP", "REJECTION"
        elif acceptance: kind, direction, state = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "ACCEPTANCE"
        elif swept: kind, direction, state = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "INTERACTION"
        else: return None
        taker = "SELL_SIDE_PRESSURE_INFERENCE"
        response = "BUY_SIDE_RESPONSE_INFERENCE" if direction == "UP" else "SELL_SIDE_CONTINUATION_INFERENCE" if direction == "DOWN" else "UNRESOLVED_PRICE_RESPONSE"
    return {
        "type": kind, "auction_state": state, "directional_implication": direction,
        "liquidity_state": "REJECTED" if state == "REJECTION" else "RECLAIMED" if state == "FAILED_BREAK_RECLAIM" else "ACCEPTANCE_CANDIDATE" if state == "ACCEPTANCE" else "TAKEN",
        "liquidity_taker": taker, "response_actor": response, "actor_evidence_type": "PRICE_ACTION_INFERENCE_ONLY",
        "strength": 0.95 if state == "REJECTION" else 0.94 if state == "FAILED_BREAK_RECLAIM" else 0.88 if state == "ACCEPTANCE" else 0.55,
        "zone": zone, "index": i, "level": level,
        "event_candle": {k: float(b[k]) for k in ("open", "high", "low", "close")}, "candle_geometry": g,
    }


def _find_recent_event(bars, highs, lows, atr):
    current = len(bars) - 1
    candidates = []
    for i in range(max(1, current - EVENT_LOOKBACK), current + 1):
        for z in highs + lows:
            e = _event_for_zone(bars, z, atr, i)
            if e:
                quality = 3 if e["auction_state"] in {"REJECTION", "ACCEPTANCE", "FAILED_BREAK_RECLAIM"} else 1
                candidates.append((quality, i, int(z.get("touches", 1)), e))
    if not candidates:
        return {"type": "NO_LIQUIDITY_EVENT", "auction_state": "UNRESOLVED", "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "liquidity_taker": "NONE", "response_actor": "NONE", "actor_evidence_type": "NONE", "strength": 0.30, "zone": None, "index": current}
    return max(candidates, key=lambda x: (x[0], x[1], x[2], x[3]["strength"]))[-1]


def _adaptive_horizon(event, atr):
    g = event.get("candle_geometry") or {}
    c = event.get("event_candle") or {}
    level = float(event.get("level", 0.0))
    displacement = abs(float(c.get("close", level)) - level) / max(atr, 1e-9)
    body = float(g.get("body_ratio", 0.0))
    if displacement >= 1.0 or body >= 0.80: return 2
    if displacement >= 0.50 or body >= 0.65: return 3
    if displacement >= 0.25: return 4
    return 5


def _response_quality(event, bar, atr):
    direction = event.get("directional_implication", "NEUTRAL")
    level = float(event.get("level", 0.0))
    c = float(bar["close"])
    g = _geometry(bar)
    hold = c > level + atr * INTERACTION_ATR if direction == "UP" else c < level - atr * INTERACTION_ATR if direction == "DOWN" else False
    displacement = (c - level) / max(atr, 1e-9) if direction == "UP" else (level - c) / max(atr, 1e-9) if direction == "DOWN" else 0.0
    return {"hold": hold, "displacement_atr": round(displacement, 4), "body_ratio": g["body_ratio"], "meaningful": hold and (displacement >= 0.20 or g["body_ratio"] >= 0.45), "geometry": g}


def _follow_through(event, bars, atr):
    i = int(event.get("index", -1)); zone = event.get("zone") or {}
    if i < 0 or i >= len(bars) - 1 or not zone:
        return {"present": False, "bars": 0, "available_bars": 0, "required_bars": 0, "horizon_bars": 0, "reason": "NO_POST_EVENT_CANDLE", "invalidated": False, "expired": False, "checks": []}
    horizon = min(MAX_CONFIRM_BARS, _adaptive_horizon(event, atr))
    direction = event.get("directional_implication", "NEUTRAL")
    level = float(event.get("level", zone.get("price", 0.0)))
    checks = []
    meaningful = 0
    invalidated = False
    for j in range(i + 1, min(len(bars), i + horizon + 1)):
        b = bars[j]; q = _response_quality(event, b, atr)
        opposite = float(b["close"]) < level - atr * INTERACTION_ATR if direction == "UP" else float(b["close"]) > level + atr * INTERACTION_ATR if direction == "DOWN" else False
        q.update({"index": j, "close": float(b["close"]), "opposite_reclaim": opposite})
        if opposite: invalidated = True
        if q["meaningful"] and not opposite: meaningful += 1
        checks.append(q)
    available = len(checks)
    # Professional confirmation requires TWO independent supportive closed candles,
    # unless the event itself is exceptionally strong AND the single response is decisive.
    event_strength = float(event.get("strength", 0.0))
    required = 2
    decisive_single = event_strength >= 0.94 and any(x["meaningful"] and x["displacement_atr"] >= 0.75 and x["body_ratio"] >= 0.65 for x in checks)
    present = not invalidated and ((meaningful >= required) or (meaningful >= 1 and decisive_single))
    expired = not present and not invalidated and available >= horizon
    return {"present": present, "bars": meaningful, "available_bars": available, "required_bars": required, "horizon_bars": horizon, "reason": "FOLLOW_THROUGH_CONFIRMED" if present else "EVENT_EXPIRED" if expired else "FOLLOW_THROUGH_ABSENT", "invalidated": invalidated, "expired": expired, "checks": checks, "decisive_single": decisive_single}


def _auction_confirmation(event, bars, atr):
    if not event.get("zone"):
        return {"state": "UNRESOLVED", "confirmed": False, "follow_through": False, "follow_through_bars": 0, "reason": "NO_EVENT", "lifecycle": "NO_EVENT", "detail": {}}
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
        state = {"REJECTION": "REJECTION_PENDING", "ACCEPTANCE": "ACCEPTANCE_PENDING", "FAILED_BREAK_RECLAIM": "REJECTION_PENDING"}.get(base, "INTERACTION_PENDING")
        confirmed, lifecycle = False, "PENDING"
    return {"state": state, "confirmed": confirmed, "follow_through": follow["present"], "follow_through_bars": follow["bars"], "reason": "POST_EVENT_RECLAMATION" if follow["invalidated"] else follow["reason"], "lifecycle": lifecycle, "detail": follow}


def _context_hint(bus):
    votes = []
    for eid in ("E1", "E2", "E3"):
        p = (bus or {}).get(eid, {})
        e = p.get("evidence", p) if isinstance(p, dict) else {}
        o = e.get("output", e) if isinstance(e, dict) else e
        t = str(o).upper()
        if any(x in t for x in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "DIRECTION: UP", 'DIRECTION\": \"UP')): votes.append("UP")
        if any(x in t for x in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DIRECTION: DOWN", 'DIRECTION\": \"DOWN')): votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


def _audit(event, auction, bars, atr, context, highs, lows):
    z = event.get("zone") or {}; c = event.get("event_candle") or {}; d = auction.get("detail") or {}
    checks = d.get("checks") or []
    last = checks[-1] if checks else {}
    return [
        f"closed_candles={len(bars)}", f"atr14={atr:.6f}", f"liquidity_map_high_zones={len(highs)}", f"liquidity_map_low_zones={len(lows)}",
        f"liquidity_side={z.get('side', 'NONE')}", f"liquidity_level={float(event.get('level', 0.0)):.6f}" if z else "liquidity_level=NONE",
        f"liquidity_kind={z.get('kind', 'NONE')}", f"touches={z.get('touches', 0)}", f"age_bars={z.get('age_bars', 0)}", f"freshness={z.get('freshness', 'NONE')}",
        f"event_index={event.get('index', len(bars)-1)}", f"event={event.get('type', 'NONE')}", f"event_close={float(c.get('close', 0.0)):.6f}",
        f"event_body_ratio={float((event.get('candle_geometry') or {}).get('body_ratio', 0.0)):.4f}",
        f"actor_evidence={event.get('actor_evidence_type', 'NONE')}", f"liquidity_taker_inference={event.get('liquidity_taker', 'NONE')}", f"response_inference={event.get('response_actor', 'NONE')}",
        "actor_identification=PRICE_ACTION_INFERENCE_NOT_ORDER_FLOW", f"auction_state={auction.get('state', 'UNRESOLVED')}", f"lifecycle={auction.get('lifecycle', 'UNRESOLVED')}",
        f"follow_through_bars={auction.get('follow_through_bars', 0)}", f"required_confirmation_bars={d.get('required_bars', 0)}", f"confirmation_horizon={d.get('horizon_bars', 0)}",
        f"meaningful_response_checks={len([x for x in checks if x.get('meaningful')])}", f"last_response_hold={last.get('hold', False)}", f"last_response_displacement_atr={last.get('displacement_atr', 0.0)}",
        f"counter_evidence_basis={'POST_EVENT_RECLAMATION' if d.get('invalidated') else 'NO_FOLLOW_THROUGH' if not auction.get('confirmed') else 'MONITORED_RECLAIM'}", f"contextual_hint={context}",
    ]


def analyze_e4(snapshot=None, evidence_bus=None):
    bars = _bars(snapshot); atr = _atr(bars); context = _context_hint(evidence_bus)
    base = {"architecture": ARCHITECTURE, "professional_brain": True, "role": E4_ROLE, "question": PROFESSIONAL_QUESTION,
            "specialists_active": False, "specialists_status": "PAUSED", "decision": None, "gate": None, "score": None,
            "trade_decision_authority": False, "decision_authority": "E9_ONLY", "reasoning_role": E4_ROLE,
            "upstream_decisions_used": False, "upstream_gates_used": False, "scores_used": False, "score_used": False,
            "contextual_direction_hint": context, "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False}}
    if len(bars) < MIN_BARS or atr <= 0:
        return {**base, "state": "UNAVAILABLE", "analysis_status": "INCOMPLETE", "finding": "LIQUIDITY_DATA_INSUFFICIENT", "direction": "NEUTRAL", "directional_implication": "NEUTRAL", "direction_confirmed": False, "confidence": 0.0, "evidence_strength": 0.0, "observations": [f"closed_candles={len(bars)}", f"atr14={atr:.6f}"], "liquidity_map": {}, "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"}, "auction": {"state": "UNRESOLVED", "confirmed": False}, "auction_state": "UNRESOLVED", "follow_through": {"present": False}, "follow_through_bars": 0, "auction_confirmation": {"confirmed": False}, "auction_confirmation_state": "UNRESOLVED", "auction_quality": "UNRESOLVED", "counter_evidence": ["INSUFFICIENT_DATA"], "invalidation": ["new closed-candle data"], "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"]}
    current = len(bars) - 1
    ph, pl = _pivots(bars); tol = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    highs = _consume(_cluster(ph[-LOOKBACK_PIVOTS:], tol, "HIGH", current), bars, atr)
    lows = _consume(_cluster(pl[-LOOKBACK_PIVOTS:], tol, "LOW", current), bars, atr)
    event = _find_recent_event(bars, highs, lows, atr); auction = _auction_confirmation(event, bars, atr); confirmed = bool(auction["confirmed"])
    direction = event.get("directional_implication", "NEUTRAL") if confirmed else "NEUTRAL"
    detail = auction.get("detail") or {}; follow = detail
    if auction["state"] == "INVALIDATED": counter = ["POST_EVENT_RECLAMATION", "ORIGINAL_AUCTION_THESIS_REJECTED"]
    elif auction["state"] == "EXPIRED": counter = ["NO_SUFFICIENT_FOLLOW_THROUGH_BEFORE_EVENT_EXPIRY", "THESIS_EXPIRED"]
    elif not event.get("zone"): counter = ["NO_LIQUIDITY_EVENT"]
    elif not confirmed: counter = ["NO_FOLLOW_THROUGH", "AUCTION_DIRECTION_REMAINS_UNRESOLVED"]
    elif direction == "UP": counter = ["RECLAIM_BELOW_LIQUIDITY_LEVEL", "OPPOSITE_LOWER_EVENT_CHALLENGES_BULLISH_THESIS"]
    else: counter = ["RECLAIM_ABOVE_LIQUIDITY_LEVEL", "OPPOSITE_HIGHER_EVENT_CHALLENGES_BEARISH_THESIS"]
    if confirmed:
        finding = f"{event['type']}_CONFIRMED"; quality = "HIGH_CONVICTION" if event.get("zone", {}).get("touches", 1) >= 2 and auction["follow_through_bars"] >= 2 else "CONFIRMED"
    elif event.get("zone"):
        finding = event["type"]; quality = "INVALIDATED" if auction["state"] == "INVALIDATED" else "EXPIRED" if auction["state"] == "EXPIRED" else "PENDING"
    else: finding, quality = "NO_LIQUIDITY_EVENT", "UNRESOLVED"
    observations = _audit(event, auction, bars, atr, context, highs, lows)
    observations += [f"event_directional_implication={event.get('directional_implication', 'NEUTRAL')}", f"direction_confirmed={confirmed}", f"counter_evidence_count={len(counter)}", f"confirmation_decisive_single={detail.get('decisive_single', False)}"]
    return {**base, "state": "ANALYSIS_COMPLETE", "analysis_status": "COMPLETE", "finding": finding, "direction": direction, "directional_implication": direction,
            "direction_confirmed": confirmed, "confidence": round(event.get("strength", 0.30) if confirmed else min(event.get("strength", 0.30), 0.45), 3),
            "evidence_strength": round(event.get("strength", 0.30), 3), "observations": observations,
            "liquidity_map": {"high_zones": highs, "low_zones": lows}, "event": event, "auction": auction, "auction_state": auction["state"],
            "follow_through": follow, "follow_through_bars": auction["follow_through_bars"], "auction_confirmation": {"confirmed": confirmed, "state": auction["state"]},
            "auction_confirmation_state": auction["state"], "auction_quality": quality, "counter_evidence": counter,
            "invalidation": ["newer confirmed liquidity event supersedes current event", "post-event close through defended liquidity level invalidates the thesis", "event expiry without sufficient follow-through invalidates confirmation"],
            "reasons": [] if confirmed else ["AUCTION_RESPONSE_NOT_CONFIRMED" if auction["state"] not in {"INVALIDATED", "EXPIRED"} else auction["state"]]}


__all__ = ["analyze_e4"]
