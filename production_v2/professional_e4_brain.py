"""Professional E4 — Liquidity & Auction Brain.

E4 is a standalone qualitative market analyst. Its only job is to answer:
"Where is liquidity, who took it, and did price accept or reject the auction?"

The brain uses closed OHLC candles only. E1-E3 evidence can corroborate the
analysis, but E4 never consumes their decisions, gates, or scores. E4 never
creates an execution decision; E9 remains the sole decision authority.
"""
from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V14"
EVIDENCE_HIERARCHY = "DATA_QUALITY -> LIQUIDITY_MAP -> LIQUIDITY_FRESHNESS -> LIQUIDITY_TAKING -> AUCTION_RESPONSE -> DIRECTIONAL_IMPLICATION -> CONFIDENCE"


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _extract_bars(source: Any) -> list[dict[str, Any]]:
    if isinstance(source, dict):
        source = source.get("bars") or []
    return list(source) if isinstance(source, (list, tuple)) else []


def _clean_bars(source: Any) -> tuple[list[dict[str, Any]], list[str]]:
    valid: list[dict[str, Any]] = []
    problems: list[str] = []
    for i, bar in enumerate(_extract_bars(source)):
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
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    previous_close: float | None = None
    for bar in bars[-period:]:
        h, l, c = float(bar["high"]), float(bar["low"]), float(bar["close"])
        trs.append(h - l if previous_close is None else max(h - l, abs(h - previous_close), abs(l - previous_close)))
        previous_close = c
    return mean(trs) if trs else 0.0


def _pivots(bars: list[dict[str, Any]], wing: int = 2) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, float(bars[i]["high"])))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, float(bars[i]["low"])))
    return highs, lows


