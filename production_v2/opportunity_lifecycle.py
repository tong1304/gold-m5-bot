from __future__ import annotations

from typing import Any

ACTIVE_STATES = {"WAITING", "READY"}
ACTIVE_THESIS_STATES = {"FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY"}
PENDING_SETUP_PREFIXES = ("OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH")


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _identity(direction: Any, setup: Any) -> str:
    direction = _text(direction)
    setup = _text(setup)
    if direction not in {"BUY", "SELL"} or not setup or setup in {"UNKNOWN", "NONE", "NO_SETUP"}:
        return ""
    return f"{direction}|{setup}"


def _is_pending_watch(setup: Any) -> bool:
    return _text(setup).startswith(PENDING_SETUP_PREFIXES)


def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Advance an opportunity across closed candles without changing trade gates."""
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

        if previous_direction and current_direction in {"BUY", "SELL"} and current_direction != previous_direction:
            return {
                **previous,
                "state": "INVALIDATED",
                "continuity": "OPPORTUNITY_INVALIDATED",
                "bars_waited": int(previous.get("bars_waited", 0) or 0),
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": "DIRECTION_CHANGED",
            }

        same_identity = bool(previous_id and identity == previous_id)
        current_is_watch = candidate and current_direction in {"BUY", "SELL"} and _is_pending_watch(current_setup)
        previous_is_real_setup = bool(previous_setup and not _is_pending_watch(previous_setup))

        # If a real E6 thesis loses its causal setup but upstream E2/E4 still
        # has explicit pending evidence, keep the directional watch alive. This
        # is a downgrade in thesis strength, not a promotion and not a reset.
        downgraded_to_watch = bool(
            previous_direction in {"BUY", "SELL"}
            and current_direction == previous_direction
            and previous_is_real_setup
            and current_is_watch
        )
        if downgraded_to_watch:
            return {
                **previous,
                "state": "WAITING",
                "continuity": "DOWNGRADED_TO_UPSTREAM_WATCH",
                "opportunity_id": _identity(current_direction, current_setup),
                "direction": current_direction,
                "setup": current_setup,
                "bars_waited": int(previous.get("bars_waited", 0) or 0) + 1,
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": None,
            }

        pending_to_setup = bool(
            previous_direction in {"BUY", "SELL"}
            and current_direction == previous_direction
            and _is_pending_watch(previous_setup)
            and candidate
            and current_setup not in {"", "UNKNOWN", "NONE", "NO_SETUP"}
            and not _is_pending_watch(current_setup)
        )

        if pending_to_setup:
            promoted_id = identity or previous_id
            return {
                **previous,
                "state": "READY" if ready else "WAITING",
                "continuity": "PROMOTED_PENDING_OPPORTUNITY_TO_SETUP" if ready else "PROMOTED_PENDING_OPPORTUNITY",
                "opportunity_id": promoted_id,
                "direction": current_direction,
                "setup": current_setup,
                "bars_waited": int(previous.get("bars_waited", 0) or 0) + 1,
                "last_evaluated_candle": candle,
                "trade_authorized": False,
                "invalidation_reason": None,
            }

        if previous_id and identity and identity != previous_id:
            reason = "DIRECTION_OR_SETUP_CHANGED"
            if previous_setup and current_setup and current_setup != previous_setup:
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

        thesis_preserved = same_identity and thesis_status in ACTIVE_THESIS_STATES
        pending_preserved = bool(
            previous_direction in {"BUY", "SELL"}
            and current_direction == previous_direction
            and _is_pending_watch(previous_setup)
            and thesis_status == "FORMING"
        )
        if not candidate and not thesis_preserved and not pending_preserved:
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
