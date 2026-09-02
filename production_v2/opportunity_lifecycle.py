from __future__ import annotations

from typing import Any

ACTIVE_STATES = {"WAITING", "READY"}
ACTIVE_THESIS_STATES = {"FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _identity(direction: Any, setup: Any) -> str:
    direction = _text(direction)
    setup = _text(setup)
    if direction not in {"BUY", "SELL"} or not setup or setup in {"UNKNOWN", "NONE", "NO_SETUP"}:
        return ""
    return f"{direction}|{setup}"


def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Advance an opportunity across closed candles without changing trade gates.

    E1-E9 are still re-evaluated on every new closed candle. Lifecycle state is
    only retained when the current candle explicitly preserves the same causal
    thesis or independently produces the same candidate. Missing evidence is
    not treated as an automatic invalidation; explicit invalidation remains a
    hard stop. E9 remains the sole execution authority.
    """
    previous = dict(previous or {})
    current = dict(current or {})
    candle = _text(current.get("candle"))
    candidate = bool(current.get("candidate"))
    ready = bool(current.get("ready"))
    invalidated = bool(current.get("invalidated"))
    executed = bool(current.get("executed"))
    thesis_status = _text(current.get("thesis_status"))
    current_direction = _text(current.get("direction"))
    current_setup = _text(current.get("setup"))
    identity = _identity(current_direction, current_setup)
    previous_state = _text(previous.get("state"))
    previous_id = _text(previous.get("opportunity_id"))
    previous_direction = _text(previous.get("direction"))
    previous_setup = _text(previous.get("setup"))

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
        if invalidated:
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": "CURRENT_CANDLE_INVALIDATED",
            }

        if previous_id and identity and identity != previous_id:
            reason = "DIRECTION_OR_SETUP_CHANGED"
            if previous_direction and current_direction != previous_direction:
                reason = "DIRECTION_CHANGED"
            elif previous_setup and current_setup != previous_setup:
                reason = "SETUP_CHANGED"
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": reason,
            }

        same_identity = bool(previous_id and identity == previous_id)
        thesis_preserved = same_identity and thesis_status in ACTIVE_THESIS_STATES
        if candidate and not same_identity:
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": "DIRECTION_OR_SETUP_CHANGED",
            }
        if not candidate and not thesis_preserved:
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": "THESIS_NOT_PRESERVED",
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
            "direction": current_direction,
            "setup": current_setup,
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
