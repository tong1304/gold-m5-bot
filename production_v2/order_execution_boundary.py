from __future__ import annotations

from typing import Any

STATES = ("NONE", "ORDER_INTENT", "ORDER_SUBMITTED", "BROKER_ACCEPTED", "POSITION_OPEN")
RANK = {state: i for i, state in enumerate(STATES)}


class ExecutionBoundaryError(ValueError):
    """Raised when execution state advances without the required authority/ack."""


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def initial_execution_state(e9: dict[str, Any] | None) -> dict[str, Any]:
    e9 = dict(e9 or {})
    decision = _text(e9.get("decision"))
    if decision not in {"BUY", "SELL", "TRADE"} or not bool(e9.get("gate_passed")):
        return {"state": "NONE", "authorized_by": None, "history": []}
    return {"state": "ORDER_INTENT", "authorized_by": "E9", "history": ["ORDER_INTENT"]}


def advance_execution_state(state: dict[str, Any], acknowledgement: str) -> dict[str, Any]:
    current = dict(state or {})
    current_state = _text(current.get("state")) or "NONE"
    target = _text(acknowledgement)
    if current_state not in RANK or target not in RANK:
        raise ExecutionBoundaryError(f"UNKNOWN_EXECUTION_STATE:{current_state}->{target}")
    if current_state == "NONE":
        raise ExecutionBoundaryError("E9_ORDER_INTENT_REQUIRED")
    if RANK[target] != RANK[current_state] + 1:
        raise ExecutionBoundaryError(f"INVALID_EXECUTION_TRANSITION:{current_state}->{target}")
    history = list(current.get("history") or [])
    history.append(target)
    current["state"] = target
    current["history"] = history
    current.setdefault("authorized_by", "E9")
    return current
