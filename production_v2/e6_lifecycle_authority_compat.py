from __future__ import annotations

from typing import Any


_PLACEHOLDERS = {"", "UNKNOWN", "NONE", "NO_SETUP", "UNRESOLVED", "NO_PLAUSIBLE_SETUP"}


def _direction(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"BUY", "UP", "BULLISH", "TREND_UP"} or text.startswith("BUY ") or text.startswith("BUY_"):
        return "BUY"
    if text in {"SELL", "DOWN", "BEARISH", "TREND_DOWN"} or text.startswith("SELL ") or text.startswith("SELL_"):
        return "SELL"
    return "NEUTRAL"


def _meaningful(value: Any) -> str:
    text = str(value or "").upper().strip()
    return "" if text in _PLACEHOLDERS else text


def _e6_state(e6: dict[str, Any]) -> str:
    # setup_state is the canonical lifecycle field; thesis_status is an alias.
    # Never let a placeholder producer value erase a meaningful E6 state.
    return (
        _meaningful(e6.get("setup_state"))
        or _meaningful(e6.get("thesis_status"))
        or _meaningful(e6.get("opportunity_stage"))
        or "FORMING"
    )


def _merge_meaningful(payload: dict[str, Any], key: str, value: Any) -> None:
    value_text = _meaningful(value)
    if value_text and not _meaningful(payload.get(key)):
        payload[key] = value_text


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E6_LIFECYCLE_AUTHORITY_COMPAT", False):
        return
    original = pipeline_module._directional_lifecycle_current

    def wrapped(*args: Any, **kwargs: Any):
        current, leader, competition = original(*args, **kwargs)
        results = args[0] if args and isinstance(args[0], dict) else kwargs.get("results") or {}
        e6_result = results.get("E6") if isinstance(results, dict) else None
        e6 = dict(getattr(e6_result, "output", {}) or {}) if e6_result is not None else {}
        direction = _direction(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction") or e6.get("finding"))
        setup = _meaningful(e6.get("setup")) or _meaningful(e6.get("setup_family")) or _meaningful(e6.get("setup_type"))
        setup_state = _e6_state(e6)
        concrete = bool(e6.get("setup_exists")) or setup not in {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
        if not concrete or direction not in {"BUY", "SELL"}:
            return current, leader, competition

        payload = current.get(direction)
        if not isinstance(payload, dict):
            payload = {"candidate": False, "direction": direction}
        if not payload.get("candidate"):
            missing = list(e6.get("missing_proof") or e6.get("wait_for") or [])
            event_id = e6.get("event_id") or e6.get("origin_event_id")
            payload.update({
                "candidate": True,
                "direction": direction,
                "setup": setup,
                "setup_family": setup,
                "setup_state": setup_state,
                "thesis_status": setup_state,
                "event_id": event_id,
                "origin_event_id": e6.get("origin_event_id") or event_id,
                "ready": False,
                "invalidated": False,
                "thesis_proven": bool(e6.get("e6_thesis_proven") or e6.get("setup_exists") or e6.get("trade_ready")),
                "wait_for": missing or ["NEXT_CLOSED_M5_CANDLE"],
                "candle": args[3] if len(args) > 3 else kwargs.get("candle"),
                "causal_event_anchor": dict((args[4] if len(args) > 4 else kwargs.get("causal_anchor")) or {}),
                "lifecycle_source": "E6_SETUP",
            })
            current[direction] = payload
        else:
            payload.setdefault("lifecycle_source", "E6_SETUP")
            _merge_meaningful(payload, "thesis_status", setup_state)
            _merge_meaningful(payload, "setup_state", setup_state)
            _merge_meaningful(payload, "setup", setup)
            _merge_meaningful(payload, "setup_family", setup)
            payload.setdefault("direction", direction)
            if e6.get("event_id") or e6.get("origin_event_id"):
                payload.setdefault("event_id", e6.get("event_id") or e6.get("origin_event_id"))
                payload.setdefault("origin_event_id", e6.get("origin_event_id") or e6.get("event_id"))
            if e6.get("missing_proof") and not payload.get("wait_for"):
                payload["wait_for"] = list(e6["missing_proof"])
        if leader == "NEUTRAL":
            leader = direction
        return current, leader, competition

    pipeline_module._directional_lifecycle_current = wrapped
    pipeline_module._E6_LIFECYCLE_AUTHORITY_COMPAT = True
