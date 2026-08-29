from __future__ import annotations

from math import isfinite
from typing import Any

from .professional_e4_brain_v18 import analyze_e4 as _base_analyze_e4

PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
E4_ROLE = "LIQUIDITY_AUCTION_ANALYST"
ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_LIQUIDITY_AUCTION_BRAIN_V30"
CONFIRM_BARS = 2
MAX_CONFIRM_BARS = 5
INTERACTION_ATR = 0.05
MIN_DISPLACEMENT_ATR = 0.20


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


def _deterministic_follow_through(event, bars, atr):
    """Closed-candle-only state machine: PENDING -> exactly one terminal state."""
    empty = {
        "present": False, "bars": 0, "available_bars": 0,
        "required_bars": CONFIRM_BARS, "horizon_bars": 0,
        "invalidated": False, "expired": False,
        "acceptance_quality": False, "rejection_quality": False,
        "reason": "NO_POST_EVENT_CANDLE", "checks": [],
        "decisive_single": False, "consecutive": False,
        "confirmed_at": None, "invalidated_at": None,
        "terminal_lifecycle": "PENDING",
    }
    if not isinstance(event, dict) or not event.get("zone"):
        return empty

    index = int(event.get("index", -1))
    if index < 0 or index >= len(bars) - 1:
        return empty

    level = _num(event.get("level"))
    direction = str(event.get("directional_implication") or "NEUTRAL").upper()
    event_atr = _num(event.get("atr_at_event")) or atr
    if level is None or event_atr is None or event_atr <= 0:
        out = dict(empty)
        out.update({"reason": "INVALID_EVENT_METRICS", "terminal_lifecycle": "PENDING"})
        return out

    horizon = min(MAX_CONFIRM_BARS, len(bars) - 1 - index)
    out = dict(empty)
    out["available_bars"] = horizon
    out["horizon_bars"] = horizon

    if direction not in {"UP", "DOWN"}:
        if horizon >= MAX_CONFIRM_BARS:
            out.update({"expired": True, "reason": "EVENT_EXPIRED", "terminal_lifecycle": "EXPIRED"})
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
                "index": j, "close": close, "hold": hold,
                "displacement_atr": displacement, "meaningful": meaningful,
                "opposite_reclaim": True, "consecutive": 0,
                "terminal": "INVALIDATION",
            })
            out.update({
                "invalidated": True, "invalidated_at": j,
                "bars": 0, "consecutive": False,
                "reason": "POST_EVENT_RECLAMATION",
                "terminal_lifecycle": "INVALIDATED",
            })
            return out

        consecutive = consecutive + 1 if meaningful else 0
        out["checks"].append({
            "index": j, "close": close, "hold": hold,
            "displacement_atr": displacement, "meaningful": meaningful,
            "opposite_reclaim": False, "consecutive": consecutive,
            "terminal": "CONFIRMATION" if consecutive >= CONFIRM_BARS else None,
        })

        # Terminal state is immutable: once confirmed, later candles cannot
        # rewrite this event into INVALIDATED. A newer event may supersede it.
        if consecutive >= CONFIRM_BARS:
            out.update({
                "present": True, "bars": consecutive,
                "confirmed_at": j, "consecutive": True,
                "reason": "FOLLOW_THROUGH_CONFIRMED",
                "terminal_lifecycle": "CONFIRMED",
            })
            out["acceptance_quality"] = event.get("auction_state") == "ACCEPTANCE"
            out["rejection_quality"] = event.get("auction_state") == "REJECTION"
            return out

    if horizon >= MAX_CONFIRM_BARS:
        out.update({"expired": True, "reason": "EVENT_EXPIRED", "terminal_lifecycle": "EXPIRED"})
    else:
        out["reason"] = "FOLLOW_THROUGH_ABSENT"
    return out


