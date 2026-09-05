from __future__ import annotations

from typing import Any


# Analysis authority and broker execution are deliberately separate domains.
EXECUTION_STATES = (
    "NOT_REQUESTED",
    "ORDER_INTENT",
    "ORDER_SUBMITTED",
    "ACCEPTED",
    "REJECTED",
    "POSITION_OPEN",
    "POSITION_CLOSED",
)

TERMINAL = {"REJECTED", "POSITION_CLOSED"}


def initial_execution_state() -> dict[str, Any]:
    return {"state": "NOT_REQUESTED", "order_id": None, "position_id": None, "error": None}


def authorize_order(result: Any) -> dict[str, Any]:
    """Create an intent only when E9 authorizes BUY/SELL.

    This function never claims that a broker accepted or opened the order.
    """
    decision = str(getattr(result, "decision", "NO_TRADE") or "NO_TRADE").upper().strip()
    gate = bool(getattr(result, "gate_passed", False))
    if decision not in {"BUY", "SELL"} or not gate:
        return initial_execution_state()
    return {"state": "ORDER_INTENT", "order_id": None, "position_id": None, "error": None}


def transition(previous: dict[str, Any] | None, state: str, *, order_id: Any = None, position_id: Any = None, error: Any = None) -> dict[str, Any]:
    state = str(state or "").upper().strip()
    if state not in EXECUTION_STATES:
        raise ValueError(f"invalid execution state: {state}")
    current = dict(previous or initial_execution_state())
    current.update({"state": state, "order_id": order_id if order_id is not None else current.get("order_id"), "position_id": position_id if position_id is not None else current.get("position_id"), "error": str(error) if error is not None else None})
    return current


def is_executed(execution: dict[str, Any] | None) -> bool:
    return str((execution or {}).get("state") or "").upper() == "POSITION_OPEN"
