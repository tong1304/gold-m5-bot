from __future__ import annotations

from math import isfinite
from typing import Any

from .professional_e4_brain_v18 import analyze_e4 as _base_analyze_e4

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V31"
CONFIRM_BARS = 2
MAX_CONFIRM_BARS = 5
INTERACTION_ATR = 0.05
MIN_DISPLACEMENT_ATR = 0.20
TERMINAL_STATES = ("CONFIRMED", "INVALIDATED", "EXPIRED")


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
        if bar.get("closed") is False or bar.get("is_closed") is False:
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
        result.append(values)
    return result


def _atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    tr = []
    for i in range(1, len(bars)):
        h, low, prev_close = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        tr.append(max(h - low, abs(h - prev_close), abs(low - prev_close)))
    return sum(tr[-period:]) / min(period, len(tr)) if tr else 0.0


def _event_class(event):
    """Normalize base event names to the only auction classes E4 may confirm."""
    kind = str(event.get("type") or "").upper()
    if "FAILED_BREAK" in kind or "SWEEP_REJECTION" in kind or "REJECTION" in kind:
        return "REJECTION"
    if "ACCEPTANCE" in kind:
        return "ACCEPTANCE"
    return "UNRESOLVED"


def _deterministic_follow_through(event, bars, atr):
    """Closed-candle-only finite state machine: PENDING -> one terminal state."""
    empty = {
        "present": False,
        "bars": 0,
        "available_bars": 0,
        "required_bars": CONFIRM_BARS,
        "horizon_bars": 0,
        "invalidated": False,
        "expired": False,
        "acceptance_quality": False,
        "rejection_quality": False,
        "reason": "NO_POST_EVENT_CANDLE",
        "checks": [],
        "decisive_single": False,
        "consecutive": False,
        "confirmed_at": None,
        "invalidated_at": None,
        "terminal_lifecycle": "PENDING",
        "terminal": False,
    }
    if not isinstance(event, dict) or not event.get("zone"):
        return empty

    index = int(event.get("index", -1))
    if index < 0 or index >= len(bars):
        out = dict(empty)
        out["reason"] = "INVALID_EVENT_INDEX"
        return out

    level = _num(event.get("level"))
    if level is None:
        zone = event.get("zone") or {}
        side = str(zone.get("side") or "").upper()
        level = _num(zone.get("upper" if side == "HIGH" else "lower"))

    event_atr = _num(event.get("atr_at_event")) or atr
    if level is None or event_atr is None or event_atr <= 0:
        out = dict(empty)
        out["reason"] = "INVALID_EVENT_METRICS"
        return out

    horizon = min(MAX_CONFIRM_BARS, max(0, len(bars) - 1 - index))
    out = dict(empty)
    out["available_bars"] = horizon
    out["horizon_bars"] = horizon

    event_class = _event_class(event)
    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    if event_class == "UNRESOLVED" or direction not in {"UP", "DOWN"}:
        if horizon >= MAX_CONFIRM_BARS:
            out.update({
                "expired": True,
                "terminal": True,
                "reason": "EVENT_EXPIRED",
                "terminal_lifecycle": "EXPIRED",
            })
        else:
            out["reason"] = "DIRECTIONAL_RESPONSE_NOT_ESTABLISHED"
        return out

    consecutive = 0
    for j in range(index + 1, index + horizon + 1):
        close = bars[j]["close"]
        if direction == "UP":
            displacement = (close - level) / event_atr
            hold = close > level + event_atr * INTERACTION_ATR
            opposite = close < level - event_atr * INTERACTION_ATR
        else:
            displacement = (level - close) / event_atr
            hold = close < level - event_atr * INTERACTION_ATR
            opposite = close > level + event_atr * INTERACTION_ATR

        meaningful = hold and displacement >= MIN_DISPLACEMENT_ATR

        if opposite:
            out["checks"].append({
                "index": j,
                "close": close,
                "hold": hold,
                "displacement_atr": displacement,
                "meaningful": meaningful,
                "opposite_reclaim": True,
                "consecutive": 0,
                "terminal": "INVALIDATED",
            })
            out.update({
                "invalidated": True,
                "terminal": True,
                "invalidated_at": j,
                "bars": 0,
                "consecutive": False,
                "reason": "POST_EVENT_RECLAMATION",
                "terminal_lifecycle": "INVALIDATED",
            })
            return out

        consecutive = consecutive + 1 if meaningful else 0
        out["checks"].append({
            "index": j,
            "close": close,
            "hold": hold,
            "displacement_atr": displacement,
            "meaningful": meaningful,
            "opposite_reclaim": False,
            "consecutive": consecutive,
            "terminal": "CONFIRMED" if consecutive >= CONFIRM_BARS else None,
        })

        # First terminal event wins. Once CONFIRMED, later candles cannot
        # rewrite this event into INVALIDATED. A newer causal event is separate.
        if consecutive >= CONFIRM_BARS:
            out.update({
                "present": True,
                "terminal": True,
                "bars": consecutive,
                "confirmed_at": j,
                "consecutive": True,
                "reason": "FOLLOW_THROUGH_CONFIRMED",
                "terminal_lifecycle": "CONFIRMED",
                "acceptance_quality": event_class == "ACCEPTANCE",
                "rejection_quality": event_class == "REJECTION",
            })
            return out

    if horizon >= MAX_CONFIRM_BARS:
        out.update({
            "expired": True,
            "terminal": True,
            "reason": "EVENT_EXPIRED",
            "terminal_lifecycle": "EXPIRED",
        })
    else:
        out["reason"] = "FOLLOW_THROUGH_ABSENT"
    return out


