from __future__ import annotations

from typing import Any

ACTIVE_STATES = {"WAITING", "READY"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _identity(direction: Any, setup: Any) -> str:
    direction = _text(direction)
    setup = _text(setup)
    if direction not in {"BUY", "SELL"} or not setup or setup in {"UNKNOWN", "NONE", "NO_SETUP"}:
        return ""
    return f"{direction}|{setup}"


def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Advance one opportunity across closed candles without authorizing trades.

    The current candle is always re-evaluated by E1-E9. This function only
    preserves a still-valid opportunity identity and its waiting history; it
    never lowers a gate or invents a setup.
    """
    previous = dict(previous or {})
    current = dict(current or {})
    candle = _text(current.get("candle"))
    candidate = bool(current.get("candidate"))
    ready = bool(current.get("ready"))
    invalidated = bool(current.get("invalidated"))
    executed = bool(current.get("executed"))
    identity = _identity(current.get("direction"), current.get("setup"))
    previous_state = _text(previous.get("state"))
    previous_id = _text(previous.get("opportunity_id"))

    if executed:
        return {
            **previous,
            "state": "EXECUTE",
            "continuity": "E9_AUTHORIZED_EXECUTION",
            "bars_waited": int(previous.get("bars_waited", 0) or 0),
            "last_evaluated_candle": candle,
            "trade_authorized": True,
            "invalidation_reason": None,
        }

    if previous_state in ACTIVE_STATES:
        if invalidated or not candidate:
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": "CURRENT_CANDLE_INVALIDATED" if invalidated else "OPPORTUNITY_NO_LONGER_VALID",
            }
        if previous_id and identity != previous_id:
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": "DIRECTION_OR_SETUP_CHANGED",
            }
        bars_waited = int(previous.get("bars_waited", 0) or 0) + 1
        return {
            **previous,
            "state": "READY" if ready else "WAITING",
            "continuity": "ADVANCING_EXISTING_OPPORTUNITY" if ready else "CONTINUING_EXISTING_OPPORTUNITY",
            "bars_waited": bars_waited,
            "last_evaluated_candle": candle,
            "trade_authorized": False,
            "invalidation_reason": None,
        }

    if candidate:
        return {
            "state": "READY" if ready else "WAITING",
            "continuity": "NEW_OPPORTUNITY_READY" if ready else "NEW_OPPORTUNITY_WATCH",
            "opportunity_id": identity,
            "direction": _text(current.get("direction")),
            "setup": _text(current.get("setup")),
            "bars_waited": 0,
            "origin_candle": candle,
            "last_evaluated_candle": candle,
            "trade_authorized": False,
            "invalidation_reason": None,
        }

    return {
        "state": "IDLE",
        "continuity": "NO_ACTIVE_PENDING_OPPORTUNITY",
        "opportunity_id": None,
        "direction": "NEUTRAL",
        "setup": "UNKNOWN",
        "bars_waited": 0,
        "origin_candle": candle or None,
        "last_evaluated_candle": candle or None,
        "trade_authorized": False,
        "invalidation_reason": None,
    }
