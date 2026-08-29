from __future__ import annotations

from hashlib import sha256
from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V51"

MIN_BARS = 30
PIVOT_WING = 2
LOOKBACK_PIVOTS = 60
FOLLOW_WINDOW = 5
CONFIRM_BARS = 2
INTERACTION_ATR = 0.05
MIN_DISPLACEMENT_ATR = 0.20
ZONE_TOLERANCE_ATR = 0.15
SWEEP_ATR = 0.05
CLOSE_TOLERANCE_ATR = 0.10
ACCEPTANCE_ATR = 0.15
MIN_BODY_RATIO = 0.55
MIN_WICK_RATIO = 0.30
LIQUIDITY_NEAR_ATR = 0.75
LIQUIDITY_FAR_ATR = 2.50
QUALITY_TOUCH_CAP = 4
TERMINAL_STATES = ("CONFIRMED", "INVALIDATED", "EXPIRED")
AUDIT_LIMIT = 200

_LIFECYCLE_STATE: dict[str, dict[str, Any]] = {}
_AUDIT_TRAIL: dict[str, list[dict[str, Any]]] = {}
_AUDIT_SEQUENCE = 0


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _bars(snapshot: Any) -> list[dict[str, Any]]:
    raw = snapshot.get("bars", []) if isinstance(snapshot, dict) else snapshot
    out: list[dict[str, Any]] = []
    for raw_bar in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(raw_bar, dict):
            continue
        v = {k: _num(raw_bar.get(k)) for k in ("open", "high", "low", "close")}
        if any(x is None for x in v.values()):
            continue
        if v["high"] < max(v["open"], v["close"]) or v["low"] > min(v["open"], v["close"]) or v["high"] < v["low"]:
            continue
        out.append({**raw_bar, **v})
    return out


def _stable_bar_identity(bar: dict[str, Any], fallback: int) -> tuple[str, str]:
    for key in ("timestamp", "time", "datetime", "date", "candle", "open_time", "close_time"):
        value = bar.get(key)
        if value not in (None, ""):
            return str(value), f"FIELD:{key}"
    payload = "|".join(f"{bar[k]:.12g}" for k in ("open", "high", "low", "close"))
    return f"OHLC:{sha256(payload.encode('utf-8')).hexdigest()[:16]}", "OHLC_HASH"


def _bar_id(bar: dict[str, Any], fallback: int) -> str:
    return _stable_bar_identity(bar, fallback)[0]


def _market(snapshot: Any) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"
    for key in ("symbol", "instrument", "market", "ticker", "asset"):
        if snapshot.get(key):
            return str(snapshot[key]).upper()
    return "UNKNOWN"


def _timeframe(snapshot: Any) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"
    for key in ("timeframe", "tf", "interval"):
        if snapshot.get(key):
            return str(snapshot[key]).upper()
    return "M5"


def _source(snapshot: Any) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"
    for key in ("source", "data_source", "provider", "feed"):
        if snapshot.get(key):
            return str(snapshot[key]).upper()
    return "UNKNOWN"


def _state_key(snapshot: Any) -> str:
    return f"{_market(snapshot)}|{_timeframe(snapshot)}|{_source(snapshot)}"


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(tr[-period:]) if tr else 0.0


def _body_ratio(bar: dict[str, Any]) -> float:
    return abs(bar["close"] - bar["open"]) / max(bar["high"] - bar["low"], 1e-12)


def _range_ratio(bar: dict[str, Any], atr: float) -> float:
    return (bar["high"] - bar["low"]) / max(atr, 1e-12)


def _pivots(bars: list[dict[str, Any]]):
    highs, lows = [], []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING : i + PIVOT_WING + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, bars[i]["low"]))
    return highs[-LOOKBACK_PIVOTS:], lows[-LOOKBACK_PIVOTS:]


