from __future__ import annotations

from math import isfinite
from typing import Any

from .professional_e4_brain_v18 import analyze_e4 as _base_analyze_e4

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V33"
CONFIRM_BARS = 2
MAX_CONFIRM_BARS = 5
INTERACTION_ATR = 0.05
MIN_DISPLACEMENT_ATR = 0.20
TERMINAL_STATES = ("CONFIRMED", "INVALIDATED", "EXPIRED")

# E4 owns only its own lifecycle state.  State is keyed by market and causal
# event id, not by the rolling-window array position.
_LIFECYCLE_STATE: dict[str, dict[str, Any]] = {}


def _num(value: Any):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def _bars(snapshot):
    raw = snapshot.get("bars", []) if isinstance(snapshot, dict) else snapshot
    result = []
    for bar in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(bar, dict):
            continue
        values = {k: _num(bar.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None for v in values.values()):
            continue
        if values["high"] < max(values["open"], values["close"]):
            continue
        if values["low"] > min(values["open"], values["close"]):
            continue
        if values["high"] < values["low"]:
            continue
        result.append({**values, "_raw": bar})
    return result


def _market_key(snapshot: Any) -> str:
    if not isinstance(snapshot, dict):
        return "UNKNOWN"
    for key in ("symbol", "instrument", "market", "ticker", "asset"):
        value = snapshot.get(key)
        if value:
            return str(value).upper()
    return "UNKNOWN"


def _bar_identity(bar: dict[str, Any], fallback_index: int) -> str:
    raw = bar.get("_raw") or {}
    for key in ("timestamp", "time", "datetime", "date", "candle", "open_time", "close_time"):
        value = raw.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return f"INDEX_FALLBACK:{fallback_index}"


def _event_class(event):
    kind = str(event.get("type") or "").upper()
    if "FAILED_BREAK" in kind or "SWEEP_REJECTION" in kind or "REJECTION" in kind:
        return "REJECTION"
    if "ACCEPTANCE" in kind:
        return "ACCEPTANCE"
    return "UNRESOLVED"


def _event_direction(event):
    return str(event.get("directional_implication") or "NEUTRAL").upper()


def _event_id(event: dict[str, Any], bars: list[dict[str, Any]]) -> str:
    index = int(event.get("index", -1))
    timestamp = _bar_identity(bars[index], index) if 0 <= index < len(bars) else str(event.get("timestamp") or "UNKNOWN")
    zone = event.get("zone") or {}
    side = str(zone.get("side") or "").upper()
    level = _num(event.get("level"))
    if level is None:
        level = _num(zone.get("upper" if side == "HIGH" else "lower"))
    return "|".join([
        timestamp,
        str(event.get("type") or "UNKNOWN"),
        side,
        str(round(level, 8)) if level is not None else "UNKNOWN",
        _event_direction(event),
    ])


def _find_event_index(event_id: str, event: dict[str, Any], bars: list[dict[str, Any]]) -> int:
    index = int(event.get("index", -1))
    if 0 <= index < len(bars) and _event_id(event, bars) == event_id:
        return index
    timestamp = event_id.split("|", 1)[0] if "|" in event_id else ""
    if timestamp and not timestamp.startswith("INDEX_FALLBACK:"):
        for i, bar in enumerate(bars):
            if _bar_identity(bar, i) == timestamp:
                return i
    return -1


def _event_level(event):
    level = _num(event.get("level"))
    if level is not None:
        return level
    zone = event.get("zone") or {}
    side = str(zone.get("side") or "").upper()
    return _num(zone.get("upper" if side == "HIGH" else "lower"))


def _empty_follow(reason="NO_POST_EVENT_CANDLE"):
    return {
        "present": False,
        "bars": 0,
        "available_bars": 0,
        "required_bars": CONFIRM_BARS,
        "horizon_bars": 0,
        "invalidated": False,
        "expired": False,
        "acceptance_quality": False,
        "rejection_quality": False,
        "reason": reason,
        "checks": [],
        "decisive_single": False,
        "consecutive": False,
        "confirmed_at": None,
        "invalidated_at": None,
        "terminal_lifecycle": "PENDING",
        "terminal": False,
    }


def _evaluate_new_candles(event: dict[str, Any], event_index: int, bars: list[dict[str, Any]], atr: float, prior: dict[str, Any] | None):
    """Deterministic E4 FSM; only unseen closed candles after the event are evaluated."""
    event_id = _event_id(event, bars)
    event_class = _event_class(event)
    direction = _event_direction(event)
    level = _event_level(event)

    if level is None or atr <= 0 or event_class == "UNRESOLVED" or direction not in {"UP", "DOWN"}:
        if prior and prior.get("lifecycle") in TERMINAL_STATES:
            return dict(prior.get("follow") or _empty_follow("TERMINAL_STATE_RETAINED")), str(prior["lifecycle"]), set(prior.get("processed_candles") or []), int(prior.get("consecutive", 0) or 0)
        return _empty_follow("INVALID_EVENT_METRICS" if level is None or atr <= 0 else "DIRECTIONAL_RESPONSE_NOT_ESTABLISHED"), "PENDING", set((prior or {}).get("processed_candles") or []), int((prior or {}).get("consecutive", 0) or 0)

    prior = prior or {}
    if prior.get("event_id") != event_id:
        prior = {}

    # First terminal transition wins forever for this exact causal event.
    if prior.get("lifecycle") in TERMINAL_STATES:
        return dict(prior.get("follow") or _empty_follow("TERMINAL_STATE_RETAINED")), str(prior["lifecycle"]), set(prior.get("processed_candles") or []), int(prior.get("consecutive", 0) or 0)

    processed = set(prior.get("processed_candles") or [])
    consecutive = int(prior.get("consecutive", 0) or 0)
    follow = dict(prior.get("follow") or _empty_follow())
    follow["checks"] = list(follow.get("checks") or [])

    for j in range(event_index + 1, len(bars)):
        candle_id = _bar_identity(bars[j], j)
        if candle_id in processed:
            continue
        processed.add(candle_id)

        close = bars[j]["close"]
        if direction == "UP":
            displacement = (close - level) / atr
            hold = close > level + atr * INTERACTION_ATR
            opposite = close < level - atr * INTERACTION_ATR
        else:
            displacement = (level - close) / atr
            hold = close < level - atr * INTERACTION_ATR
            opposite = close > level + atr * INTERACTION_ATR
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
            follow["checks"].append(check)
            follow.update({
                "invalidated": True,
                "terminal": True,
                "invalidated_at": candle_id,
                "bars": 0,
                "consecutive": 0,
                "reason": "POST_EVENT_RECLAMATION",
                "terminal_lifecycle": "INVALIDATED",
                "available_bars": len(processed),
                "horizon_bars": min(MAX_CONFIRM_BARS, len(processed)),
            })
            return follow, "INVALIDATED", processed, 0

        consecutive = consecutive + 1 if meaningful else 0
        check["consecutive"] = consecutive
        check["terminal"] = "CONFIRMED" if consecutive >= CONFIRM_BARS else None
        follow["checks"].append(check)

        if consecutive >= CONFIRM_BARS:
            follow.update({
                "present": True,
                "terminal": True,
                "bars": consecutive,
                "available_bars": len(processed),
                "horizon_bars": min(MAX_CONFIRM_BARS, len(processed)),
                "confirmed_at": candle_id,
                "consecutive": True,
                "reason": "FOLLOW_THROUGH_CONFIRMED",
                "terminal_lifecycle": "CONFIRMED",
                "acceptance_quality": event_class == "ACCEPTANCE",
                "rejection_quality": event_class == "REJECTION",
            })
            return follow, "CONFIRMED", processed, consecutive

    age = len(processed)
    follow["available_bars"] = age
    follow["horizon_bars"] = min(MAX_CONFIRM_BARS, age)
    follow["bars"] = consecutive
    follow["consecutive"] = consecutive > 0

    if age >= MAX_CONFIRM_BARS:
        follow.update({
            "expired": True,
            "terminal": True,
            "reason": "EVENT_EXPIRED",
            "terminal_lifecycle": "EXPIRED",
        })
        return follow, "EXPIRED", processed, consecutive

    follow["reason"] = "FOLLOW_THROUGH_ABSENT" if age else "NO_POST_EVENT_CANDLE"
    return follow, "PENDING", processed, consecutive


def _auction_state(event, lifecycle):
    if not event.get("zone"):
        return "UNRESOLVED", False
    event_class = _event_class(event)
    if lifecycle == "INVALIDATED":
        return "INVALIDATED", False
    if lifecycle == "EXPIRED":
        return "EXPIRED", False
    if lifecycle == "CONFIRMED":
        if event_class == "ACCEPTANCE":
            return "ACCEPTANCE_CONFIRMED", True
        if event_class == "REJECTION":
            return "REJECTION_CONFIRMED", True
        return "AUCTION_CONFIRMED", True
    if event_class == "ACCEPTANCE":
        return "ACCEPTANCE_PENDING", False
    if event_class == "REJECTION":
        return "REJECTION_PENDING", False
    return "INTERACTION_PENDING", False


def _get_atr(result):
    for item in result.get("observations") or []:
        if str(item).startswith("atr14="):
            return _num(str(item).split("=", 1)[1]) or 0.0
    return 0.0


def _transition(previous: str | None, current: str) -> str:
    return f"{previous or 'NONE'}->{current}"


def analyze_e4(snapshot=None, evidence_bus=None):
    """E4-only liquidity/auction analysis with persistent deterministic FSM."""
    result = dict(_base_analyze_e4(snapshot, evidence_bus))
    bars = _bars(snapshot)
    atr = _get_atr(result)
    detected_event = dict(result.get("event") or {})
    market = _market_key(snapshot)
    state = _LIFECYCLE_STATE.get(market)

    detected_id = _event_id(detected_event, bars) if detected_event.get("zone") else None

    # A newly detected causal event supersedes an older lifecycle.  Otherwise
    # the stored event remains authoritative and is advanced only by unseen
    # closed candles.  No future candle is synthesized.
    if detected_event.get("zone") and detected_id:
        if state is None or detected_id != state.get("event_id"):
            event = detected_event
            event_id = detected_id
            event_index = _find_event_index(event_id, event, bars)
            prior = None
        else:
            event = dict(state.get("event") or detected_event)
            event_id = state["event_id"]
            event_index = _find_event_index(event_id, event, bars)
            prior = state
    elif state and state.get("event_id"):
        event = dict(state.get("event") or {})
        event_id = state["event_id"]
        event_index = _find_event_index(event_id, event, bars)
        prior = state
    else:
        event = detected_event
        event_id = None
        event_index = -1
        prior = None

    previous_lifecycle = str(prior.get("lifecycle")) if prior else None

    if event_id and event_index >= 0:
        follow, lifecycle, processed, consecutive = _evaluate_new_candles(event, event_index, bars, atr, prior)
        previous_event_state = state if state and state.get("event_id") == event_id else None
        previous_terminal = previous_event_state and previous_event_state.get("lifecycle") in TERMINAL_STATES
        if previous_terminal:
            lifecycle = str(previous_event_state["lifecycle"])
            follow = dict(previous_event_state.get("follow") or follow)
            processed = set(previous_event_state.get("processed_candles") or processed)
            consecutive = int(previous_event_state.get("consecutive", consecutive) or 0)
        _LIFECYCLE_STATE[market] = {
            "event_id": event_id,
            "event": dict(event),
            "lifecycle": lifecycle,
            "processed_candles": set(processed),
            "consecutive": consecutive,
            "follow": dict(follow),
            "last_processed_candle_id": _bar_identity(bars[-1], len(bars) - 1) if bars else None,
            "event_age_bars": max(0, len(bars) - 1 - event_index),
        }
        prior_for_transition = previous_event_state
    elif event_id and prior and prior.get("lifecycle") in TERMINAL_STATES:
        follow = dict(prior.get("follow") or _empty_follow("TERMINAL_STATE_RETAINED"))
        lifecycle = str(prior["lifecycle"])
        processed = set(prior.get("processed_candles") or [])
        consecutive = int(prior.get("consecutive", 0) or 0)
        prior_for_transition = prior
    else:
        follow = _empty_follow("NO_LIQUIDITY_EVENT")
        lifecycle = "PENDING"
        processed = set()
        consecutive = 0
        prior_for_transition = prior

    state_name, confirmed = _auction_state(event, lifecycle)
    direction = _event_direction(event) if confirmed else "NEUTRAL"
    event_age = 0
    if event_index >= 0:
        event_age = max(0, len(bars) - 1 - event_index)
    elif prior:
        event_age = int(prior.get("event_age_bars", 0) or 0)

    event_class = _event_class(event)
    terminal_reason = follow.get("reason") if lifecycle in TERMINAL_STATES else None
    transition = _transition(str(prior_for_transition.get("lifecycle")) if prior_for_transition else None, lifecycle)

    result["architecture"] = ARCHITECTURE
    result["professional_brain"] = True
    result["role"] = E4_ROLE
    result["question"] = PROFESSIONAL_QUESTION
    result["decision"] = None
    result["gate"] = None
    result["score"] = None
    result["trade_decision_authority"] = False
    result["decision_authority"] = "E9_ONLY"
    result["reasoning_role"] = E4_ROLE
    result["upstream_decisions_used"] = False
    result["upstream_gates_used"] = False
    result["scores_used"] = False
    result["score_used"] = False

    result["auction"] = {
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
        "last_processed_candle_id": _LIFECYCLE_STATE.get(market, {}).get("last_processed_candle_id"),
        "detail": follow,
    }
    result["auction_state"] = state_name
    result["auction_confirmation"] = {"confirmed": confirmed, "state": state_name}
    result["auction_confirmation_state"] = state_name
    result["follow_through"] = follow
    result["follow_through_bars"] = follow.get("bars", 0)
    result["event_id"] = event_id
    result["event_age_bars"] = event_age
    result["lifecycle"] = lifecycle
    result["lifecycle_transition"] = transition
    result["terminal_state"] = lifecycle if lifecycle in TERMINAL_STATES else None
    result["terminal_reason"] = terminal_reason
    result["direction"] = direction
    result["directional_implication"] = direction
    result["direction_confirmed"] = confirmed

    if not event.get("zone"):
        finding = "NO_LIQUIDITY_EVENT"
        reasons = ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]
    elif lifecycle == "INVALIDATED":
        finding = str(event.get("type", "LIQUIDITY_EVENT")) + "_INVALIDATED"
        reasons = ["AUCTION_THESIS_INVALIDATED", "POST_EVENT_RECLAMATION"]
    elif lifecycle == "EXPIRED":
        finding = str(event.get("type", "LIQUIDITY_EVENT")) + "_EXPIRED"
        reasons = ["AUCTION_THESIS_EXPIRED", "NO_SUFFICIENT_FOLLOW_THROUGH"]
    elif lifecycle == "CONFIRMED":
        finding = str(event.get("type", "LIQUIDITY_EVENT")) + "_CONFIRMED"
        reasons = []
    else:
        finding = str(event.get("type", "LIQUIDITY_EVENT"))
        reasons = ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]

    result["finding"] = finding
    result["analyst_conclusion"] = finding
    result["auction_quality"] = "CONFIRMED" if confirmed else lifecycle
    result["reasons"] = reasons
    result["counter_evidence"] = [
        "POST_EVENT_RECLAMATION" if lifecycle == "INVALIDATED" else "NO_FOLLOW_THROUGH",
        "AUCTION_DIRECTION_REMAINS_UNRESOLVED" if not confirmed else "OPPOSITE_LIQUIDITY_EVENT_CHALLENGES_THESIS",
    ]
    result["invalidation"] = [
        "post-event close through defended liquidity level invalidates thesis before confirmation",
        "event expiry without sufficient follow-through prevents confirmation",
        "a newer causal event starts a new independent E4 lifecycle",
    ]

    reasoning = result.get("professional_reasoning")
    if isinstance(reasoning, dict):
        reasoning["response"] = {"status": lifecycle, "direction": direction, "actor": event.get("response_actor", "NONE")}
        reasoning["follow_through"] = {"confirmed": confirmed, "bars": follow.get("bars", 0), "required_bars": CONFIRM_BARS, "reason": follow.get("reason")}
        reasoning["thesis_status"] = lifecycle
        reasoning["actor_identification"] = "INFERENCE_FROM_OHLC_ONLY"
        reasoning["lifecycle_rule"] = "PENDING -> exactly one terminal state: CONFIRMED|INVALIDATED|EXPIRED; first terminal wins"
    else:
        result["professional_reasoning"] = {
            "question": PROFESSIONAL_QUESTION,
            "thesis_status": lifecycle,
            "actor_identification": "INFERENCE_FROM_OHLC_ONLY",
            "lifecycle_rule": "PENDING -> exactly one terminal state: CONFIRMED|INVALIDATED|EXPIRED; first terminal wins",
        }

    audit = dict(result.get("audit") or {})
    audit.update({
        "closed_candle_only": True,
        "no_lookahead": True,
        "actor_identification": "PRICE_ACTION_INFERENCE_ONLY",
        "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW",
        "auction_state": state_name,
        "auction_event_class": event_class,
        "event_id": event_id,
        "event_age_bars": event_age,
        "lifecycle": lifecycle,
        "lifecycle_transition": transition,
        "follow_through_bars": follow.get("bars", 0),
        "available_post_event_bars": follow.get("available_bars", 0),
        "required_confirmation_bars": CONFIRM_BARS,
        "confirmation_horizon": min(MAX_CONFIRM_BARS, event_age),
        "terminal_states": list(TERMINAL_STATES),
        "terminal_state_immutable": True,
        "first_terminal_wins": True,
        "persistent_state": True,
        "state_key": market,
        "processed_candles": len(processed),
        "last_processed_candle_id": _LIFECYCLE_STATE.get(market, {}).get("last_processed_candle_id"),
        "newer_event_precedence": "CAUSAL_TIME",
        "direction_authority": "E4_AUCTION_EVIDENCE_ONLY",
    })
    result["audit"] = audit

    return result


__all__ = ["analyze_e4", "ARCHITECTURE"]