def _auction_state(event, follow):
    if not event.get("zone"):
        return "UNRESOLVED", False, "PENDING"

    lifecycle = str(follow.get("terminal_lifecycle") or "PENDING").upper()
    event_class = _event_class(event)

    if lifecycle == "INVALIDATED":
        return "INVALIDATED", False, "INVALIDATED"
    if lifecycle == "EXPIRED":
        return "EXPIRED", False, "EXPIRED"
    if lifecycle == "CONFIRMED":
        if event_class == "ACCEPTANCE":
            return "ACCEPTANCE_CONFIRMED", True, "CONFIRMED"
        if event_class == "REJECTION":
            return "REJECTION_CONFIRMED", True, "CONFIRMED"
        return "AUCTION_CONFIRMED", True, "CONFIRMED"

    if event_class == "ACCEPTANCE":
        return "ACCEPTANCE_PENDING", False, "PENDING"
    if event_class == "REJECTION":
        return "REJECTION_PENDING", False, "PENDING"
    return "INTERACTION_PENDING", False, "PENDING"


def analyze_e4(snapshot=None, evidence_bus=None):
    """E4-only liquidity/auction analysis with deterministic lifecycle semantics."""
    result = dict(_base_analyze_e4(snapshot, evidence_bus))
    bars = _bars(snapshot)
    atr = _atr(bars)
    event = dict(result.get("event") or {})

    follow = _deterministic_follow_through(event, bars, atr)
    state, confirmed, lifecycle = _auction_state(event, follow)
    direction = event.get("directional_implication", "NEUTRAL") if confirmed else "NEUTRAL"

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

    event_class = _event_class(event)
    result["auction"] = {
        "state": state,
        "confirmed": confirmed,
        "follow_through_bars": follow.get("bars", 0),
        "lifecycle": lifecycle,
        "event_class": event_class,
        "detail": follow,
    }
    result["auction_state"] = state
    result["auction_confirmation"] = {"confirmed": confirmed, "state": state}
    result["auction_confirmation_state"] = state
    result["follow_through"] = follow
    result["follow_through_bars"] = follow.get("bars", 0)
    result["direction"] = direction
    result["directional_implication"] = direction
    result["direction_confirmed"] = confirmed

    if not event.get("zone"):
        finding = "NO_LIQUIDITY_EVENT"
        reasons = ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]
    elif state == "INVALIDATED":
        finding = event.get("type", "LIQUIDITY_EVENT") + "_INVALIDATED"
        reasons = ["AUCTION_THESIS_INVALIDATED", "POST_EVENT_RECLAMATION"]
    elif state == "EXPIRED":
        finding = event.get("type", "LIQUIDITY_EVENT") + "_EXPIRED"
        reasons = ["AUCTION_THESIS_EXPIRED", "NO_SUFFICIENT_FOLLOW_THROUGH"]
    elif confirmed:
        finding = event.get("type", "LIQUIDITY_EVENT") + "_CONFIRMED"
        reasons = []
    else:
        finding = event.get("type", "LIQUIDITY_EVENT")
        reasons = ["TRUE_AUCTION_CONFIRMATION_NOT_PROVEN"]

    result["finding"] = finding
    result["analyst_conclusion"] = finding
    result["auction_quality"] = (
        "CONFIRMED" if confirmed
        else "INVALIDATED" if state == "INVALIDATED"
        else "EXPIRED" if state == "EXPIRED"
        else "PENDING"
    )
    result["reasons"] = reasons
    result["counter_evidence"] = [
        "POST_EVENT_RECLAMATION" if state == "INVALIDATED" else "NO_FOLLOW_THROUGH",
        "AUCTION_DIRECTION_REMAINS_UNRESOLVED" if not confirmed else "OPPOSITE_LIQUIDITY_EVENT_CHALLENGES_THESIS",
    ]
    result["invalidation"] = [
        "newer causal liquidity event supersedes current event",
        "post-event close through defended liquidity level invalidates thesis before confirmation",
        "event expiry without sufficient follow-through prevents confirmation",
    ]

    reasoning = result.get("professional_reasoning")
    thesis_status = (
        "CONFIRMED" if confirmed
        else "INVALIDATED" if state == "INVALIDATED"
        else "EXPIRED" if state == "EXPIRED"
        else "UNRESOLVED"
    )
    if isinstance(reasoning, dict):
        reasoning["response"] = {
            "status": "CONFIRMED" if confirmed else lifecycle,
            "direction": direction,
            "actor": event.get("response_actor", "NONE"),
        }
        reasoning["follow_through"] = {
            "confirmed": follow.get("present", False),
            "bars": follow.get("bars", 0),
            "required_bars": CONFIRM_BARS,
            "reason": follow.get("reason"),
        }
        reasoning["thesis_status"] = thesis_status
        reasoning["actor_identification"] = "INFERENCE_FROM_OHLC_ONLY"
        reasoning["lifecycle_rule"] = "PENDING -> exactly one terminal state: CONFIRMED|INVALIDATED|EXPIRED"
    else:
        result["professional_reasoning"] = {
            "question": PROFESSIONAL_QUESTION,
            "thesis_status": thesis_status,
            "actor_identification": "INFERENCE_FROM_OHLC_ONLY",
            "lifecycle_rule": "PENDING -> exactly one terminal state: CONFIRMED|INVALIDATED|EXPIRED",
        }

    audit = dict(result.get("audit") or {})
    audit.update({
        "closed_candle_only": True,
        "no_lookahead": True,
        "actor_identification": "PRICE_ACTION_INFERENCE_ONLY",
        "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW",
        "auction_state": state,
        "auction_event_class": event_class,
        "follow_through_bars": follow.get("bars", 0),
        "required_confirmation_bars": CONFIRM_BARS,
        "confirmation_horizon": follow.get("horizon_bars", 0),
        "sweep_confirmation_allowed": False,
        "direction_authority": "E4_AUCTION_EVIDENCE_ONLY",
        "terminal_states": list(TERMINAL_STATES),
        "terminal_state_immutable": True,
        "first_terminal_wins": True,
        "newer_event_precedence": "CAUSAL_TIME",
    })
    result["audit"] = audit

    return result


__all__ = ["analyze_e4", "ARCHITECTURE"]
