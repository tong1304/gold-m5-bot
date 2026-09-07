from __future__ import annotations

from typing import Any

VALID_DIRECTIONS = {"BUY", "SELL"}
TERMINAL_STATES = {"INVALIDATED", "EXPIRED", "REPLACED"}
ACTIVE_STATES = {"WATCHING", "WAITING", "READY"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _event(value: Any) -> str:
    return str(value or "").strip()


def _same_event(previous: Any, current: Any) -> bool:
    p, c = _event(previous), _event(current)
    if p and c:
        return p.casefold() == c.casefold()
    return not p and not c


def install(lifecycle_module: Any, pipeline_module: Any | None = None) -> None:
    if getattr(lifecycle_module, "_CONTRACT_SURGERY_INSTALLED", False):
        return

    original_advance = lifecycle_module.advance_opportunity

    def guarded_advance(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
        p = dict(previous or {})
        c = dict(current or {})
        state = _text(p.get("state"))
        if state in TERMINAL_STATES:
            previous_event = p.get("event_id") or p.get("origin_event_id")
            current_event = c.get("event_id") or c.get("origin_event_id")
            # A terminal opportunity must stay terminal on the same/no causal
            # event. It can reopen only when a genuinely new causal event exists.
            if _same_event(previous_event, current_event):
                out = dict(p)
                candle = c.get("candle")
                if candle not in (None, ""):
                    out["last_evaluated_candle"] = candle
                out["trade_authorized"] = False
                return out

        result = original_advance(p, c)

        # A new causal event currently falls through the legacy helper as
        # REPLACED, which makes the new opportunity disappear from the active
        # set. Promote that new event into a fresh WATCH/WAIT/READY state while
        # retaining the old identity only as historical lineage.
        if (
            _text(result.get("state")) == "REPLACED"
            and _text(p.get("state")) in ACTIVE_STATES
            and _text(c.get("direction")) in VALID_DIRECTIONS
            and bool(c.get("candidate"))
        ):
            direction = _text(c.get("direction"))
            setup = _text(c.get("setup") or c.get("setup_family") or "OPPORTUNITY_WATCH")
            event_id = c.get("event_id") or c.get("origin_event_id")
            opportunity_id = lifecycle_module._identity(direction, setup, event_id)
            if opportunity_id:
                ready = bool(c.get("ready"))
                return {
                    **c,
                    "state": "READY" if ready else "WATCHING" if setup in WATCH_SETUPS else "WAITING",
                    "lifecycle_state": "EXECUTABLE" if ready else "OPPORTUNITY_WATCH" if setup in WATCH_SETUPS else "TRIGGER_PENDING",
                    "opportunity_phase": "EXECUTABLE" if ready else "OPPORTUNITY_WATCH" if setup in WATCH_SETUPS else "TRIGGER_PENDING",
                    "continuity": "NEW_CAUSAL_EVENT_REPLACED_ACTIVE_OPPORTUNITY",
                    "previous_opportunity_id": p.get("opportunity_id"),
                    "opportunity_id": opportunity_id,
                    "event_id": event_id,
                    "origin_event_id": event_id,
                    "bars_waited": 0,
                    "origin_candle": c.get("candle"),
                    "last_evaluated_candle": c.get("candle"),
                    "trade_authorized": False,
                    "invalidation_reason": None,
                }
        return result

    lifecycle_module.advance_opportunity = guarded_advance
    lifecycle_module._CONTRACT_SURGERY_INSTALLED = True
    lifecycle_module._CONTRACT_SURGERY_ORIGINAL = original_advance

    if pipeline_module is not None:
        # pipeline.py imports the callable into its module namespace, so bind the
        # same guarded function there before later lifecycle membranes wrap it.
        pipeline_module.advance_opportunity = guarded_advance
        pipeline_module.advance_opportunity_directions = lifecycle_module.advance_opportunity_directions
