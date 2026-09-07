from __future__ import annotations

from typing import Any, Callable


_VALID_SPEEDS = {"FAST", "STANDARD", "SLOW", "BLOCK"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _timing_fields(current: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Carry opportunity-timing metadata across lifecycle normalization without granting authority."""
    current = dict(current or {})
    previous = dict(previous or {})
    timing = current.get("opportunity_timing") if isinstance(current.get("opportunity_timing"), dict) else {}
    previous_timing = previous.get("opportunity_timing") if isinstance(previous.get("opportunity_timing"), dict) else {}

    phase = _text(current.get("opportunity_phase") or timing.get("phase") or previous.get("opportunity_phase") or previous_timing.get("phase"))
    speed = _text(
        current.get("opportunity_speed")
        or current.get("opportunity_decision_speed")
        or timing.get("decision_speed")
        or previous.get("opportunity_speed")
        or previous.get("opportunity_decision_speed")
        or previous_timing.get("decision_speed")
    )
    if speed not in _VALID_SPEEDS:
        speed = "SLOW" if phase == "LATE_OPPORTUNITY" else "STANDARD"

    confirmation_window = (
        current.get("confirmation_window")
        or timing.get("confirmation_window")
        or previous.get("confirmation_window")
        or previous_timing.get("confirmation_window")
    )
    chase_prohibited = bool(
        current.get("chase_prohibited")
        if "chase_prohibited" in current
        else previous.get("chase_prohibited", phase == "LATE_OPPORTUNITY")
    )

    if phase == "LATE_OPPORTUNITY":
        speed = "SLOW"
        confirmation_window = confirmation_window or "NEW_CAUSAL_EVENT"
        chase_prohibited = True
        wait_for = "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
    elif phase == "EARLY_OPPORTUNITY":
        confirmation_window = confirmation_window or "NEXT_CLOSED_M5_CANDLE"
        wait_for = "FAST_CLOSED_CANDLE_CONFIRMATION" if speed == "FAST" else "CLOSED_CANDLE_CONFIRMATION"
    else:
        wait_for = current.get("wait_for") or previous.get("wait_for")

    return {
        "opportunity_phase": phase,
        "opportunity_speed": speed,
        "confirmation_window": confirmation_window,
        "chase_prohibited": chase_prohibited,
        "wait_for": wait_for,
        "timing_source": "OPPORTUNITY_TIMING_LIFECYCLE_MEMBRANE",
    }


def _decorate(result: dict[str, Any], current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(result or {})
    timing = _timing_fields(current, previous)
    if timing["opportunity_phase"]:
        out.update(timing)
    # Lifecycle state is observational. E9 remains the only authority capable of
    # setting execution/trade authorization.
    out["trade_authorized"] = False
    return out


def install(pipeline_module: Any) -> Callable[..., dict[str, Any]]:
    """Wrap the pipeline's imported lifecycle function after module import."""
    original = getattr(pipeline_module, "advance_opportunity_directions")
    if getattr(original, "_timing_membrane", False):
        return original

    def wrapped(previous: dict[str, Any] | None, current_by_direction: dict[str, dict[str, Any]], *, leader: str = "NEUTRAL", competition: str = "UNCONTESTED") -> dict[str, Any]:
        current = {direction: dict(current_by_direction.get(direction) or {}) for direction in ("BUY", "SELL")}
        previous_map = previous.get("opportunities") if isinstance(previous, dict) and isinstance(previous.get("opportunities"), dict) else {}
        for direction in ("BUY", "SELL"):
            prior = previous_map.get(direction) if isinstance(previous_map, dict) and isinstance(previous_map.get(direction), dict) else None
            current[direction].update(_timing_fields(current[direction], prior))

        result = original(previous, current, leader=leader, competition=competition)
        output = dict(result or {})
        opportunities = output.get("opportunities") if isinstance(output.get("opportunities"), dict) else {}
        for direction in ("BUY", "SELL"):
            item = opportunities.get(direction)
            if isinstance(item, dict):
                prior = previous_map.get(direction) if isinstance(previous_map, dict) and isinstance(previous_map.get(direction), dict) else None
                opportunities[direction] = _decorate(item, current[direction], prior)
        output["opportunities"] = opportunities

        leader_item = opportunities.get(_text(output.get("leader"))) if _text(output.get("leader")) in {"BUY", "SELL"} else None
        if isinstance(leader_item, dict):
            for key in ("opportunity_phase", "opportunity_speed", "confirmation_window", "chase_prohibited", "wait_for", "timing_source"):
                if key in leader_item:
                    output[key] = leader_item[key]
        output["trade_authorized"] = False
        output["timing_membrane"] = "ACTIVE"
        return output

    wrapped._timing_membrane = True
    wrapped._timing_original = original
    pipeline_module.advance_opportunity_directions = wrapped
    return wrapped
