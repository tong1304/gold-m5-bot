from __future__ import annotations

from typing import Any

ALERT_NONE = "NONE"
ALERT_READY = "TRADE_ALERT"
ALERT_SENT = "ALERT_SENT"
USER_ACTION_REQUIRED = "USER_ACTION_REQUIRED"


def _truth(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in {"1", "TRUE", "YES", "PASS", "PASSED", "CONFIRMED", "READY", "TRADE"}
    return bool(value)


def build_trade_alert(result: Any, lifecycle: dict[str, Any] | None = None) -> dict[str, Any]:
    lifecycle = dict(lifecycle or {})
    decision = str(getattr(result, "decision", "NO_TRADE") or "NO_TRADE").upper().strip()
    gate = _truth(getattr(result, "gate_passed", False))
    stage = str(lifecycle.get("lifecycle_stage") or "").upper().strip()
    authorized = stage == "TRADE" and gate and decision in {"BUY", "SELL"}
    return {
        "state": ALERT_READY if authorized else ALERT_NONE,
        "user_action": USER_ACTION_REQUIRED if authorized else None,
        "direction": decision if authorized else None,
        "opportunity_id": lifecycle.get("opportunity_id"),
        "origin_event_id": lifecycle.get("origin_event_id"),
        "event_id": lifecycle.get("event_id"),
        "lifecycle_stage": stage or None,
        "alert_authorized_by": "E9" if authorized else None,
        "broker_execution": False,
        "position_open": False,
    }


def should_alert(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    previous = dict(previous or {})
    return current.get("state") == ALERT_READY and previous.get("state") != ALERT_READY
