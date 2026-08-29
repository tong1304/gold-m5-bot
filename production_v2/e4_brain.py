from __future__ import annotations

from math import isfinite
from statistics import mean
from typing import Any

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V35"
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
TERMINAL_STATES = ("CONFIRMED", "INVALIDATED", "EXPIRED")

# Runtime-persistent FSM. Lifecycle identity is the causal event_id, never a
# rolling-array index. State is intentionally process-local: E4 has no external
# storage contract, but it survives repeated analyze_e4() calls in one worker.
_LIFECYCLE_STATE: dict[str, dict[str, Any]] = {}


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
        if v["high"] < max(v["open"], v["close"]):
            continue
        if v["low"] > min(v["open"], v["close"]):
            continue
        if v["high"] < v["low"]:
            continue
        out.append({**raw_bar, **v})
    return out


def _bar_id(bar: dict[str, Any], fallback: int) -> str:
    for key in ("timestamp", "time", "datetime", "date", "candle", "open_time", "close_time"):
        value = bar.get(key)
        if value not in (None, ""):
            return str(value)
    return f"INDEX_FALLBACK:{fallback}"


def _market(snapshot: Any) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"
    for key in ("symbol", "instrument", "market", "ticker", "asset"):
        if snapshot.get(key):
            return str(snapshot[key]).upper()
    return "UNKNOWN"


