from __future__ import annotations

from functools import wraps
from typing import Any

ACTIVE = {"WATCHING", "WAITING", "READY"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def install(module: Any) -> None:
    if getattr(module, "_PROFESSIONAL_LIFECYCLE_IDENTITY_V1", False):
        return
    original = module.advance_opportunity

    @wraps(original)
    def advance_opportunity(previous: dict[str, Any] | None, current: dict[str, Any]):
        previous = dict(previous or {})
        current = dict(current or {})
        result = original(previous, current)
        p_state = _text(previous.get("state"))
        p_direction = _text(previous.get("direction"))
        p_event = str(previous.get("event_id") or previous.get("origin_event_id") or "").strip()
        c_direction = _text(current.get("direction"))
        c_event = str(current.get("event_id") or current.get("origin_event_id") or "").strip()
        p_id = str(previous.get("opportunity_id") or "").strip()
        setup = _text(current.get("setup") or current.get("setup_family"))
        if (
            p_state in ACTIVE
            and p_direction in {"BUY", "SELL"}
            and c_direction == p_direction
            and c_event
            and c_event != p_event
            and c_event != p_id
        ):
            new_id = f"{c_direction}|{setup or 'OPPORTUNITY_WATCH'}|{c_event}"
            return {
                **current,
                "state": "REPLACED",
                "lifecycle_state": "REPLACED",
                "opportunity_phase": "REPLACED",
                "continuity": "NEW_CAUSAL_EVENT_REPLACED_ACTIVE_OPPORTUNITY",
                "previous_opportunity_id": p_id,
                "opportunity_id": new_id,
                "event_id": c_event,
                "origin_event_id": c_event,
                "bars_waited": 0,
                "origin_candle": current.get("candle") or previous.get("origin_candle"),
                "last_evaluated_candle": current.get("candle") or previous.get("last_evaluated_candle"),
                "trade_authorized": False,
                "ready": False,
                "invalidation_reason": "NEW_CAUSAL_EVENT",
            }
        return result

    module.advance_opportunity = advance_opportunity
    module._PROFESSIONAL_LIFECYCLE_IDENTITY_V1 = True