def _cluster(levels: list[tuple[int, float]], tolerance: float, side: str, current: int) -> list[dict[str, Any]]:
    groups: list[list[tuple[int, float]]] = []
    for idx, price in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(price - mean(p for _, p in groups[-1])) > tolerance:
            groups.append([(idx, price)])
        else:
            groups[-1].append((idx, price))
    zones: list[dict[str, Any]] = []
    for group in groups:
        prices = [p for _, p in group]
        last_touch = max(i for i, _ in group)
        touches = len(group)
        age = max(0, current - last_touch)
        zones.append({
            "side": side,
            "price": mean(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": touches,
            "last_touch_index": last_touch,
            "age_bars": age,
            "kind": "EQUAL_LIQUIDITY" if touches >= 2 else "SWING_LIQUIDITY",
            "freshness": "FRESH" if touches >= 2 or age <= 24 else "AGED",
        })
    return zones


def _liquidity_consumption(zones: list[dict[str, Any]], bars: list[dict[str, Any]], atr: float) -> list[dict[str, Any]]:
    threshold = max(atr * 0.05, 1e-9)
    current = len(bars) - 1
    output: list[dict[str, Any]] = []
    for zone in zones:
        z = dict(zone)
        takes: list[int] = []
        for i in range(zone["last_touch_index"] + 1, len(bars)):
            bar = bars[i]
            crossed = bar["high"] > zone["upper"] + threshold if zone["side"] == "HIGH" else bar["low"] < zone["lower"] - threshold
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


def _body_ratio(bar: dict[str, Any]) -> float:
    span = max(float(bar["high"]) - float(bar["low"]), 1e-12)
    return abs(float(bar["close"]) - float(bar["open"])) / span


def _event_for_zone(bars: list[dict[str, Any]], zone: dict[str, Any], atr: float, index: int) -> dict[str, Any] | None:
    if index <= 0:
        return None
    bar, previous = bars[index], bars[index - 1]
    span = max(bar["high"] - bar["low"], 1e-12)
    upper_wick = (bar["high"] - max(bar["open"], bar["close"])) / span
    lower_wick = (min(bar["open"], bar["close"]) - bar["low"]) / span
    band = max(atr * 0.10, 1e-9)
    extension = max(atr * 0.15, 1e-9)
    if zone["side"] == "HIGH":
        swept = bar["high"] > zone["upper"] + band and bar["close"] <= zone["upper"] + band
        failed = previous["close"] > zone["upper"] + extension and bar["close"] <= zone["upper"]
        accepted = bar["close"] > zone["upper"] + extension and _body_ratio(bar) >= 0.55
        if failed:
            return {"type": "HIGH_FAILED_BREAK_RECLAIM", "auction_state": "FAILED_BREAK_RECLAIM", "directional_implication": "DOWN", "liquidity_state": "RECLAIMED", "liquidity_taker": "BUYERS", "response_actor": "SELLERS", "strength": 0.92, "zone": zone, "index": index}
        if swept and upper_wick >= 0.30:
            return {"type": "HIGH_SWEEP_REJECTION", "auction_state": "REJECTION", "directional_implication": "DOWN", "liquidity_state": "TAKEN", "liquidity_taker": "BUYERS", "response_actor": "SELLERS", "strength": 0.94, "zone": zone, "index": index}
        if accepted:
            return {"type": "HIGH_ACCEPTANCE", "auction_state": "ACCEPTANCE", "directional_implication": "UP", "liquidity_state": "ACCEPTED", "liquidity_taker": "BUYERS", "response_actor": "BUYERS", "strength": 0.88, "zone": zone, "index": index}
    else:
        swept = bar["low"] < zone["lower"] - band and bar["close"] >= zone["lower"] - band
        failed = previous["close"] < zone["lower"] - extension and bar["close"] >= zone["lower"]
        accepted = bar["close"] < zone["lower"] - extension and _body_ratio(bar) >= 0.55
        if failed:
            return {"type": "LOW_FAILED_BREAK_RECLAIM", "auction_state": "FAILED_BREAK_RECLAIM", "directional_implication": "UP", "liquidity_state": "RECLAIMED", "liquidity_taker": "SELLERS", "response_actor": "BUYERS", "strength": 0.92, "zone": zone, "index": index}
        if swept and lower_wick >= 0.30:
            return {"type": "LOW_SWEEP_REJECTION", "auction_state": "REJECTION", "directional_implication": "UP", "liquidity_state": "TAKEN", "liquidity_taker": "SELLERS", "response_actor": "BUYERS", "strength": 0.94, "zone": zone, "index": index}
        if accepted:
            return {"type": "LOW_ACCEPTANCE", "auction_state": "ACCEPTANCE", "directional_implication": "DOWN", "liquidity_state": "ACCEPTED", "liquidity_taker": "SELLERS", "response_actor": "SELLERS", "strength": 0.88, "zone": zone, "index": index}
    return None


def _detect_event(bars: list[dict[str, Any]], high_zones: list[dict[str, Any]], low_zones: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    current = len(bars) - 1
    candidates = high_zones + low_zones
    for index in range(current, max(-1, current - 4), -1):
        bar = bars[index]
        nearby = sorted(candidates, key=lambda z: abs(z["price"] - bar["close"]))
        for zone in nearby:
            touched = bar["high"] >= zone["lower"] - atr * 0.10 if zone["side"] == "HIGH" else bar["low"] <= zone["upper"] + atr * 0.10
            if touched:
                event = _event_for_zone(bars, zone, atr, index)
                if event:
                    return event
    return {"type": "NO_CONFIRMED_LIQUIDITY_EVENT", "auction_state": "UNRESOLVED", "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "liquidity_taker": "NONE", "response_actor": "NONE", "strength": 0.30, "zone": None, "index": current}


def _context_hint(evidence_bus: dict[str, Any] | None) -> tuple[str, dict[str, bool]]:
    votes: list[str] = []
    used: dict[str, bool] = {}
    for engine_id in ("E1", "E2", "E3"):
        package = (evidence_bus or {}).get(engine_id, {})
        evidence = package.get("evidence", package) if isinstance(package, dict) else {}
        output = evidence.get("output", evidence) if isinstance(evidence, dict) else evidence
        text = str(output).upper()
        used[engine_id] = bool(package)
        if any(token in text for token in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH")):
            votes.append("UP")
        if any(token in text for token in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH")):
            votes.append("DOWN")
    direction = "UP" if votes.count("UP") > votes.count("DOWN") else "DOWN" if votes.count("DOWN") > votes.count("UP") else "NEUTRAL"
    return direction, used


def _incomplete(reason: str, problems: list[str] | None = None) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE, "question": PROFESSIONAL_QUESTION, "finding": "LIQUIDITY_DATA_INSUFFICIENT", "auction_state": "UNRESOLVED", "directional_implication": "NEUTRAL", "liquidity_state": "UNRESOLVED", "confidence": 0.0, "evidence_strength": 0.0, "analysis_status": "INCOMPLETE", "reasoning_role": E4_ROLE,
        "evidence": {"raw_market_data_used": False, "decisions_used": False, "gates_used": False, "scores_used": False}, "missing_evidence": ["CLOSED_CANDLE_HISTORY"], "observations": list(problems or []), "conflicts": [], "reasons": [reason],
        "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "MAP_LIQUIDITY_AND_CLASSIFY_AUCTION_ONLY", "primary_state": "UNRESOLVED", "direction": "NEUTRAL", "thesis": reason, "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": {}, "context_used": False, "context_corrobation_only": True, "decisions_used": False, "gates_used": False, "scores_used": False},
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None, "score": None,
    }


def analyze_e4(bars: Any, evidence_bus: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze closed M5 candles independently; accepts list or market snapshot."""
    valid, problems = _clean_bars(bars)
    if len(valid) < 60:
        return _incomplete("insufficient reliable closed candles; liquidity analysis withheld", problems[:6])
    atr = _atr(valid)
    if atr <= 0:
        return _incomplete("ATR invalid; liquidity analysis withheld", ["ATR_INVALID"])

    high_levels, low_levels = _pivots(valid)
    tolerance = max(atr * 0.15, 1e-9)
    high_zones = _liquidity_consumption(_cluster(high_levels[-60:], tolerance, "HIGH", len(valid) - 1), valid, atr)
    low_zones = _liquidity_consumption(_cluster(low_levels[-60:], tolerance, "LOW", len(valid) - 1), valid, atr)
    event = _detect_event(valid, high_zones, low_zones, atr)
    context, context_used = _context_hint(evidence_bus)
    event_direction = event["directional_implication"]
    context_conflict = event_direction in {"UP", "DOWN"} and context in {"UP", "DOWN"} and event_direction != context

    if "SWEEP" in event["type"]:
        reasons = ["LIQUIDITY_TAKEN", "REJECTION_AFTER_SWEEP"]
    elif "FAILED_BREAK" in event["type"]:
        reasons = ["FAILED_BREAK_RECLAIM", "LIQUIDITY_RECLAIMED"]
    elif "ACCEPTANCE" in event["type"]:
        reasons = ["ACCEPTANCE_BEYOND_LIQUIDITY"]
    else:
        reasons = ["NO_CONFIRMED_EVENT"]
    if context_conflict:
        reasons.append("EVENT_VS_CONTEXT_DIVERGENCE")

    all_zones = high_zones + low_zones
    fresh_count = sum(z["state"] in {"FRESH", "TAKEN"} for z in all_zones)
    zone_quality = min(1.0, fresh_count / max(1, min(len(all_zones), 8)))
    confidence = event["strength"] * 0.78 + zone_quality * 0.18 + (0.04 if event_direction == context and context != "NEUTRAL" else 0.0)
    confidence = round(max(0.0, min(0.99, confidence)), 3)

    price = float(valid[-1]["close"])
    nearest_high = min((z for z in high_zones if z["price"] >= price), key=lambda z: z["price"] - price, default=None)
    nearest_low = min((z for z in low_zones if z["price"] <= price), key=lambda z: price - z["price"], default=None)
    independent = {
        "liquidity_above": nearest_high["price"] if nearest_high else None,
        "liquidity_below": nearest_low["price"] if nearest_low else None,
        "fresh_above": sum(z["state"] in {"FRESH", "TAKEN"} for z in high_zones),
        "fresh_below": sum(z["state"] in {"FRESH", "TAKEN"} for z in low_zones),
        "recently_taken_above": sum(bool(z["recently_taken"]) for z in high_zones),
        "recently_taken_below": sum(bool(z["recently_taken"]) for z in low_zones),
        "current_event": event["type"], "auction_state": event["auction_state"], "event_direction": event_direction,
        "liquidity_taker": event["liquidity_taker"], "response_actor": event["response_actor"], "event_strength": event["strength"],
    }
    return {
        "architecture": ARCHITECTURE, "question": PROFESSIONAL_QUESTION, "finding": event["type"], "auction_state": event["auction_state"], "directional_implication": event_direction,
        "liquidity_state": event["liquidity_state"], "liquidity_taker": event["liquidity_taker"], "response_actor": event["response_actor"], "confidence": confidence,
        "evidence_strength": round(float(event["strength"]), 3), "analysis_status": "COMPLETE", "reasoning_role": E4_ROLE,
        "observations": [f"closed_candles={len(valid)}", f"atr14={atr:.6f}", f"high_liquidity_zones={len(high_zones)}", f"low_liquidity_zones={len(low_zones)}", f"event={event['type']}", f"liquidity_state={event['liquidity_state']}", f"liquidity_taker={event['liquidity_taker']}", f"response_actor={event['response_actor']}", f"auction_state={event['auction_state']}", f"event_direction={event_direction}", f"context_direction={context}"],
        "liquidity_map": {"high_zones": high_zones, "low_zones": low_zones}, "event": event, "independent_evidence": independent,
        "evidence": {"raw_market_data_used": True, "closed_candles_only": True, "decisions_used": False, "gates_used": False, "scores_used": False, "context_used": context_used, "context_corrobation_only": True},
        "missing_evidence": ["CONFIRMED_AUCTION_EVENT"] if event["type"] == "NO_CONFIRMED_LIQUIDITY_EVENT" else [],
        "conflicts": ["EVENT_VS_CONTEXT_DIVERGENCE"] if context_conflict else [], "reasons": reasons,
        "reasoning_trace": [f"QUESTION -> {PROFESSIONAL_QUESTION}", f"LIQUIDITY_MAP -> high_zones={len(high_zones)}, low_zones={len(low_zones)}", f"LIQUIDITY_TAKING -> {event['liquidity_state']} by {event['liquidity_taker']}", f"AUCTION_RESPONSE -> {event['auction_state']}", f"DIRECTIONAL_IMPLICATION -> {event_direction}"],
        "professional_reasoning": {"question": PROFESSIONAL_QUESTION, "task": "MAP_LIQUIDITY_AND_CLASSIFY_AUCTION_ONLY", "primary_state": event["auction_state"], "direction": event_direction, "thesis": event["type"], "evidence_hierarchy": EVIDENCE_HIERARCHY, "independent_evidence": independent, "context_used": any(context_used.values()), "context_corrobation_only": True, "decisions_used": False, "gates_used": False, "scores_used": False, "conflict_detected": context_conflict, "conflict_count": int(context_conflict), "classification_reason": ";".join(reasons)},
        "trade_decision_authority": False, "decision_authority": "E9_ONLY", "decision": None, "gate": None, "score": None,
    }


__all__ = ["ARCHITECTURE", "E4_ROLE", "EVIDENCE_HIERARCHY", "PROFESSIONAL_QUESTION", "analyze_e4"]
