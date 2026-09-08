from __future__ import annotations

from functools import wraps
from typing import Any

ACTIVE = {"WATCHING", "WAITING", "READY"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH"}
CONCRETE_EXCLUDED = {"", "UNKNOWN", "NONE", "NO_SETUP", *WATCH_SETUPS}
THESIS_STATES = {"FORMING", "VALIDATING", "THESIS_FORMED", "PROVEN"}


def _event(previous: dict[str, Any], current: dict[str, Any]) -> tuple[str, str]:
    p = str(previous.get("event_id") or previous.get("event_timestamp") or previous.get("event_candle") or "").strip()
    c = str(current.get("event_id") or current.get("event_timestamp") or current.get("event_candle") or "").strip()
    return p, c


def _new_causal_event(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    p, c = _event(previous, current)
    return bool(p and c and p.casefold() != c.casefold())


def _same_closed_candle(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    p = str(previous.get("last_evaluated_candle") or "").strip()
    c = str(current.get("candle") or current.get("event_candle") or "").strip()
    return bool(p and c and p == c)


def _as_new_watch(result: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return {
        **result,
        "state": "WATCHING",
        "lifecycle_state": "OPPORTUNITY_WATCH",
        "opportunity_phase": "OPPORTUNITY_WATCH",
        "setup": current.get("setup") or current.get("setup_family") or result.get("setup") or "OPPORTUNITY_WATCH",
        "direction": current.get("direction") or result.get("direction"),
        "candidate": bool(current.get("candidate", result.get("candidate", True))),
        "trade_authorized": False,
        "ready": False,
        "continuity": "NEW_CAUSAL_EVENT_REPLACED_ACTIVE_OPPORTUNITY",
        "event_id": current.get("event_id", result.get("event_id")),
        "event_timestamp": current.get("event_timestamp", result.get("event_timestamp")),
        "event_candle": current.get("event_candle", result.get("event_candle")),
        "bars_waited": 0,
        "age_bars": 0,
        "age_minutes": 0,
    }


def _as_invalidated(result: dict[str, Any], previous: dict[str, Any], current: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **result,
        "state": "INVALIDATED",
        "lifecycle_state": "INVALIDATED",
        "opportunity_phase": "INVALIDATED",
        "opportunity_id": previous.get("opportunity_id") or result.get("opportunity_id"),
        "direction": previous.get("direction") or current.get("direction") or result.get("direction"),
        "setup": previous.get("setup") or current.get("setup") or current.get("setup_family") or result.get("setup") or "OPPORTUNITY_WATCH",
        "continuity": "OPPORTUNITY_INVALIDATED",
        "trade_authorized": False,
        "ready": False,
        "invalidation_reason": reason,
    }


def install(module: Any) -> None:
    if getattr(module, "_PROFESSIONAL_LIFECYCLE_CONTRACT_V3", False):
        return
    original = module.advance_opportunity
    original_directions = module.advance_opportunity_directions

    @wraps(original)
    def advance_opportunity(previous, current):
        previous = dict(previous or {})
        current = dict(current or {})
        result = dict(original(previous, current) or {})

        for key in (
            "opportunity_phase", "opportunity_speed", "confirmation_window",
            "wait_for", "chase_prohibited", "thesis_status", "upstream_evidence",
            "event_id", "event_timestamp", "event_candle", "age_bars", "age_minutes",
        ):
            if key in current and key not in result:
                result[key] = current[key]

        ps = str(previous.get("setup") or "").upper()
        cs = str(current.get("setup") or current.get("setup_family") or "").upper()
        ts = str(current.get("thesis_status") or "").upper()
        thesis_proven = bool(current.get("thesis_proven")) or ts in {"VALIDATING", "THESIS_FORMED", "PROVEN"}
        previous_state = str(previous.get("state") or "").upper()
        pd = str(previous.get("direction") or "").upper()
        cd = str(current.get("direction") or "").upper()
        fresh_event = _new_causal_event(previous, current)
        same_candle = _same_closed_candle(previous, current)

        # Terminal evidence loss must win over every active-state preservation
        # rule. Otherwise the later WATCHING branch can resurrect an invalid
        # opportunity on the same closed candle.
        if current.get("invalidated"):
            if previous_state in ACTIVE:
                return _as_invalidated(result, previous, current, current.get("invalidation_reason") or "CURRENT_CANDLE_INVALIDATED")
            return result
        if current.get("upstream_evidence_lost") or current.get("causal_evidence_lost"):
            if previous_state in ACTIVE and ps in WATCH_SETUPS:
                return _as_invalidated(result, previous, current, "UPSTREAM_CAUSAL_EVIDENCE_LOST")
            return result

        if previous_state in ACTIVE and pd == cd and fresh_event:
            return _as_new_watch(result, current)

        # Expiry is evaluated before preserving WATCHING. A new closed candle
        # that reaches the maximum watch age terminates the watch; evaluating
        # the same candle twice remains idempotent.
        if previous_state == "WATCHING" and pd == cd and not same_candle and not thesis_proven:
            try:
                max_watch_bars = int(getattr(module, "MAX_WATCH_BARS", 5))
                waited = int(result.get("bars_waited", previous.get("bars_waited", 0)) or 0)
            except (TypeError, ValueError):
                max_watch_bars, waited = 5, 0
            if waited >= max_watch_bars:
                return {
                    **result,
                    "state": "EXPIRED",
                    "lifecycle_state": "EXPIRED",
                    "opportunity_phase": "EXPIRED",
                    "opportunity_id": previous.get("opportunity_id") or result.get("opportunity_id"),
                    "direction": pd or cd or result.get("direction"),
                    "setup": previous.get("setup") or cs or "OPPORTUNITY_WATCH",
                    "continuity": "OPPORTUNITY_EXPIRED",
                    "bars_waited": waited,
                    "trade_authorized": False,
                    "ready": False,
                    "invalidation_reason": "WATCH_MAX_AGE_REACHED",
                    "wait_for": "NEW_CAUSAL_OPPORTUNITY",
                }

        # WATCHING is a causal-discovery state. A concrete setup label alone
        # does not prove the thesis. Explicit validation/proof is the promotion
        # gate; FORMING remains WATCHING.
        if previous_state == "WATCHING" and pd == cd and not thesis_proven:
            if same_candle or cs in WATCH_SETUPS:
                continuity = "CONTINUING_UPSTREAM_WATCH"
            else:
                continuity = "PRESERVING_PENDING_OPPORTUNITY"
            return {
                **result,
                "state": "WATCHING",
                "lifecycle_state": "OPPORTUNITY_WATCH",
                "opportunity_phase": "OPPORTUNITY_WATCH",
                "opportunity_id": previous.get("opportunity_id") or result.get("opportunity_id"),
                "direction": pd or cd or result.get("direction"),
                "setup": previous.get("setup") or "OPPORTUNITY_WATCH",
                "candidate": bool(current.get("candidate", result.get("candidate", True))),
                "trade_authorized": False,
                "ready": False,
                "continuity": continuity,
                "bars_waited": result.get("bars_waited", previous.get("bars_waited", 0)),
                "age_bars": result.get("age_bars", previous.get("age_bars", 0)),
            }

        if (
            previous_state in ACTIVE
            and ps in WATCH_SETUPS
            and cs not in CONCRETE_EXCLUDED
            and thesis_proven
            and not current.get("ready")
        ):
            return {
                **result,
                "state": "WAITING",
                "lifecycle_state": "TRIGGER_PENDING",
                "opportunity_phase": "TRIGGER_PENDING",
                "setup": cs,
                "direction": current.get("direction"),
                "candidate": True,
                "trade_authorized": False,
                "ready": False,
                "continuity": "PROMOTED_PENDING_OPPORTUNITY",
            }
        return result

    @wraps(original_directions)
    def advance_opportunity_directions(
        previous, current_by_direction, *, leader="NEUTRAL", competition="UNCONTESTED"
    ):
        result = original_directions(
            previous, current_by_direction, leader=leader, competition=competition
        )
        book = result.get("opportunities", {})
        for direction in ("BUY", "SELL"):
            item = book.get(direction)
            current = current_by_direction.get(direction) or {}
            if isinstance(item, dict) and item.get("state") == "REPLACED" and current.get("candidate"):
                book[direction] = _as_new_watch(item, current)
        if leader in {"BUY", "SELL"} and isinstance(book.get(leader), dict):
            result["leader"] = leader
        result["active_directions"] = [
            d for d in ("BUY", "SELL")
            if isinstance(book.get(d), dict) and book[d].get("state") in ACTIVE
        ]
        return result

    module.advance_opportunity = advance_opportunity
    module.advance_opportunity_directions = advance_opportunity_directions
    module._PROFESSIONAL_LIFECYCLE_CONTRACT_V3 = True