def _auction_state(event, follow):
    if not event.get("zone"):
        return "UNRESOLVED", False, "NO_EVENT"

    lifecycle = follow.get("terminal_lifecycle", "PENDING")
    base = str(event.get("auction_state") or "UNRESOLVED").upper()

    if lifecycle == "INVALIDATED":
        return "INVALIDATED", False, "INVALIDATED"
    if lifecycle == "CONFIRMED":
        if base == "ACCEPTANCE":
            return "ACCEPTANCE_CONFIRMED", True, "CONFIRMED"
        if base == "REJECTION":
            return "REJECTION_CONFIRMED", True, "CONFIRMED"
        return "AUCTION_CONFIRMED", True, "CONFIRMED"
    if lifecycle == "EXPIRED":
        return "EXPIRED", False, "EXPIRED"
    if base == "ACCEPTANCE":
        return "ACCEPTANCE_PENDING", False, "PENDING"
    if base == "REJECTION":
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

    result["auction"] = {
        "state": state,
        "confirmed": confirmed,
        "follow_through_bars": follow.get("bars", 0),
        "lifecycle": lifecycle,
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
    result["auction_quality"] = "CONFIRMED" if confirmed else "INVALIDATED" if state == "INVALIDATED" else "EXPIRED" if state == "EXPIRED" else "PENDING"
    result["reasons"] = reasons
    result["counter_evidence"] = [
        "POST_EVENT_RECLAMATION" if state == "INVALIDATED" else "NO_FOLLOW_THROUGH",
        "AUCTION_DIRECTION_REMAINS_UNRESOLVED" if not confirmed else "OPPOSITE_LIQUIDITY_EVENT_CHALLENGES_THESIS",
    ]
    result["invalidation"] = [
        "newer causal liquidity event supersedes current event",
        "post-event close through defended liquidity level invalidates thesis before confirmation",
        "event expiry without sufficient follow-through invalidates confirmation",
    ]

    reasoning = result.get("professional_reasoning")
    if isinstance(reasoning, dict):
        reasoning["response"] = {"status": "CONFIRMED" if confirmed else lifecycle,
                                  "direction": direction,
                                  "actor": event.get("response_actor", "NONE")}
        reasoning["follow_through"] = {
            "confirmed": follow.get("present", False),
            "bars": follow.get("bars", 0),
            "required_bars": CONFIRM_BARS,
            "reason": follow.get("reason"),
        }
        reasoning["thesis_status"] = "CONFIRMED" if confirmed else "INVALIDATED" if state == "INVALIDATED" else "EXPIRED" if state == "EXPIRED" else "UNRESOLVED"
        reasoning["actor_identification"] = "INFERENCE_FROM_OHLC_ONLY"
        reasoning["lifecycle_rule"] = "PENDING -> exactly one of CONFIRMED|INVALIDATED|EXPIRED"
    else:
        result["professional_reasoning"] = {
            "question": PROFESSIONAL_QUESTION,
            "thesis_status": "CONFIRMED" if confirmed else "INVALIDATED" if state == "INVALIDATED" else "EXPIRED" if state == "EXPIRED" else "UNRESOLVED",
            "actor_identification": "INFERENCE_FROM_OHLC_ONLY",
            "lifecycle_rule": "PENDING -> exactly one of CONFIRMED|INVALIDATED|EXPIRED",
        }

    audit = dict(result.get("audit") or {})
    audit.update({
        "closed_candle_only": True,
        "no_lookahead": True,
        "actor_identification": "PRICE_ACTION_INFERENCE_ONLY",
        "actor_identification_limit": "OHLC_CANNOT_IDENTIFY_ACTUAL_PARTICIPANTS_OR_ORDER_FLOW",
        "auction_state": state,
        "follow_through_bars": follow.get("bars", 0),
        "required_confirmation_bars": CONFIRM_BARS,
        "confirmation_horizon": follow.get("horizon_bars", 0),
        "sweep_confirmation_allowed": False,
        "direction_authority": "E4_AUCTION_EVIDENCE_ONLY",
        "terminal_states": ["CONFIRMED", "INVALIDATED", "EXPIRED"],
        "terminal_state_immutable": True,
        "newer_event_precedence": "CAUSAL_TIME",
    })
    result["audit"] = audit

    return result


__all__ = ["analyze_e4", "ARCHITECTURE"]