def _zones(levels, tolerance, side, current):
    groups = []
    for item in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(item[1] - mean(p for _, p in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    result = []
    for group in groups:
        prices = [p for _, p in group]
        last_touch = max(i for i, _ in group)
        result.append({"side": side, "price": mean(prices), "lower": min(prices), "upper": max(prices), "touches": len(group), "last_touch_index": last_touch, "age_bars": max(0, current - last_touch), "kind": "EQUAL_LIQUIDITY" if len(group) >= 2 else "SWING_LIQUIDITY", "freshness": "FRESH" if current - last_touch <= 24 else "AGED"})
    return result


def _classify_zone(zone: dict[str, Any], current_price: float, atr: float) -> dict[str, Any]:
    z = dict(zone)
    distance = abs(z["price"] - current_price) / max(atr, 1e-12)
    z["distance_from_current_atr"] = round(distance, 6)
    z["proximity"] = "NEAR" if distance <= LIQUIDITY_NEAR_ATR else "ACTIVE" if distance <= LIQUIDITY_FAR_ATR else "DISTANT"
    if z["side"] == "HIGH":
        z["location"] = "ABOVE_PRICE"
        z["externality"] = "EXTERNAL" if z["price"] >= current_price + atr else "INTERNAL"
    else:
        z["location"] = "BELOW_PRICE"
        z["externality"] = "EXTERNAL" if z["price"] <= current_price - atr else "INTERNAL"
    touch_factor = min(z["touches"], QUALITY_TOUCH_CAP) / QUALITY_TOUCH_CAP
    freshness_factor = 1.0 if z["freshness"] == "FRESH" else 0.55
    proximity_factor = 1.0 if z["proximity"] == "NEAR" else 0.75 if z["proximity"] == "ACTIVE" else 0.35
    external_factor = 1.0 if z["externality"] == "EXTERNAL" else 0.75
    kind_factor = 1.0 if z["kind"] == "EQUAL_LIQUIDITY" else 0.80
    quality = 100.0 * (0.30 * touch_factor + 0.25 * freshness_factor + 0.20 * proximity_factor + 0.15 * external_factor + 0.10 * kind_factor)
    z["quality"] = round(quality, 2)
    z["quality_components"] = {"touches": round(touch_factor, 4), "freshness": round(freshness_factor, 4), "proximity": round(proximity_factor, 4), "externality": round(external_factor, 4), "liquidity_type": round(kind_factor, 4)}
    return z


def _liquidity_map(bars: list[dict[str, Any]], atr: float) -> dict[str, Any]:
    if not bars or atr <= 0:
        return {"zones": [], "zone_count": 0, "equal_liquidity_count": 0, "swing_liquidity_count": 0, "nearest_above": None, "nearest_below": None, "external_above": None, "external_below": None}
    current, price = len(bars) - 1, bars[-1]["close"]
    highs, lows = _pivots(bars)
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    raw = _zones(highs, tolerance, "HIGH", current) + _zones(lows, tolerance, "LOW", current)
    zones = [_classify_zone(z, price, atr) for z in raw]
    zones.sort(key=lambda z: (z["distance_from_current_atr"], -z["quality"]))
    above = [z for z in zones if z["price"] >= price]
    below = [z for z in zones if z["price"] <= price]
    ext_above = [z for z in above if z["externality"] == "EXTERNAL"]
    ext_below = [z for z in below if z["externality"] == "EXTERNAL"]
    return {"zones": zones, "zone_count": len(zones), "equal_liquidity_count": sum(z["kind"] == "EQUAL_LIQUIDITY" for z in zones), "swing_liquidity_count": sum(z["kind"] == "SWING_LIQUIDITY" for z in zones), "nearest_above": above[0] if above else None, "nearest_below": below[0] if below else None, "external_above": min(ext_above, key=lambda z: z["distance_from_current_atr"]) if ext_above else None, "external_below": min(ext_below, key=lambda z: z["distance_from_current_atr"]) if ext_below else None}


def _event_for_zone(bars, zone, atr, i):
    if i <= zone["last_touch_index"] or i <= 0 or atr <= 0:
        return None
    b, p = bars[i], bars[i - 1]
    level = zone["upper"] if zone["side"] == "HIGH" else zone["lower"]
    sweep, band, extension = max(atr * SWEEP_ATR, 1e-9), max(atr * CLOSE_TOLERANCE_ATR, 1e-9), max(atr * ACCEPTANCE_ATR, 1e-9)
    body, displacement, range_atr = _body_ratio(b), abs(b["close"] - level) / max(atr, 1e-12), _range_ratio(b, atr)
    if zone["side"] == "HIGH":
        swept = b["high"] > level + sweep
        wick = (b["high"] - max(b["open"], b["close"])) / max(b["high"] - b["low"], 1e-12)
        rejection = swept and b["close"] <= level + band and wick >= MIN_WICK_RATIO
        failed = p["close"] > level + extension and b["close"] <= level + band
        acceptance = b["close"] > level + extension and body >= MIN_BODY_RATIO
        if failed: kind, direction, taker, actor, strength = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "BUYERS", "SELLERS", 0.94
        elif rejection: kind, direction, taker, actor, strength = "HIGH_SWEEP_REJECTION", "DOWN", "BUYERS", "SELLERS", 0.95
        elif acceptance: kind, direction, taker, actor, strength = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "BUYERS", "BUYERS", 0.88
        elif swept: kind, direction, taker, actor, strength = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "BUYERS", "UNCLEAR", 0.55
        else: return None
    else:
        swept = b["low"] < level - sweep
        wick = (min(b["open"], b["close"]) - b["low"]) / max(b["high"] - b["low"], 1e-12)
        rejection = swept and b["close"] >= level - band and wick >= MIN_WICK_RATIO
        failed = p["close"] < level - extension and b["close"] >= level - band
        acceptance = b["close"] < level - extension and body >= MIN_BODY_RATIO
        if failed: kind, direction, taker, actor, strength = "LOW_FAILED_BREAK_RECLAIM", "UP", "SELLERS", "BUYERS", 0.94
        elif rejection: kind, direction, taker, actor, strength = "LOW_SWEEP_REJECTION", "UP", "SELLERS", "BUYERS", 0.95
        elif acceptance: kind, direction, taker, actor, strength = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "SELLERS", "SELLERS", 0.88
        elif swept: kind, direction, taker, actor, strength = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "SELLERS", "UNCLEAR", 0.55
        else: return None
    candle_id, identity_basis = _stable_bar_identity(b, i)
    return {"type": kind, "directional_implication": direction, "liquidity_taker": taker, "response_actor": actor, "strength": strength, "zone": dict(zone), "index": i, "event_atr": float(atr), "event_level": float(level), "event_candle_id": candle_id, "event_candle_identity_basis": identity_basis, "event_candle": {k: b[k] for k in ("open", "high", "low", "close")}, "event_body_ratio": round(body, 6), "event_range_atr": round(range_atr, 6), "event_displacement_atr": round(displacement, 6)}


def _no_event(index: int):
    return {"type": "NO_CONFIRMED_LIQUIDITY_EVENT", "directional_implication": "NEUTRAL", "liquidity_taker": "NONE", "response_actor": "NONE", "strength": 0.30, "zone": None, "index": index, "event_atr": 0.0, "event_level": None, "event_candle_id": None, "event_candle_identity_basis": None}


def _detect_event(bars, atr):
    if len(bars) < MIN_BARS or atr <= 0:
        return _no_event(len(bars) - 1)
    current, price = len(bars) - 1, bars[-1]["close"]
    highs, lows = _pivots(bars)
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    raw_zones = _zones(highs, tolerance, "HIGH", current) + _zones(lows, tolerance, "LOW", current)
    zones = [_classify_zone(z, price, atr) for z in raw_zones]
    candidates = []
    for i in range(max(1, current - FOLLOW_WINDOW), current + 1):
        for zone in zones:
            event = _event_for_zone(bars, zone, atr, i)
            if event:
                candidates.append(event)
    if not candidates:
        return _no_event(current)
    return max(candidates, key=lambda e: (e["index"], e["strength"], e["zone"].get("quality", 0.0), e["zone"].get("touches", 1)))


def _event_class(event):
    kind = str(event.get("type") or "").upper()
    if "FAILED_BREAK" in kind or "REJECTION" in kind: return "REJECTION"
    if "ACCEPTANCE" in kind: return "ACCEPTANCE"
    return "UNRESOLVED"


def _event_level(event) -> float | None:
    value = _num(event.get("event_level"))
    if value is not None: return value
    value = _num(event.get("level"))
    if value is not None: return value
    zone = event.get("zone") or {}
    return _num(zone.get("upper" if str(zone.get("side") or "").upper() == "HIGH" else "lower"))


def _event_id(event, bars):
    zone = event.get("zone")
    if not zone: return None
    i = int(event.get("index", -1))
    candle = event.get("event_candle_id")
    if not candle and 0 <= i < len(bars): candle, _ = _stable_bar_identity(bars[i], i)
    level = _event_level(event)
    return f"{candle}|{event.get('type','UNKNOWN')}|{str(zone.get('side') or '').upper()}|{level:.8f}|{event.get('directional_implication','NEUTRAL')}" if level is not None else f"{candle}|{event.get('type','UNKNOWN')}|{str(zone.get('side') or '').upper()}|UNKNOWN|{event.get('directional_implication','NEUTRAL')}"


def _find_event_index(event, event_id, bars):
    if not event_id: return -1
    i = int(event.get("index", -1))
    if 0 <= i < len(bars) and _event_id(event, bars) == event_id: return i
    candle_id = str(event_id).split("|", 1)[0]
    return next((j for j, bar in enumerate(bars) if _bar_id(bar, j) == candle_id), -1)


def _advance(event, index, bars, current_atr, prior):
    event_id, direction, event_class = _event_id(event, bars), str(event.get("directional_implication") or "NEUTRAL").upper(), _event_class(event)
    level, event_atr = _event_level(event), _num(event.get("event_atr")) or current_atr
    prior = prior if prior and prior.get("event_id") == event_id else None
    if prior and prior.get("lifecycle") in TERMINAL_STATES: return prior["lifecycle"], dict(prior.get("follow") or {}), set(prior.get("processed_candles") or []), int(prior.get("consecutive", 0) or 0)
    if level is None or event_atr <= 0 or direction not in {"UP", "DOWN"} or event_class == "UNRESOLVED":
        return "PENDING", {"reason": "INVALID_EVENT_METRICS", "checks": [], "bars": 0, "available_bars": 0, "required_bars": CONFIRM_BARS, "horizon_bars": 0, "terminal": False, "terminal_lifecycle": "PENDING"}, set(), 0
    processed = set(prior.get("processed_candles") or []) if prior else set()
    checks = list((prior.get("follow") or {}).get("checks") or []) if prior else []
    consecutive = int(prior.get("consecutive", 0) or 0) if prior else 0
    for j in range(index + 1, len(bars)):
        candle_id, identity_basis = _stable_bar_identity(bars[j], j)
        if candle_id in processed: continue
        processed.add(candle_id)
        close = bars[j]["close"]
        displacement = (close - level) / event_atr if direction == "UP" else (level - close) / event_atr
        hold = close > level + event_atr * INTERACTION_ATR if direction == "UP" else close < level - event_atr * INTERACTION_ATR
        opposite = close < level - event_atr * INTERACTION_ATR if direction == "UP" else close > level + event_atr * INTERACTION_ATR
        meaningful = hold and displacement >= MIN_DISPLACEMENT_ATR
        check = {"index": j, "candle_id": candle_id, "identity_basis": identity_basis, "close": close, "hold": hold, "displacement_atr": round(displacement, 6), "meaningful": meaningful, "opposite_reclaim": opposite, "consecutive_before": consecutive}
        if opposite:
            check.update({"consecutive": 0, "terminal": "INVALIDATED"}); checks.append(check)
            return "INVALIDATED", {"present": False, "bars": 0, "available_bars": len(processed), "required_bars": CONFIRM_BARS, "horizon_bars": min(FOLLOW_WINDOW, len(processed)), "invalidated": True, "expired": False, "reason": "POST_EVENT_RECLAMATION", "checks": checks, "confirmed_at": None, "invalidated_at": candle_id, "terminal": True, "terminal_lifecycle": "INVALIDATED"}, processed, 0
        consecutive = consecutive + 1 if meaningful else 0
        check["consecutive"], check["terminal"] = consecutive, "CONFIRMED" if consecutive >= CONFIRM_BARS else None
        checks.append(check)
        if consecutive >= CONFIRM_BARS:
            return "CONFIRMED", {"present": True, "bars": consecutive, "available_bars": len(processed), "required_bars": CONFIRM_BARS, "horizon_bars": min(FOLLOW_WINDOW, len(processed)), "invalidated": False, "expired": False, "reason": "FOLLOW_THROUGH_CONFIRMED", "checks": checks, "confirmed_at": candle_id, "invalidated_at": None, "terminal": True, "terminal_lifecycle": "CONFIRMED", "acceptance_quality": event_class == "ACCEPTANCE", "rejection_quality": event_class == "REJECTION"}, processed, consecutive
    age = len(processed)
    if age >= FOLLOW_WINDOW:
        return "EXPIRED", {"present": False, "bars": consecutive, "available_bars": age, "required_bars": CONFIRM_BARS, "horizon_bars": FOLLOW_WINDOW, "invalidated": False, "expired": True, "reason": "EVENT_EXPIRED", "checks": checks, "confirmed_at": None, "invalidated_at": None, "terminal": True, "terminal_lifecycle": "EXPIRED"}, processed, consecutive
    return "PENDING", {"present": False, "bars": consecutive, "available_bars": age, "required_bars": CONFIRM_BARS, "horizon_bars": age, "invalidated": False, "expired": False, "reason": "FOLLOW_THROUGH_ABSENT" if age else "NO_POST_EVENT_CANDLE", "checks": checks, "confirmed_at": None, "invalidated_at": None, "terminal": False, "terminal_lifecycle": "PENDING"}, processed, consecutive


def _event_index_for_id(event_id, bars):
    if not event_id: return -1
    candle_id = str(event_id).split("|", 1)[0]
    return next((j for j, bar in enumerate(bars) if _bar_id(bar, j) == candle_id), -1)


def _newer_event_wins(candidate, candidate_id, prior, bars):
    if not candidate_id or not prior or not prior.get("event_id"): return True
    if candidate_id == prior["event_id"]: return False
    candidate_index = int(candidate.get("index", -1))
    prior_index = _find_event_index(prior.get("event") or {}, prior["event_id"], bars)
    if prior_index < 0: prior_index = _event_index_for_id(prior["event_id"], bars)
    if prior_index < 0: return candidate_index >= 0
    return candidate_index > prior_index


def _auction_quality(event, lifecycle, follow):
    zone = event.get("zone") or {}
    event_class = _event_class(event)
    zone_quality = float(zone.get("quality") or 0.0)
    displacement = float(event.get("event_displacement_atr") or 0.0)
    body = float(event.get("event_body_ratio") or 0.0)
    range_atr = float(event.get("event_range_atr") or 0.0)
    follow_bars = int(follow.get("bars", 0) or 0)
    meaningful = sum(1 for c in (follow.get("checks") or []) if c.get("meaningful"))
    event_factor = 1.0 if event_class in {"ACCEPTANCE", "REJECTION"} else 0.25
    confirmed_factor = 1.0 if lifecycle == "CONFIRMED" else 0.55 if lifecycle == "PENDING" else 0.20
    quality = 100.0 * (0.25 * zone_quality / 100.0 + 0.15 * event_factor + 0.15 * min(max(displacement, 0.0), 1.0) + 0.10 * min(max(body / 0.70, 0.0), 1.0) + 0.10 * min(max(range_atr / 1.50, 0.0), 1.0) + 0.20 * min(max(meaningful / max(CONFIRM_BARS, 1), 0.0), 1.0) + 0.05 * confirmed_factor)
    counter = []
    if lifecycle != "CONFIRMED": counter.append("AUCTION_NOT_TERMINALLY_CONFIRMED")
    if event_class == "ACCEPTANCE" and follow_bars < CONFIRM_BARS: counter.append("ACCEPTANCE_REQUIRES_FOLLOW_THROUGH")
    if event_class == "REJECTION" and zone_quality < 50.0: counter.append("LOW_LIQUIDITY_QUALITY_REDUCES_REJECTION_SIGNIFICANCE")
    if zone and zone.get("externality") == "INTERNAL": counter.append("INTERNAL_LIQUIDITY_HAS_LOWER_INFORMATIONAL_WEIGHT")
    return {"quality": round(quality, 2), "classification": "HIGH_INFORMATION" if quality >= 75 else "MEDIUM_INFORMATION" if quality >= 50 else "LOW_INFORMATION", "event_class": event_class, "event_type": event.get("type"), "lifecycle": lifecycle, "liquidity_quality": round(zone_quality, 2), "follow_through_bars": follow_bars, "meaningful_follow_through_bars": meaningful, "displacement_atr": round(displacement, 6), "body_ratio": round(body, 6), "range_atr": round(range_atr, 6), "counter_evidence": counter, "interpretation": "PRICE_ACCEPTED_NEW_AUCTION_AREA" if event_class == "ACCEPTANCE" and lifecycle == "CONFIRMED" else "PRICE_REJECTED_LIQUIDITY_AUCTION" if event_class == "REJECTION" and lifecycle == "CONFIRMED" else "AUCTION_EVIDENCE_NOT_YET_DECISIVE"}


def _proof_observations(bars, atr, event, event_id, lifecycle, transition, event_age, follow, processed, last_candle_id, liquidity_map, auction_quality):
    checks = follow.get("checks") or []
    latest_check = checks[-1] if checks else {}
    zone = event.get("zone") or {}
    return [f"closed_candles={len(bars)}", f"atr14_current={atr:.6f}", f"event={event.get('type','NONE')}", f"event_id={event_id or 'NONE'}", f"event_candle_id={event.get('event_candle_id') or 'NONE'}", f"event_candle_identity_basis={event.get('event_candle_identity_basis') or 'NONE'}", f"event_level={_event_level(event) if _event_level(event) is not None else 'NONE'}", f"event_atr_frozen={_num(event.get('event_atr')) or 0.0:.6f}", f"liquidity_taker={event.get('liquidity_taker','NONE')}", f"response_actor={event.get('response_actor','NONE')}", f"liquidity_type={zone.get('kind','NONE')}", f"liquidity_externality={zone.get('externality','NONE')}", f"liquidity_proximity={zone.get('proximity','NONE')}", f"liquidity_quality={zone.get('quality','NONE')}", f"liquidity_zone_count={liquidity_map.get('zone_count',0)}", f"auction_quality={auction_quality.get('quality',0.0)}", f"auction_information={auction_quality.get('classification','UNKNOWN')}", f"auction_state={lifecycle}", f"transition={transition}", f"event_age_bars={event_age}", f"processed_candles={len(processed)}", f"last_processed_candle_id={last_candle_id or 'NONE'}", f"follow_through_bars={follow.get('bars', 0)}", f"required_confirmation_bars={CONFIRM_BARS}", f"confirmation_horizon={FOLLOW_WINDOW}", f"latest_check={latest_check.get('candle_id','NONE')}:{latest_check.get('terminal') or ('MEANINGFUL' if latest_check.get('meaningful') else 'NON_MEANINGFUL')}", f"terminal={lifecycle in TERMINAL_STATES}"]


def _audit_snapshot(state_key, record):
    global _AUDIT_SEQUENCE
    _AUDIT_SEQUENCE += 1
    entry = dict(record); entry["audit_sequence"] = _AUDIT_SEQUENCE; entry["state_key"] = state_key
    trail = _AUDIT_TRAIL.setdefault(state_key, []); trail.append(entry)
    if len(trail) > AUDIT_LIMIT: del trail[:-AUDIT_LIMIT]


def analyze_e4(snapshot=None, evidence_bus=None):
    """E4 liquidity-map and auction-quality analyst. E9 remains final authority."""
    bars = _bars(snapshot)
    market, timeframe, source = _market(snapshot), _timeframe(snapshot), _source(snapshot)
    state_key, current_atr = _state_key(snapshot), _atr(bars)
    current_candle_id = _bar_id(bars[-1], len(bars) - 1) if bars else None
    current_price = bars[-1]["close"] if bars else 0.0
    liquidity_map = _liquidity_map(bars, current_atr)
    detected, detected_id, prior = _detect_event(bars, current_atr), None, _LIFECYCLE_STATE.get(state_key)
    detected_id = _event_id(detected, bars)
    if prior and prior.get("event_id") == detected_id:
        event, event_id, event_index, previous, event_origin = dict(prior.get("event") or detected), prior["event_id"], _find_event_index(prior.get("event") or detected, prior["event_id"], bars), prior, "RESUME_EXISTING_EVENT"
    elif detected_id and _newer_event_wins(detected, detected_id, prior, bars):
        event, event_id, event_index, previous, event_origin = dict(detected), detected_id, int(detected.get("index", -1)), None, "NEW_CAUSAL_EVENT"
    elif prior and prior.get("event_id"):
        event, event_id, event_index, previous, event_origin = dict(prior.get("event") or {}), prior["event_id"], _find_event_index(prior.get("event") or {}, prior["event_id"], bars), prior, "HOLD_EXISTING_EVENT"
    else:
        event, event_id, event_index, previous, event_origin = detected, detected_id, int(detected.get("index", -1)), None, "NO_PERSISTED_EVENT"
    previous_lifecycle = previous.get("lifecycle") if previous else None
    if event_id and event_index >= 0:
        lifecycle, follow, processed, consecutive = _advance(event, event_index, bars, current_atr, previous)
        last_processed = current_candle_id
        _LIFECYCLE_STATE[state_key] = {"event_id": event_id, "event": dict(event), "lifecycle": lifecycle, "processed_candles": set(processed), "consecutive": consecutive, "follow": dict(follow), "event_index": event_index, "event_age_bars": max(0, len(bars) - 1 - event_index), "last_processed_candle_id": last_processed, "last_closed_candle_id": current_candle_id, "event_origin": event_origin, "identity_basis": event.get("event_candle_identity_basis")}
    else:
        lifecycle, follow, processed, consecutive, last_processed = "PENDING", {"reason": "NO_LIQUIDITY_EVENT", "bars": 0, "available_bars": 0, "required_bars": CONFIRM_BARS, "horizon_bars": 0, "checks": [], "terminal": False, "terminal_lifecycle": "PENDING"}, set(), 0, (prior or {}).get("last_processed_candle_id")
    event_class, confirmed = _event_class(event), lifecycle == "CONFIRMED"
    state_name = "ACCEPTANCE_CONFIRMED" if confirmed and event_class == "ACCEPTANCE" else "REJECTION_CONFIRMED" if confirmed and event_class == "REJECTION" else "AUCTION_CONFIRMED" if confirmed else "INVALIDATED" if lifecycle == "INVALIDATED" else "EXPIRED" if lifecycle == "EXPIRED" else "ACCEPTANCE_PENDING" if event_class == "ACCEPTANCE" else "REJECTION_PENDING" if event_class == "REJECTION" else "UNRESOLVED"
    direction = str(event.get("directional_implication") or "NEUTRAL").upper() if confirmed else "NEUTRAL"
    event_age = max(0, len(bars) - 1 - event_index) if event_index >= 0 else int((prior or {}).get("event_age_bars", 0) or 0)
    transition, terminal_reason = f"{previous_lifecycle or 'NONE'}->{lifecycle}", follow.get("reason") if lifecycle in TERMINAL_STATES else None
    auction_quality = _auction_quality(event, lifecycle, follow)
    if not event.get("zone"): finding, reasons = "NO_LIQUIDITY_EVENT", ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]
    elif lifecycle == "CONFIRMED": finding, reasons = f"{event.get('type','LIQUIDITY_EVENT')}_CONFIRMED", []
    elif lifecycle == "INVALIDATED": finding, reasons = f"{event.get('type','LIQUIDITY_EVENT')}_INVALIDATED", ["AUCTION_THESIS_INVALIDATED", "POST_EVENT_RECLAMATION"]
    elif lifecycle == "EXPIRED": finding, reasons = f"{event.get('type','LIQUIDITY_EVENT')}_EXPIRED", ["AUCTION_THESIS_EXPIRED", "NO_SUFFICIENT_FOLLOW_THROUGH"]
    else: finding, reasons = str(event.get("type", "LIQUIDITY_EVENT")), ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]
    reasons = list(dict.fromkeys(reasons + auction_quality.get("counter_evidence", [])))
    observations = _proof_observations(bars, current_atr, event, event_id, lifecycle, transition, event_age, follow, processed, last_processed, liquidity_map, auction_quality)
    observations.extend([f"market={market}", f"timeframe={timeframe}", f"source={source}", f"state_key={state_key}", f"current_closed_candle_id={current_candle_id or 'NONE'}", f"event_origin={event_origin}"])
    prior_event_id = previous.get("event_id") if previous else None
    audit_record = {"current_closed_candle_id": current_candle_id, "detected_event_id": detected_id, "active_event_id": event_id, "prior_event_id": prior_event_id, "event_origin": event_origin, "lifecycle_before": previous_lifecycle, "lifecycle_after": lifecycle, "transition": transition, "event_age_bars": event_age, "processed_candle_count": len(processed), "last_processed_candle_id": last_processed, "detected_type": detected.get("type"), "active_type": event.get("type"), "event_candle_id": event.get("event_candle_id"), "event_identity_basis": event.get("event_candle_identity_basis"), "event_level": _event_level(event), "event_atr_frozen": _num(event.get("event_atr")), "current_atr": current_atr, "event_class": event_class, "direction": direction, "follow_through_bars": follow.get("bars", 0), "required_confirmation_bars": CONFIRM_BARS, "confirmation_horizon": FOLLOW_WINDOW, "terminal": lifecycle in TERMINAL_STATES, "terminal_reason": terminal_reason, "checks": list(follow.get("checks") or []), "persistence_action": event_origin, "idempotent": True, "liquidity_map_zone_count": liquidity_map.get("zone_count", 0), "auction_quality": auction_quality.get("quality"), "auction_information": auction_quality.get("classification")}
    _audit_snapshot(state_key, audit_record)
    audit_trail = list(_AUDIT_TRAIL.get(state_key, []))
    return {"architecture": ARCHITECTURE, "professional_brain": True, "role": E4_ROLE, "question": PROFESSIONAL_QUESTION, "finding": finding, "analyst_conclusion": finding, "event": event, "event_id": event_id, "event_age_bars": event_age, "lifecycle": lifecycle, "lifecycle_transition": transition, "terminal_state": lifecycle if lifecycle in TERMINAL_STATES else None, "terminal_reason": terminal_reason, "auction_state": state_name, "auction_confirmation_state": state_name, "auction_confirmation": {"confirmed": confirmed, "state": state_name}, "auction": {"state": state_name, "confirmed": confirmed, "follow_through_bars": follow.get("bars", 0), "lifecycle": lifecycle, "event_class": event_class, "event_id": event_id, "event_age_bars": event_age, "transition": transition, "terminal": lifecycle in TERMINAL_STATES, "terminal_reason": terminal_reason, "processed_candles": len(processed), "last_processed_candle_id": last_processed, "detail": follow, "quality": auction_quality}, "liquidity_map": liquidity_map, "liquidity": {"active_event_zone": event.get("zone"), "nearest_above": liquidity_map.get("nearest_above"), "nearest_below": liquidity_map.get("nearest_below"), "external_above": liquidity_map.get("external_above"), "external_below": liquidity_map.get("external_below"), "zone_count": liquidity_map.get("zone_count", 0)}, "auction_quality": auction_quality, "follow_through": follow, "follow_through_bars": follow.get("bars", 0), "direction": direction, "directional_implication": direction, "direction_confirmed": confirmed, "liquidity_taker": event.get("liquidity_taker", "NONE"), "response_actor": event.get("response_actor", "NONE"), "observations": observations, "reasons": reasons, "reason_codes": reasons, "counter_evidence": list(dict.fromkeys(["POST_EVENT_RECLAMATION" if lifecycle == "INVALIDATED" else "NO_FOLLOW_THROUGH", "AUCTION_DIRECTION_REMAINS_UNRESOLVED" if not confirmed else "OPPOSITE_LIQUIDITY_EVENT_CHALLENGES_THESIS", *auction_quality.get("counter_evidence", [])])), "invalidation": ["post-event close through defended liquidity level invalidates thesis before confirmation", "event expiry without sufficient follow-through prevents confirmation", "a newer causal event starts a new independent E4 lifecycle"], "decision": None, "gate": None, "gate_passed": None, "score": None, "trade_decision_authority": False, "decision_authority": "E9_ONLY", "reasoning_role": E4_ROLE, "upstream_decisions_used": False, "upstream_gates_used": False, "scores_used": False, "score_used": False, "professional_reasoning": {"thesis_status": lifecycle, "actor_identification": "INFERENCE_FROM_OHLC_ONLY", "liquidity_map_method": "CONFIRMED_PIVOTS_CLUSTERED_BY_ATR", "auction_quality_method": "LIQUIDITY_QUALITY_PLUS_EVENT_RESPONSE_PLUS_FOLLOW_THROUGH", "lifecycle_rule": "PENDING -> exactly one terminal state: CONFIRMED|INVALIDATED|EXPIRED; first terminal wins per event_id", "response": {"status": lifecycle, "direction": direction, "actor": event.get("response_actor", "NONE")}}, "identity": {"state_key": state_key, "market": market, "timeframe": timeframe, "source": source, "event_id": event_id, "event_candle_id": event.get("event_candle_id"), "event_candle_identity_basis": event.get("event_candle_identity_basis"), "identity_rule": "timestamp/time/datetime/date/candle/open_time/close_time, else deterministic OHLC SHA256", "index_is_not_identity": True}, "persistence": {"enabled": True, "scope": "PROCESS_LOCAL", "state_key": state_key, "same_event_resumes": True, "terminal_state_immutable": True, "first_terminal_wins": True, "processed_candles_are_idempotent": True, "event_atr_and_level_frozen": True, "durable_across_process_restart": False, "durability_limit": "NO_EXTERNAL_STORAGE_ALLOWED_BY_FILE_SCOPE"}, "audit": {"complete": True, "audit_sequence": _AUDIT_SEQUENCE, "trail_size": len(audit_trail), "trail_limit": AUDIT_LIMIT, "latest": audit_record, "trail": audit_trail, "closed_candle_only": True, "no_lookahead": True, "actor_identification": "PRICE_ACTION_INFERENCE_ONLY", "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW", "auction_state": state_name, "auction_event_class": event_class, "event_id": event_id, "event_candle_id": event.get("event_candle_id"), "event_level": _event_level(event), "event_atr_frozen": _num(event.get("event_atr")), "current_atr": current_atr, "event_age_bars": event_age, "lifecycle": lifecycle, "lifecycle_transition": transition, "follow_through_bars": follow.get("bars", 0), "available_post_event_bars": follow.get("available_bars", 0), "required_confirmation_bars": CONFIRM_BARS, "confirmation_horizon": FOLLOW_WINDOW, "terminal_states": list(TERMINAL_STATES), "terminal_state_immutable": True, "first_terminal_wins": True, "persistent_state": True, "state_key": state_key, "processed_candles": len(processed), "last_processed_candle_id": last_processed, "last_closed_candle_id": current_candle_id, "event_origin": event_origin, "newer_event_precedence": "CAUSAL_TIME", "direction_authority": "E4_AUCTION_EVIDENCE_ONLY", "audit_trail_is_process_local": True, "audit_trail_complete_for_current_process": True, "liquidity_map_zone_count": liquidity_map.get("zone_count", 0), "liquidity_map_equal_liquidity_count": liquidity_map.get("equal_liquidity_count", 0), "liquidity_map_external_levels": sum(z.get("externality") == "EXTERNAL" for z in liquidity_map.get("zones", [])), "auction_quality": auction_quality}}


__all__ = ["analyze_e4", "ARCHITECTURE"]
