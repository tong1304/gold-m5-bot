from __future__ import annotations

from functools import wraps
from typing import Any

ACTIVE = {"WATCHING", "WAITING", "READY"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH"}
CONCRETE_EXCLUDED = {"", "UNKNOWN", "NONE", "NO_SETUP", *WATCH_SETUPS}
THESIS_STATES = {"FORMING", "VALIDATING", "THESIS_FORMED", "PROVEN"}


def _new_causal_event(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    """A fresh causal event supersedes the old watch identity."""
    previous_event = previous.get("event_id") or previous.get("event_timestamp") or previous.get("event_candle")
    current_event = current.get("event_id") or current.get("event_timestamp") or current.get("event_candle")
    return bool(previous_event and current_event and previous_event != current_event)


def _as_new_watch(result: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    return {
        **result,
        "state": "WATCHING",
        "lifecycle_state": "OPPORTUNITY_WATCH",
        "opportunity_phase": "OPPORTUNITY_WATCH",
        "setup": current.get("setup") or current.get("setup_family") or result.get("setup"),
        "direction": current.get("direction") or result.get("direction"),
        "candidate": bool(current.get("candidate", result.get("candidate", True))),
        "trade_authorized": False,
        "ready": False,
        "continuity": "NEW_CAUSAL_EVENT_NEW_ACTIVE_WATCH",
        "event_id": current.get("event_id", result.get("event_id")),
        "event_timestamp": current.get("event_timestamp", result.get("event_timestamp")),
        "event_candle": current.get("event_candle", result.get("event_candle")),
        "age_bars": current.get("age_bars", 0),
        "age_minutes": current.get("age_minutes", 0),
    }


def install(module: Any) -> None:
    if getattr(module, "_PROFESSIONAL_LIFECYCLE_CONTRACT_V2", False):
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

        # A new causal event becomes a fresh active watch. Do this before the
        # generic REPLACED result can erase the new opportunity identity.
        if (
            previous.get("state") in ACTIVE
            and ps in WATCH_SETUPS
            and cs not in CONCRETE_EXCLUDED
            and _new_causal_event(previous, current)
        ):
            return _as_new_watch(result, current)

        if (
            previous.get("state") in ACTIVE
            and ps in WATCH_SETUPS
            and cs not in CONCRETE_EXCLUDED
            and ts in THESIS_STATES
            and not current.get("ready")
        ):
            result = {
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
    module._PROFESSIONAL_LIFECYCLE_CONTRACT_V2 = True
