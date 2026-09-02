from __future__ import annotations

from typing import Any

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")


def _text(value: Any) -> str:
    return str(value if value is not None else "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    for value in (
        output.get("direction"), output.get("opportunity_direction"),
        output.get("direction_thesis"), output.get("thesis_direction"),
        output.get("finding"),
    ):
        text = _text(value)
        if text in {"BUY", "UP", "BULLISH", "TREND_UP"} or text.startswith("BUY "):
            return "BUY"
        if text in {"SELL", "DOWN", "BEARISH", "TREND_DOWN"} or text.startswith("SELL "):
            return "SELL"
    return "NEUTRAL"


def build_handoff(engine_id: str, output: dict[str, Any], upstream_outputs: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """Build an immutable-style evidence packet for the next brain.

    The packet carries upstream observations forward but explicitly prevents a
    downstream specialist from becoming authoritative over another specialist.
    """
    out = dict(output or {})
    upstream = {key: dict(value or {}) for key, value in (upstream_outputs or {}).items()}
    return {
        "engine": engine_id,
        "direction": _direction(out),
        "stage": _text(out.get("opportunity_stage") or out.get("stage") or out.get("state")),
        "state": _text(out.get("opportunity_state") or out.get("state")),
        "next_required_event": out.get("opportunity_next_event") or out.get("next_required_event"),
        "upstream": upstream,
        "authority": f"{engine_id}_OWN_SCOPE_ONLY",
        "must_not_rewrite_upstream": True,
    }


def build_lifecycle(results: dict[str, Any]) -> dict[str, Any]:
    """Summarize the current opportunity without authorizing a trade."""
    outputs: dict[str, dict[str, Any]] = {}
    for key, value in (results or {}).items():
        outputs[key] = dict(value.output) if hasattr(value, "output") else dict(value or {})

    directions = [_direction(outputs[key]) for key in ("E2", "E4", "E5", "E6") if key in outputs]
    direction = "SELL" if directions.count("SELL") > directions.count("BUY") else "BUY" if directions.count("BUY") > directions.count("SELL") else "NEUTRAL"

    invalidated = any(
        "INVALID" in _text(outputs[key].get("opportunity_stage") or outputs[key].get("state"))
        for key in outputs
    )
    waiting_stages = {"AUCTION_PENDING", "REGIME_DEVELOPING", "FORMING", "WAITING_CONFIRMATION"}
    waiting = any(
        _text(outputs[key].get("opportunity_stage") or outputs[key].get("state")) in waiting_stages
        for key in outputs
    )

    if invalidated:
        state = "INVALIDATED"
    elif waiting:
        state = "WAITING"
    else:
        state = "OBSERVING"

    next_required_event = next(
        (
            outputs[key].get("opportunity_next_event") or outputs[key].get("next_required_event")
            for key in ("E4", "E5", "E2", "E6", "E7", "E8")
            if key in outputs and (outputs[key].get("opportunity_next_event") or outputs[key].get("next_required_event"))
        ),
        None,
    )
    return {
        "state": state,
        "direction": direction,
        "next_required_event": next_required_event,
        "trade_authorized": False,
        "authority": "E9",
    }
