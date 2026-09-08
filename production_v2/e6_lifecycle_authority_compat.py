from __future__ import annotations

from typing import Any


def _direction(value: Any) -> str:
    text = str(value or "").upper().strip()
    if text in {"BUY", "UP", "BULLISH", "TREND_UP"} or text.startswith("BUY ") or text.startswith("BUY_"):
        return "BUY"
    if text in {"SELL", "DOWN", "BEARISH", "TREND_DOWN"} or text.startswith("SELL ") or text.startswith("SELL_"):
        return "SELL"
    return "NEUTRAL"


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
        setup = str(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type") or "").upper().strip()
        setup_state = str(e6.get("thesis_status") or e6.get("setup_state") or e6.get("opportunity_stage") or "FORMING").upper().strip()
        concrete = bool(e6.get("setup_exists")) or setup not in {"", "UNKNOWN", "NONE", "NO_SETUP", "OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
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
            payload.setdefault("thesis_status", setup_state)
            payload.setdefault("setup_state", setup_state)
        if leader == "NEUTRAL":
            leader = direction
        return current, leader, competition

    pipeline_module._directional_lifecycle_current = wrapped
    pipeline_module._E6_LIFECYCLE_AUTHORITY_COMPAT = True