def _atr(bars: list[dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    tr: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(tr[-period:]) if tr else 0.0


def _body_ratio(bar: dict[str, Any]) -> float:
    return abs(bar["close"] - bar["open"]) / max(bar["high"] - bar["low"], 1e-12)


def _pivots(bars: list[dict[str, Any]]):
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(PIVOT_WING, len(bars) - PIVOT_WING):
        window = bars[i - PIVOT_WING : i + PIVOT_WING + 1]
        if bars[i]["high"] >= max(x["high"] for x in window):
            highs.append((i, bars[i]["high"]))
        if bars[i]["low"] <= min(x["low"] for x in window):
            lows.append((i, bars[i]["low"]))
    return highs[-LOOKBACK_PIVOTS:], lows[-LOOKBACK_PIVOTS:]


def _zones(levels, tolerance, side, current):
    groups: list[list[tuple[int, float]]] = []
    for item in sorted(levels, key=lambda x: x[1]):
        if not groups or abs(item[1] - mean(p for _, p in groups[-1])) > tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    result = []
    for group in groups:
        prices = [p for _, p in group]
        last_touch = max(i for i, _ in group)
        age = max(0, current - last_touch)
        result.append({
            "side": side,
            "price": mean(prices),
            "lower": min(prices),
            "upper": max(prices),
            "touches": len(group),
            "last_touch_index": last_touch,
            "age_bars": age,
            "kind": "EQUAL_LIQUIDITY" if len(group) >= 2 else "SWING_LIQUIDITY",
            "freshness": "FRESH" if age <= 24 else "AGED",
        })
    return result


def _event_for_zone(bars, zone, atr, i):
    if i <= zone["last_touch_index"] or i <= 0 or atr <= 0:
        return None
    b, p = bars[i], bars[i - 1]
    level = zone["upper"] if zone["side"] == "HIGH" else zone["lower"]
    sweep = max(atr * SWEEP_ATR, 1e-9)
    band = max(atr * CLOSE_TOLERANCE_ATR, 1e-9)
    extension = max(atr * ACCEPTANCE_ATR, 1e-9)
    if zone["side"] == "HIGH":
        swept = b["high"] > level + sweep
        wick = (b["high"] - max(b["open"], b["close"])) / max(b["high"] - b["low"], 1e-12)
        rejection = swept and b["close"] <= level + band and wick >= MIN_WICK_RATIO
        failed = p["close"] > level + extension and b["close"] <= level + band
        acceptance = b["close"] > level + extension and _body_ratio(b) >= MIN_BODY_RATIO
        if failed:
            kind, direction, taker, actor, strength = "HIGH_FAILED_BREAK_RECLAIM", "DOWN", "BUYERS", "SELLERS", 0.94
        elif rejection:
            kind, direction, taker, actor, strength = "HIGH_SWEEP_REJECTION", "DOWN", "BUYERS", "SELLERS", 0.95
        elif acceptance:
            kind, direction, taker, actor, strength = "HIGH_ACCEPTANCE_CANDIDATE", "UP", "BUYERS", "BUYERS", 0.88
        elif swept:
            kind, direction, taker, actor, strength = "HIGH_LIQUIDITY_INTERACTION", "NEUTRAL", "BUYERS", "UNCLEAR", 0.55
        else:
            return None
    else:
        swept = b["low"] < level - sweep
        wick = (min(b["open"], b["close"]) - b["low"]) / max(b["high"] - b["low"], 1e-12)
        rejection = swept and b["close"] >= level - band and wick >= MIN_WICK_RATIO
        failed = p["close"] < level - extension and b["close"] >= level - band
        acceptance = b["close"] < level - extension and _body_ratio(b) >= MIN_BODY_RATIO
        if failed:
            kind, direction, taker, actor, strength = "LOW_FAILED_BREAK_RECLAIM", "UP", "SELLERS", "BUYERS", 0.94
        elif rejection:
            kind, direction, taker, actor, strength = "LOW_SWEEP_REJECTION", "UP", "SELLERS", "BUYERS", 0.95
        elif acceptance:
            kind, direction, taker, actor, strength = "LOW_ACCEPTANCE_CANDIDATE", "DOWN", "SELLERS", "SELLERS", 0.88
        elif swept:
            kind, direction, taker, actor, strength = "LOW_LIQUIDITY_INTERACTION", "NEUTRAL", "SELLERS", "UNCLEAR", 0.55
        else:
            return None
    return {
        "type": kind,
        "directional_implication": direction,
        "liquidity_taker": taker,
        "response_actor": actor,
        "strength": strength,
        "zone": dict(zone),
        "index": i,
        "event_atr": float(atr),
        "event_level": float(level),
        "event_candle_id": _bar_id(b, i),
        "event_candle": {k: b[k] for k in ("open", "high", "low", "close")},
    }


def _no_event(index: int):
    return {
        "type": "NO_CONFIRMED_LIQUIDITY_EVENT",
        "directional_implication": "NEUTRAL",
        "liquidity_taker": "NONE",
        "response_actor": "NONE",
        "strength": 0.30,
        "zone": None,
        "index": index,
        "event_atr": 0.0,
        "event_level": None,
        "event_candle_id": None,
    }


def _detect_event(bars, atr):
    if len(bars) < MIN_BARS or atr <= 0:
        return _no_event(len(bars) - 1)
    highs, lows = _pivots(bars)
    current = len(bars) - 1
    tolerance = max(atr * ZONE_TOLERANCE_ATR, 1e-9)
    zones = _zones(highs, tolerance, "HIGH", current) + _zones(lows, tolerance, "LOW", current)
    candidates = []
    # Detection is bounded to the confirmation horizon. A previously persisted
    # event always wins over rediscovery of the same causal candle.
    for i in range(max(1, current - FOLLOW_WINDOW), current + 1):
        for zone in zones:
            event = _event_for_zone(bars, zone, atr, i)
            if event:
                candidates.append(event)
    if not candidates:
        return _no_event(current)
    return max(candidates, key=lambda e: (e["index"], e["strength"], e["zone"].get("touches", 1)))


def _event_class(event):
    kind = str(event.get("type") or "").upper()
    if "FAILED_BREAK" in kind or "REJECTION" in kind:
        return "REJECTION"
    if "ACCEPTANCE" in kind:
        return "ACCEPTANCE"
    return "UNRESOLVED"


def _event_level(event) -> float | None:
    value = _num(event.get("event_level"))
    if value is not None:
        return value
    value = _num(event.get("level"))
    if value is not None:
        return value
    zone = event.get("zone") or {}
    side = str(zone.get("side") or "").upper()
    return _num(zone.get("upper" if side == "HIGH" else "lower"))


def _event_id(event, bars):
    zone = event.get("zone")
    if not zone:
        return None
    i = int(event.get("index", -1))
    candle = event.get("event_candle_id") or (_bar_id(bars[i], i) if 0 <= i < len(bars) else "UNKNOWN")
    side = str(zone.get("side") or "").upper()
    level = _event_level(event)
    level_text = f"{level:.8f}" if level is not None else "UNKNOWN"
    return f"{candle}|{event.get('type','UNKNOWN')}|{side}|{level_text}|{event.get('directional_implication','NEUTRAL')}"


def _find_event_index(event, event_id, bars):
    if not event_id:
        return -1
    i = int(event.get("index", -1))
    if 0 <= i < len(bars) and _event_id(event, bars) == event_id:
        return i
    candle_id = str(event_id).split("|", 1)[0]
    for j, bar in enumerate(bars):
        if _bar_id(bar, j) == candle_id:
            return j
    return -1


def _advance(event, index, bars, current_atr, prior):
    """Advance one causal event without re-evaluating already processed candles.

    The event ATR and level are frozen at event creation. This prevents later
    volatility changes from changing the meaning of a historical confirmation.
    A terminal state is immutable for that event_id.
    """
    event_id = _event_id(event, bars)
    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    event_class = _event_class(event)
    level = _event_level(event)
    event_atr = _num(event.get("event_atr")) or current_atr
    prior = prior if prior and prior.get("event_id") == event_id else None

    if prior and prior.get("lifecycle") in TERMINAL_STATES:
        return (
            prior["lifecycle"],
            dict(prior.get("follow") or {}),
            set(prior.get("processed_candles") or []),
            int(prior.get("consecutive", 0) or 0),
        )

    if level is None or event_atr <= 0 or direction not in {"UP", "DOWN"} or event_class == "UNRESOLVED":
        return "PENDING", {"reason": "INVALID_EVENT_METRICS", "checks": [], "bars": 0, "available_bars": 0, "required_bars": CONFIRM_BARS, "horizon_bars": 0, "terminal": False, "terminal_lifecycle": "PENDING"}, set(), 0

    processed = set(prior.get("processed_candles") or []) if prior else set()
    checks = list((prior.get("follow") or {}).get("checks") or []) if prior else []
    consecutive = int(prior.get("consecutive", 0) or 0) if prior else 0

    # Causal order is determined by the current closed-candle array, but each
    # candle can enter the FSM only once by immutable candle id.
    for j in range(index + 1, len(bars)):
        candle_id = _bar_id(bars[j], j)
        if candle_id in processed:
            continue
        processed.add(candle_id)
        close = bars[j]["close"]
        displacement = (close - level) / event_atr if direction == "UP" else (level - close) / event_atr
        hold = close > level + event_atr * INTERACTION_ATR if direction == "UP" else close < level - event_atr * INTERACTION_ATR
        opposite = close < level - event_atr * INTERACTION_ATR if direction == "UP" else close > level + event_atr * INTERACTION_ATR
        meaningful = hold and displacement >= MIN_DISPLACEMENT_ATR
        check = {
            "index": j,
            "candle_id": candle_id,
            "close": close,
            "hold": hold,
            "displacement_atr": round(displacement, 6),
            "meaningful": meaningful,
            "opposite_reclaim": opposite,
            "consecutive_before": consecutive,
        }
        if opposite:
            check.update({"consecutive": 0, "terminal": "INVALIDATED"})
            checks.append(check)
            return "INVALIDATED", {
                "present": False, "bars": 0, "available_bars": len(processed),
                "required_bars": CONFIRM_BARS, "horizon_bars": min(FOLLOW_WINDOW, len(processed)),
                "invalidated": True, "expired": False, "reason": "POST_EVENT_RECLAMATION",
                "checks": checks, "confirmed_at": None, "invalidated_at": candle_id,
                "terminal": True, "terminal_lifecycle": "INVALIDATED",
            }, processed, 0
        consecutive = consecutive + 1 if meaningful else 0
        check["consecutive"] = consecutive
        check["terminal"] = "CONFIRMED" if consecutive >= CONFIRM_BARS else None
        checks.append(check)
        if consecutive >= CONFIRM_BARS:
            return "CONFIRMED", {
                "present": True, "bars": consecutive, "available_bars": len(processed),
                "required_bars": CONFIRM_BARS, "horizon_bars": min(FOLLOW_WINDOW, len(processed)),
                "invalidated": False, "expired": False, "reason": "FOLLOW_THROUGH_CONFIRMED",
                "checks": checks, "confirmed_at": candle_id, "invalidated_at": None,
                "terminal": True, "terminal_lifecycle": "CONFIRMED",
                "acceptance_quality": event_class == "ACCEPTANCE",
                "rejection_quality": event_class == "REJECTION",
            }, processed, consecutive

    age = len(processed)
    if age >= FOLLOW_WINDOW:
        return "EXPIRED", {
            "present": False, "bars": consecutive, "available_bars": age,
            "required_bars": CONFIRM_BARS, "horizon_bars": FOLLOW_WINDOW,
            "invalidated": False, "expired": True, "reason": "EVENT_EXPIRED",
            "checks": checks, "confirmed_at": None, "invalidated_at": None,
            "terminal": True, "terminal_lifecycle": "EXPIRED",
        }, processed, consecutive

    return "PENDING", {
        "present": False, "bars": consecutive, "available_bars": age,
        "required_bars": CONFIRM_BARS, "horizon_bars": age,
        "invalidated": False, "expired": False,
        "reason": "FOLLOW_THROUGH_ABSENT" if age else "NO_POST_EVENT_CANDLE",
        "checks": checks, "confirmed_at": None, "invalidated_at": None,
        "terminal": False, "terminal_lifecycle": "PENDING",
    }, processed, consecutive


def _newer_event_wins(candidate, candidate_id, prior, bars) -> bool:
    if not candidate_id or not prior or not prior.get("event_id"):
        return True
    if candidate_id == prior["event_id"]:
        return False
    candidate_index = int(candidate.get("index", -1))
    prior_event = prior.get("event") or {}
    prior_index = _find_event_index(prior_event, prior["event_id"], bars)
    if prior_index < 0:
        prior_candle = str(prior["event_id"]).split("|", 1)[0]
        prior_index = next((j for j, b in enumerate(bars) if _bar_id(b, j) == prior_candle), -1)
    # A candidate may replace only an older causal event. Equal/older events
    # cannot rewind the FSM.
    return candidate_index > prior_index >= 0


def _proof_observations(bars, atr, event, event_id, lifecycle, transition, event_age, follow, processed, last_candle_id):
    checks = follow.get("checks") or []
    latest_check = checks[-1] if checks else {}
    return [
        f"closed_candles={len(bars)}",
        f"atr14_current={atr:.6f}",
        f"event={event.get('type','NONE')}",
        f"event_id={event_id or 'NONE'}",
        f"event_candle_id={event.get('event_candle_id') or 'NONE'}",
        f"event_level={_event_level(event) if _event_level(event) is not None else 'NONE'}",
        f"event_atr_frozen={_num(event.get('event_atr')) or 0.0:.6f}",
        f"liquidity_taker={event.get('liquidity_taker','NONE')}",
        f"response_actor={event.get('response_actor','NONE')}",
        f"auction_state={lifecycle}",
        f"transition={transition}",
        f"event_age_bars={event_age}",
        f"processed_candles={len(processed)}",
        f"last_processed_candle_id={last_candle_id or 'NONE'}",
        f"follow_through_bars={follow.get('bars', 0)}",
        f"required_confirmation_bars={CONFIRM_BARS}",
        f"confirmation_horizon={FOLLOW_WINDOW}",
        f"latest_check={latest_check.get('candle_id','NONE')}:{latest_check.get('terminal') or ('MEANINGFUL' if latest_check.get('meaningful') else 'NON_MEANINGFUL')}",
        f"terminal={lifecycle in TERMINAL_STATES}",
    ]


def analyze_e4(snapshot=None, evidence_bus=None):
    """E4 deterministic liquidity/auction analyst; E9 retains trade authority."""
    bars = _bars(snapshot)
    market = _market(snapshot)
    current_atr = _atr(bars)
    detected = _detect_event(bars, current_atr)
    detected_id = _event_id(detected, bars)
    prior = _LIFECYCLE_STATE.get(market)

    # Same event_id always resumes the existing FSM. A newer causal event can
    # start a new lifecycle; an older/rediscovered event can never rewind it.
    if prior and prior.get("event_id") == detected_id:
        event = dict(prior.get("event") or detected)
        event_id = prior["event_id"]
        event_index = _find_event_index(event, event_id, bars)
        previous = prior
        event_origin = "RESUME_EXISTING_EVENT"
    elif detected_id and _newer_event_wins(detected, detected_id, prior, bars):
        event = dict(detected)
        event_id = detected_id
        event_index = int(detected.get("index", -1))
        previous = None
        event_origin = "NEW_CAUSAL_EVENT"
    elif prior and prior.get("event_id"):
        event = dict(prior.get("event") or {})
        event_id = prior["event_id"]
        event_index = _find_event_index(event, event_id, bars)
        previous = prior
        event_origin = "HOLD_EXISTING_EVENT"
    else:
        event, event_id, event_index, previous = detected, detected_id, int(detected.get("index", -1)), None
        event_origin = "NO_PERSISTED_EVENT"

    if event_id and event_index >= 0:
        lifecycle, follow, processed, consecutive = _advance(event, event_index, bars, current_atr, previous)
        previous_lifecycle = previous.get("lifecycle") if previous else None
        last_processed = _bar_id(bars[-1], len(bars) - 1) if bars else None
        _LIFECYCLE_STATE[market] = {
            "event_id": event_id,
            "event": dict(event),
            "lifecycle": lifecycle,
            "processed_candles": set(processed),
            "consecutive": consecutive,
            "follow": dict(follow),
            "event_index": event_index,
            "event_age_bars": max(0, len(bars) - 1 - event_index),
            "last_processed_candle_id": last_processed,
            "last_closed_candle_id": last_processed,
            "event_origin": event_origin,
        }
    else:
        lifecycle = "PENDING"
        follow = {"reason": "NO_LIQUIDITY_EVENT", "bars": 0, "available_bars": 0, "required_bars": CONFIRM_BARS, "horizon_bars": 0, "checks": [], "terminal": False, "terminal_lifecycle": "PENDING"}
        processed = set()
        consecutive = 0
        previous_lifecycle = prior.get("lifecycle") if prior else None
        last_processed = (_LIFECYCLE_STATE.get(market) or {}).get("last_processed_candle_id")

    event_class = _event_class(event)
    confirmed = lifecycle == "CONFIRMED"
    if lifecycle == "CONFIRMED":
        state_name = "ACCEPTANCE_CONFIRMED" if event_class == "ACCEPTANCE" else "REJECTION_CONFIRMED" if event_class == "REJECTION" else "AUCTION_CONFIRMED"
    elif lifecycle == "INVALIDATED":
        state_name = "INVALIDATED"
    elif lifecycle == "EXPIRED":
        state_name = "EXPIRED"
    elif event_class == "ACCEPTANCE":
        state_name = "ACCEPTANCE_PENDING"
    elif event_class == "REJECTION":
        state_name = "REJECTION_PENDING"
    else:
        state_name = "UNRESOLVED"

    direction = str(event.get("directional_implication") or "NEUTRAL").upper() if confirmed else "NEUTRAL"
    event_age = max(0, len(bars) - 1 - event_index) if event_index >= 0 else int((_LIFECYCLE_STATE.get(market) or {}).get("event_age_bars", 0) or 0)
    transition = f"{previous_lifecycle or 'NONE'}->{lifecycle}"
    terminal_reason = follow.get("reason") if lifecycle in TERMINAL_STATES else None
    last_processed = (_LIFECYCLE_STATE.get(market) or {}).get("last_processed_candle_id", last_processed)

    if not event.get("zone"):
        finding, reasons = "NO_LIQUIDITY_EVENT", ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]
    elif lifecycle == "CONFIRMED":
        finding, reasons = f"{event.get('type','LIQUIDITY_EVENT')}_CONFIRMED", []
    elif lifecycle == "INVALIDATED":
        finding, reasons = f"{event.get('type','LIQUIDITY_EVENT')}_INVALIDATED", ["AUCTION_THESIS_INVALIDATED", "POST_EVENT_RECLAMATION"]
    elif lifecycle == "EXPIRED":
        finding, reasons = f"{event.get('type','LIQUIDITY_EVENT')}_EXPIRED", ["AUCTION_THESIS_EXPIRED", "NO_SUFFICIENT_FOLLOW_THROUGH"]
    else:
        finding, reasons = str(event.get("type", "LIQUIDITY_EVENT")), ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]

    observations = _proof_observations(bars, current_atr, event, event_id, lifecycle, transition, event_age, follow, processed, last_processed)
    observations.append(f"event_origin={event_origin}")

    return {
        "architecture": ARCHITECTURE,
        "professional_brain": True,
        "role": E4_ROLE,
        "question": PROFESSIONAL_QUESTION,
        "finding": finding,
        "analyst_conclusion": finding,
        "event": event,
        "event_id": event_id,
        "event_age_bars": event_age,
        "lifecycle": lifecycle,
        "lifecycle_transition": transition,
        "terminal_state": lifecycle if lifecycle in TERMINAL_STATES else None,
        "terminal_reason": terminal_reason,
        "auction_state": state_name,
        "auction_confirmation_state": state_name,
        "auction_confirmation": {"confirmed": confirmed, "state": state_name},
        "auction": {
            "state": state_name,
            "confirmed": confirmed,
            "follow_through_bars": follow.get("bars", 0),
            "lifecycle": lifecycle,
            "event_class": event_class,
            "event_id": event_id,
            "event_age_bars": event_age,
            "transition": transition,
            "terminal": lifecycle in TERMINAL_STATES,
            "terminal_reason": terminal_reason,
            "processed_candles": len(processed),
            "last_processed_candle_id": last_processed,
            "detail": follow,
        },
        "follow_through": follow,
        "follow_through_bars": follow.get("bars", 0),
        "direction": direction,
        "directional_implication": direction,
        "direction_confirmed": confirmed,
        "liquidity_taker": event.get("liquidity_taker", "NONE"),
        "response_actor": event.get("response_actor", "NONE"),
        "observations": observations,
        "reasons": reasons,
        "reason_codes": reasons,
        "counter_evidence": [
            "POST_EVENT_RECLAMATION" if lifecycle == "INVALIDATED" else "NO_FOLLOW_THROUGH",
            "AUCTION_DIRECTION_REMAINS_UNRESOLVED" if not confirmed else "OPPOSITE_LIQUIDITY_EVENT_CHALLENGES_THESIS",
        ],
        "invalidation": [
            "post-event close through defended liquidity level invalidates thesis before confirmation",
            "event expiry without sufficient follow-through prevents confirmation",
            "a newer causal event starts a new independent E4 lifecycle",
        ],
        "decision": None,
        "gate": None,
        "gate_passed": None,
        "score": None,
        "trade_decision_authority": False,
        "decision_authority": "E9_ONLY",
        "reasoning_role": E4_ROLE,
        "upstream_decisions_used": False,
        "upstream_gates_used": False,
        "scores_used": False,
        "score_used": False,
        "professional_reasoning": {
            "thesis_status": lifecycle,
            "actor_identification": "INFERENCE_FROM_OHLC_ONLY",
            "lifecycle_rule": "PENDING -> exactly one terminal state: CONFIRMED|INVALIDATED|EXPIRED; first terminal wins per event_id",
            "response": {"status": lifecycle, "direction": direction, "actor": event.get("response_actor", "NONE")},
        },
        "audit": {
            "closed_candle_only": True,
            "no_lookahead": True,
            "actor_identification": "PRICE_ACTION_INFERENCE_ONLY",
            "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW",
            "auction_state": state_name,
            "auction_event_class": event_class,
            "event_id": event_id,
            "event_candle_id": event.get("event_candle_id"),
            "event_level": _event_level(event),
            "event_atr_frozen": _num(event.get("event_atr")),
            "current_atr": current_atr,
            "event_age_bars": event_age,
            "lifecycle": lifecycle,
            "lifecycle_transition": transition,
            "follow_through_bars": follow.get("bars", 0),
            "available_post_event_bars": follow.get("available_bars", 0),
            "required_confirmation_bars": CONFIRM_BARS,
            "confirmation_horizon": FOLLOW_WINDOW,
            "terminal_states": list(TERMINAL_STATES),
            "terminal_state_immutable": True,
            "first_terminal_wins": True,
            "persistent_state": True,
            "state_key": market,
            "processed_candles": len(processed),
            "last_processed_candle_id": last_processed,
            "last_closed_candle_id": last_processed,
            "event_origin": event_origin,
            "newer_event_precedence": "CAUSAL_TIME",
            "direction_authority": "E4_AUCTION_EVIDENCE_ONLY",
        },
    }


__all__ = ["analyze_e4", "ARCHITECTURE"]
