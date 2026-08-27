"""E4 Professional Liquidity & Auction Brain V10.

Standalone analysis-only peer brain. E4 independently maps liquidity, classifies
sweeps, rejection, acceptance and failed breaks, and reports auction state as
qualitative evidence. It never authorizes a trade and never consumes upstream
scores, gates or decisions. Legacy E4 sub-engines 4A-4F remain paused.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V10"
_FORBIDDEN = {
    "decision", "trade_decision", "decision_score", "score", "gate",
    "gate_passed", "specialist_gate",
}


def _f(x: Any):
    try:
        y = float(x)
        return y if isfinite(y) else None
    except (TypeError, ValueError):
        return None


def _bars(snapshot: Any) -> list[dict[str, float]]:
    source = snapshot if isinstance(snapshot, list) else (snapshot or {}).get("bars") or []
    out = []
    for b in source:
        if not isinstance(b, dict):
            continue
        vals = {k: _f(b.get(k)) for k in ("open", "high", "low", "close")}
        if all(v is not None for v in vals.values()) and vals["high"] >= vals["low"]:
            out.append(vals)
    return out


def _atr(bars: list[dict[str, float]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        trs.append(max(
            b["high"] - b["low"],
            abs(b["high"] - p["close"]),
            abs(b["low"] - p["close"]),
        ))
    return sum(trs[-period:]) / min(len(trs), period)


def _pivots(bars: list[dict[str, float]], wing: int = 2):
    highs, lows = [], []
    for i in range(wing, len(bars) - wing):
        window = bars[i - wing:i + wing + 1]
        h, l = bars[i]["high"], bars[i]["low"]
        if h >= max(x["high"] for x in window):
            highs.append((i, h))
        if l <= min(x["low"] for x in window):
            lows.append((i, l))
    return highs, lows


def _clusters(levels, tolerance: float, current_index: int):
    groups = []
    for index, price in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(price - sum(x[1] for x in groups[-1]) / len(groups[-1])) > tolerance:
            groups.append([(index, price)])
        else:
            groups[-1].append((index, price))
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
            "type": "CLUSTERED" if touches > 1 else "SWING",
            "fresh": touches <= 2 and age <= 40,
        })
    return zones


def _directional_context(bus):
    ctx = {}
    for eid in ("E1", "E2", "E3"):
        package = (bus or {}).get(eid, {})
        if not isinstance(package, dict):
            continue
        evidence = package.get("evidence")
        if isinstance(evidence, dict):
            evidence = evidence.get("output", evidence)
        if isinstance(evidence, dict):
            ctx[eid] = {
                k: v for k, v in evidence.items()
                if str(k).lower() not in _FORBIDDEN
            }
    return ctx


def _context_hint(ctx):
    votes = []
    for data in ctx.values():
        text = str(data).upper()
        if any(token in text for token in ("DIRECTION=UP", "TREND_STATE=UP", "PRESSURE=BULLISH", "UP_EVIDENCE")):
            votes.append("UP")
        if any(token in text for token in ("DIRECTION=DOWN", "TREND_STATE=DOWN", "PRESSURE=BEARISH", "DOWN_EVIDENCE")):
            votes.append("DOWN")
    if votes.count("UP") > votes.count("DOWN"):
        return "UP"
    if votes.count("DOWN") > votes.count("UP"):
        return "DOWN"
    return "NEUTRAL"


def _zone_state(zone, bars, side, tolerance):
    """Classify whether a liquidity zone is fresh, consumed or still actionable."""
    price = zone["price"]
    taken = False
    rejected = False
    accepted = False
    for b in bars[max(0, zone["last_touch_index"] + 1):]:
        if side == "HIGH":
            crossed = b["high"] > zone["upper"] + tolerance * 0.05
            if crossed:
                taken = True
                rejected = b["close"] <= zone["upper"] + tolerance * 0.10
                accepted = b["close"] > zone["upper"] + tolerance * 0.15
        else:
            crossed = b["low"] < zone["lower"] - tolerance * 0.05
            if crossed:
                taken = True
                rejected = b["close"] >= zone["lower"] - tolerance * 0.10
                accepted = b["close"] < zone["lower"] - tolerance * 0.15
    zone = dict(zone)
    zone["state"] = "ACCEPTED" if accepted else "REJECTED" if rejected else "TAKEN" if taken else "FRESH" if zone["fresh"] else "AGED"
    zone["consumed"] = taken
    return zone


def _find_recent_event(bars, high_zones, low_zones, atr):
    last = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else last
    tolerance = max(atr * 0.10, 1e-9)
    range_ = max(last["high"] - last["low"], 1e-9)
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]

    high_candidates = [z for z in high_zones if last["high"] > z["upper"] - tolerance]
    low_candidates = [z for z in low_zones if last["low"] < z["lower"] + tolerance]

    high_zone = min(high_candidates, key=lambda z: abs(last["high"] - z["price"]), default=None)
    low_zone = min(low_candidates, key=lambda z: abs(last["low"] - z["price"]), default=None)

    high_sweep = bool(high_zone and last["high"] > high_zone["upper"] + tolerance * 0.05 and last["close"] <= high_zone["upper"] + tolerance * 0.10)
    low_sweep = bool(low_zone and last["low"] < low_zone["lower"] - tolerance * 0.05 and last["close"] >= low_zone["lower"] - tolerance * 0.10)
    high_rejection = high_sweep and upper_wick / range_ >= 0.30
    low_rejection = low_sweep and lower_wick / range_ >= 0.30

    # Acceptance requires a closed-candle displacement beyond the zone.
    high_accept = bool(high_zone and last["close"] > high_zone["upper"] + atr * 0.15)
    low_accept = bool(low_zone and last["close"] < low_zone["lower"] - atr * 0.15)

    # Failed-break/reclaim: the prior candle escaped, then the closed candle reclaimed.
    high_failed = bool(high_zone and previous["close"] > high_zone["upper"] + atr * 0.10 and last["close"] <= high_zone["upper"])
    low_failed = bool(low_zone and previous["close"] < low_zone["lower"] - atr * 0.10 and last["close"] >= low_zone["lower"])

    if high_failed:
        return {"type": "HIGH_FAILED_BREAK_RECLAIM", "liquidity_state": "TAKEN", "direction": "DOWN", "zone": high_zone, "strength": 0.86}
    if low_failed:
        return {"type": "LOW_FAILED_BREAK_RECLAIM", "liquidity_state": "TAKEN", "direction": "UP", "zone": low_zone, "strength": 0.86}
    if high_rejection:
        return {"type": "HIGH_SWEEP_REJECTION", "liquidity_state": "TAKEN", "direction": "DOWN", "zone": high_zone, "strength": 0.90}
    if low_rejection:
        return {"type": "LOW_SWEEP_REJECTION", "liquidity_state": "TAKEN", "direction": "UP", "zone": low_zone, "strength": 0.90}
    if high_accept:
        return {"type": "HIGH_SWEEP_ACCEPTANCE", "liquidity_state": "ACCEPTED", "direction": "UP", "zone": high_zone, "strength": 0.82}
    if low_accept:
        return {"type": "LOW_SWEEP_ACCEPTANCE", "liquidity_state": "ACCEPTED", "direction": "DOWN", "zone": low_zone, "strength": 0.82}
    if high_sweep:
        return {"type": "HIGH_LIQUIDITY_INTERACTION", "liquidity_state": "TAKEN", "direction": "NEUTRAL", "zone": high_zone, "strength": 0.58}
    if low_sweep:
        return {"type": "LOW_LIQUIDITY_INTERACTION", "liquidity_state": "TAKEN", "direction": "NEUTRAL", "zone": low_zone, "strength": 0.58}
    return {"type": "NO_CONFIRMED_LIQUIDITY_EVENT", "liquidity_state": "UNRESOLVED", "direction": "NEUTRAL", "zone": None, "strength": 0.42}


def analyze_e4(snapshot: dict[str, Any] | list[dict[str, Any]] | None = None, evidence_bus: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = snapshot or {}
    bars = _bars(snapshot)
    atr = _atr(bars)
    ctx = _directional_context(evidence_bus)
    if len(bars) < 20 or atr <= 0:
        return {
            "state": "UNAVAILABLE",
            "analysis_status": "INCOMPLETE",
            "architecture": ARCHITECTURE,
            "question": QUESTION,
            "finding": "LIQUIDITY_DATA_INSUFFICIENT",
            "direction": "NEUTRAL",
            "directional_implication": "NEUTRAL",
            "contextual_direction_hint": _context_hint(ctx),
            "confidence": 0.0,
            "evidence_strength": 0.0,
            "observations": [], "evidence": {"raw_market_data_used": True, "decisions_used": False, "gates_used": False, "scores_used": False},
            "liquidity_map": {}, "event": {"type": "LIQUIDITY_DATA_INSUFFICIENT", "liquidity_state": "UNRESOLVED"},
            "interaction": {}, "auction_state": "UNRESOLVED", "context_used": {e: bool(ctx.get(e)) for e in ("E1", "E2", "E3")},
            "reasons": ["INSUFFICIENT_CLOSED_CANDLE_DATA"], "conflicts": [], "missing_evidence": ["CLOSED_CANDLE_HISTORY"],
            "decision": None, "gate": None, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "score": None,
        }

    hi, lo = _pivots(bars)
    tolerance = max(atr * 0.15, 1e-9)
    high_zones = _clusters(hi[-40:], tolerance, len(bars) - 1)
    low_zones = _clusters(lo[-40:], tolerance, len(bars) - 1)
    high_zones = [_zone_state(z, bars, "HIGH", tolerance) for z in high_zones]
    low_zones = [_zone_state(z, bars, "LOW", tolerance) for z in low_zones]
    event = _find_recent_event(bars, high_zones, low_zones, atr)

    price = bars[-1]["close"]
    fresh_high = [z for z in high_zones if not z["consumed"] and z["fresh"]]
    fresh_low = [z for z in low_zones if not z["consumed"] and z["fresh"]]
    consumed_high = [z for z in high_zones if z["consumed"]]
    consumed_low = [z for z in low_zones if z["consumed"]]
    nearest_high = min((z for z in high_zones if z["price"] >= price), key=lambda z: z["price"] - price, default=None)
    nearest_low = min((z for z in low_zones if z["price"] <= price), key=lambda z: price - z["price"], default=None)

    event_type = event["type"]
    if event_type.endswith("REJECTION") or "FAILED_BREAK" in event_type:
        auction = "REJECTION"
    elif event_type.endswith("ACCEPTANCE"):
        auction = "ACCEPTANCE"
    elif fresh_high and fresh_low:
        auction = "BALANCED"
    else:
        auction = "UNRESOLVED"

    reasons = []
    if event["liquidity_state"] == "TAKEN":
        reasons.append("LIQUIDITY_TAKEN")
    if event_type.endswith("REJECTION"):
        reasons.append("REJECTION_AFTER_SWEEP")
    if "FAILED_BREAK" in event_type:
        reasons.append("FAILED_BREAK_RECLAIM")
    if event_type.endswith("ACCEPTANCE"):
        reasons.append("ACCEPTANCE_BEYOND_LIQUIDITY")
    if event_type == "NO_CONFIRMED_LIQUIDITY_EVENT":
        reasons.append("NO_CONFIRMED_EVENT")
    if not fresh_high and not fresh_low:
        reasons.append("FRESH_LIQUIDITY_LIMITED")

    observations = [
        f"closed_candles={len(bars)}", f"atr14={atr:.6f}", f"price={price:.6f}",
        f"high_liquidity_zones={len(high_zones)}", f"low_liquidity_zones={len(low_zones)}",
        f"fresh_high_zones={len(fresh_high)}", f"fresh_low_zones={len(fresh_low)}",
        f"consumed_high_zones={len(consumed_high)}", f"consumed_low_zones={len(consumed_low)}",
        f"event={event_type}", f"liquidity_state={event['liquidity_state']}",
        f"auction_state={auction}", f"contextual_direction={_context_hint(ctx)}",
    ]

    missing = []
    if not high_zones and not low_zones:
        missing.append("LIQUIDITY_ZONES")
    if event_type == "NO_CONFIRMED_LIQUIDITY_EVENT":
        missing.append("CONFIRMED_AUCTION_EVENT")

    return {
        "state": "ANALYSIS_COMPLETE",
        "analysis_status": "COMPLETE",
        "architecture": ARCHITECTURE,
        "question": QUESTION,
        "finding": event_type,
        "direction": event["direction"],
        "directional_implication": event["direction"],
        "contextual_direction_hint": _context_hint(ctx),
        "confidence": round(event["strength"], 3),
        "evidence_strength": round(event["strength"], 3),
        "observations": observations,
        "evidence": {
            "raw_market_data_used": True,
            "decisions_used": False,
            "gates_used": False,
            "scores_used": False,
            "liquidity_event": event_type,
            "liquidity_state": event["liquidity_state"],
            "auction_state": auction,
            "zone_evidence": len(high_zones) + len(low_zones),
        },
        "liquidity_map": {
            "high_zones": high_zones,
            "low_zones": low_zones,
            "fresh_high_zones": len(fresh_high),
            "fresh_low_zones": len(fresh_low),
            "consumed_high_zones": len(consumed_high),
            "consumed_low_zones": len(consumed_low),
            "nearest_high": nearest_high["price"] if nearest_high else None,
            "nearest_low": nearest_low["price"] if nearest_low else None,
        },
        "event": event,
        "interaction": {
            "rejection": auction == "REJECTION",
            "acceptance": auction == "ACCEPTANCE",
            "failed_break_reclaim": "FAILED_BREAK" in event_type,
        },
        "auction_state": auction,
        "context_used": {e: bool(ctx.get(e)) for e in ("E1", "E2", "E3")},
        "reasons": reasons,
        "conflicts": [],
        "missing_evidence": sorted(set(missing)),
        "decision": None,
        "gate": None,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "score": None,
    }
