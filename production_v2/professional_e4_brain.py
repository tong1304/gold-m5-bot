"""Professional E4 brain: liquidity and auction-state analysis.

Standalone professional module. E4 has the same structural contract as the
professional E1-E3 brains, but its internal reasoning is exclusively about
liquidity location, liquidity consumption, auction interaction, and
acceptance/rejection. It does not wrap or delegate to the legacy E4 brain.

E4 never emits a trade decision, gate, score, entry, stop, target, or execution
instruction. E9 remains the sole decision authority.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
EVIDENCE_HIERARCHY = "DATA_QUALITY -> LIQUIDITY_MAP -> FRESHNESS -> INTERACTION -> AUCTION_RESPONSE -> EVENT_CONFIDENCE"


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _clean_bars(bars: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    valid, problems = [], []
    for i, bar in enumerate(bars or []):
        if not isinstance(bar, dict):
            problems.append(f"bar_{i}_not_mapping")
            continue
        values = {k: _num(bar.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            problems.append(f"bar_{i}_ohlc_invalid")
            continue
        o, h, l, c = values["open"], values["high"], values["low"], values["close"]
        if h < max(o, c) or l > min(o, c) or h < l:
            problems.append(f"bar_{i}_ohlc_inconsistent")
            continue
        valid.append({**bar, **values})
    return valid, problems


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    trs, previous = [], None
    for bar in bars[-period:]:
        h, l, c = float(bar["high"]), float(bar["low"]), float(bar["close"])
        trs.append(h - l if previous is None else max(h - l, abs(h - previous), abs(l - previous)))
        previous = c
    return mean(trs) if trs else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = 2):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, float(bars[i]["high"])))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, float(bars[i]["low"])))
    return highs, lows


def _zones(levels, tolerance: float, current: int, side: str):
    groups = []
    for idx, price in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(price - mean(x[1] for x in groups[-1])) > tolerance:
            groups.append([(idx, price)])
        else:
            groups[-1].append((idx, price))
    result = []
    for group in groups:
        prices = [p for _, p in group]
        last = max(i for i, _ in group)
        touches, age = len(group), current - last
        result.append({
            "side": side,
            "price": mean(prices), "lower": min(prices), "upper": max(prices),
            "touches": touches, "last_touch_index": last, "age_bars": age,
            "kind": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "freshness": "FRESH" if touches >= 2 or age <= 24 else "AGED",
        })
    return result


def _consumption(zones, bars, atr: float):
    threshold = max(atr * 0.05, 1e-9)
    current = len(bars) - 1
    output = []
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
            "recently_taken": latest is not None and current - latest <= 2,
            "state": "TAKEN" if latest is not None and current - latest <= 2 else "CONSUMED" if latest is not None else zone["freshness"],
        })
        output.append(z)
    return output


def _body_ratio(bar):
    span = max(bar["high"] - bar["low"], 1e-12)
    return abs(bar["close"] - bar["open"]) / span


def _event_on_zone(bars, zone, atr, index):
    if index <= 0:
        return None
    b, p = bars[index], bars[index - 1]
    span = max(b["high"] - b["low"], 1e-12)
    upper_wick = (b["high"] - max(b["open"], b["close"])) / span
    lower_wick = (min(b["open"], b["close"]) - b["low"]) / span
    band, extension = max(atr * 0.10, 1e-9), max(atr * 0.15, 1e-9)
    if zone["side"] == "HIGH":
        swept = b["high"] > zone["upper"] + band and b["close"] <= zone["upper"] + band
        failed = p["close"] > zone["upper"] + extension and b["close"] <= zone["upper"]
        accepted = b["close"] > zone["upper"] + extension and _body_ratio(b) >= 0.55
        if failed:
            return {"type": "HIGH_FAILED_BREAK_RECLAIM", "auction_state": "FAILED_BREAK_RECLAIM", "directional_implication": "DOWN", "liquidity_state": "RECLAIMED", "strength": 0.92, "zone": zone, "index": index}
        if swept and upper_wick >= 0.30:
            return {"type": "HIGH_SWEEP_REJECTION", "auction_state": "REJECTION", "directional_implication": "DOWN", "liquidity_state": "TAKEN", "strength": 0.94, "zone": zone, "index": index}
        if accepted:
            return {"type": "HIGH_ACCEPTANCE", "auction_state": "ACCEPTANCE", "directional_implication": "UP", "liquidity_state": "ACCEPTED", "strength": 0.88, "zone": zone, "index": index}
    else:
        swept = b["low"] < zone["lower"] - band and b["close"] >= zone["lower"] - band
        failed = p["close"] < zone["lower"] - extension and b["close"] >= zone["lower"]
        accepted = b["close"] < zone["lower"] - extension and _body_ratio(b) >= 0.55
        if failed:
            return {"type": "LOW_FAILED_BREAK_RECLAIM", "auction_state": "FAILED_BREAK_RECLAIM", "directional_implication": "UP", "liquidity_state": "RECLAIMED", "strength": 0.92, "zone": zone, "index": index}
        if swept and lower_wick >= 0.30:
            return {"type": "LOW_SWEEP_REJECTION", "auction_state": "REJECTION", "directional_implication": "UP", "liquidity_state": "TAKEN", "strength": 0.94, "zone": zone, "index": index}
        if accepted:
            return {"type": "LOW_ACCEPTANCE", "auction_state": "ACCEPTANCE", "directional_implication": "DOWN", "liquidity_state": "ACCEPTED", "strength": 0.88, "zone": zone, "index": index}
    return None


def _detect_event(bars, highs, lows, atr):
    current = len(bars) - 1
    price = bars[-1]["close"]
    candidates = highs + lows
    candidates.sort(key=lambda z: abs(z["price"] - price))
    for index in range(current, max(-1, current - 3), -1):
        for zone in candidates:
            if abs(zone["price"] - bars[index]["close"]) <= atr or (zone["side"] == "HIGH" and bars[index]["high"] >= zone["upper"] - atr * 0.10) or (zone["side"] == "LOW" and bars[index]["low"] <= zone["lower"] + atr * 0.10):
                event = _event_on_zone(bars, zone, atr, index)
                if event:
                    return event
    return {"type": "NO_CONFIRMED_LIQUIDITY_EVENT", "auction_state": "UNRESOLVED", "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "strength": 0.30, "zone": None, "index": current}


def _context_hint(evidence_bus):
    votes = []
    for eid in ("E1", "E2", "E3"):
        package = (evidence_bus or {}).get(eid, {})
        evidence = package.get("evidence", package) if isinstance(package, dict) else {}
        text = str(evidence.get("output", evidence) if isinstance(evidence, dict) else evidence).upper()
        if any(t in text for t in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH")): votes.append("UP")
        if any(t in text for t in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH")): votes.append("DOWN")
    return "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"


def _incomplete(reason, conflicts=None):
    conflicts = conflicts or []
    return {
        "question": PROFESSIONAL_QUESTION, "finding": "LIQUIDITY_DATA_INSUFFICIENT", "auction_state": "UNRESOLVED",
        "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "confidence": 0.0,
        "evidence_strength": 0.0, "evidence": [], "conflicts": conflicts, "missing_evidence": ["CLOSED_CANDLE_HISTORY"],
        "reasoning_trace": [f"QUESTION -> {PROFESSIONAL_QUESTION}", f"DATA_QUALITY -> {reason}"],
        "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "MAP_LIQUIDITY_AND_CLASSIFY_AUCTION_ONLY", "primary_state": "UNRESOLVED", "direction": "NEUTRAL", "thesis": reason, "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": {}, "context_corrobation_only": True, "conflict_detected": bool(conflicts), "conflict_count": len(conflicts), "classification_reason": reason},
        "analysis_status": "INCOMPLETE", "reasoning_role": E4_ROLE, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None, "score": None,
    }


def analyze_e4(bars: list[dict[str, Any]] | None, evidence_bus: dict[str, Any] | None = None) -> dict[str, Any]:
    """Independently map liquidity and classify the current auction response."""
    valid, problems = _clean_bars(bars)
    if len(valid) < 60:
        return _incomplete("insufficient reliable candles; liquidity analysis withheld", problems[:6])
    atr = _atr(valid)
    if atr <= 0:
        return _incomplete("ATR invalid; liquidity analysis withheld", ["ATR_INVALID"])

    high_levels, low_levels = _pivots(valid)
    tolerance = max(atr * 0.15, 1e-9)
    high_zones = _consumption(_zones(high_levels[-50:], tolerance, len(valid) - 1, "HIGH"), valid, atr)
    low_zones = _consumption(_zones(low_levels[-50:], tolerance, len(valid) - 1, "LOW"), valid, atr)
    event = _detect_event(valid, high_zones, low_zones, atr)
    context = _context_hint(evidence_bus)
    context_conflict = event["directional_implication"] in {"UP", "DOWN"} and context in {"UP", "DOWN"} and event["directional_implication"] != context
    reasons = []
    if "SWEEP" in event["type"]: reasons = ["LIQUIDITY_TAKEN", "REJECTION_AFTER_SWEEP"]
    elif "FAILED_BREAK" in event["type"]: reasons = ["FAILED_BREAK_RECLAIM", "LIQUIDITY_RECLAIMED"]
    elif "ACCEPTANCE" in event["type"]: reasons = ["ACCEPTANCE_BEYOND_LIQUIDITY"]
    else: reasons = ["NO_CONFIRMED_EVENT"]
    if context_conflict: reasons.append("EVENT_VS_CONTEXT_DIVERGENCE")

    all_zones = high_zones + low_zones
    fresh = sum(z["state"] in {"FRESH", "TAKEN"} for z in all_zones)
    zone_quality = min(1.0, fresh / max(1, min(len(all_zones), 8)))
    confidence = round(max(0.0, min(0.99, event["strength"] * 0.78 + zone_quality * 0.18 + (0.04 if event["directional_implication"] == context and context != "NEUTRAL" else 0.0))), 3)
    price = float(valid[-1]["close"])
    nearest_high = min((z for z in high_zones if z["price"] >= price), key=lambda z: z["price"] - price, default=None)
    nearest_low = min((z for z in low_zones if z["price"] <= price), key=lambda z: price - z["price"], default=None)
    independent = {
        "liquidity_above": nearest_high["price"] if nearest_high else None,
        "liquidity_below": nearest_low["price"] if nearest_low else None,
        "fresh_above": sum(z["state"] in {"FRESH", "TAKEN"} for z in high_zones),
        "fresh_below": sum(z["state"] in {"FRESH", "TAKEN"} for z in low_zones),
        "recently_taken_above": sum(z["recently_taken"] for z in high_zones),
        "recently_taken_below": sum(z["recently_taken"] for z in low_zones),
        "current_event": event["type"], "auction_state": event["auction_state"],
        "event_direction": event["directional_implication"], "event_strength": event["strength"],
    }
    return {
        "question": PROFESSIONAL_QUESTION, "finding": event["type"], "auction_state": event["auction_state"],
        "directional_implication": event["directional_implication"], "liquidity_state": event["liquidity_state"],
        "confidence": confidence, "evidence_strength": event["strength"], "analysis_status": "COMPLETE",
        "reasoning_role": E4_ROLE, "trade_decision_authority": False, "decision_authority": "E9_ONLY",
        "decision": None, "gate": None, "score": None,
        "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False, "context_used": {e: bool((evidence_bus or {}).get(e)) for e in ("E1", "E2", "E3")}, "context_is_corroboration_only": True},
        "observations": [f"closed_candles={len(valid)}", f"atr14={atr:.6f}", f"price={price:.6f}", f"high_liquidity_zones={len(high_zones)}", f"low_liquidity_zones={len(low_zones)}", f"event={event['type']}", f"auction_state={event['auction_state']}", f"context_hint={context}"],
        "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones, "nearest_high": nearest_high, "nearest_low": nearest_low},
        "event": event,
        "interaction": {"liquidity_taken": event["liquidity_state"] in {"TAKEN", "RECLAIMED", "ACCEPTED"}, "rejection": event["auction_state"] == "REJECTION", "acceptance": event["auction_state"] == "ACCEPTANCE", "failed_break_reclaim": event["auction_state"] == "FAILED_BREAK_RECLAIM"},
        "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "MAP_LIQUIDITY_AND_CLASSIFY_AUCTION_ONLY", "primary_state": event["auction_state"], "direction": event["directional_implication"], "thesis": event["type"], "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": independent, "context_corrobation_only": True, "context_direction_hint": context, "conflict_detected": context_conflict, "conflict_count": int(context_conflict), "classification_reason": ";".join(reasons), "data_quality": round(max(0.0, 1.0 - min(0.5, len(problems) / 20.0)), 3)},
        "reasoning_trace": [f"QUESTION -> {PROFESSIONAL_QUESTION}", "LIQUIDITY_MAP -> swing/equal liquidity identified", f"LIQUIDITY_INTERACTION -> {event['liquidity_state']}", f"AUCTION_RESPONSE -> {event['auction_state']}", f"CLASSIFICATION -> {event['type']}", "AUTHORITY -> E4 provides evidence only; E9 decides"],
        "reasons": reasons, "conflicts": [r for r in reasons if "DIVERGENCE" in r], "missing_evidence": [] if event["zone"] else ["CONFIRMED_AUCTION_EVENT"],
    }


__all__ = ["PROFESSIONAL_QUESTION", "E4_ROLE", "EVIDENCE_HIERARCHY", "analyze_e4"]
