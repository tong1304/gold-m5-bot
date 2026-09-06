from __future__ import annotations

"""Retrospective terminal-opportunity measurement at the lifecycle boundary.

This boundary observes transitions only. It never changes E9 authority or
trade authorization. Measurements are attached to the lifecycle state so the
existing PostgreSQL memory save persists them across restarts.
"""

from functools import wraps
from typing import Any, Callable

from .missed_opportunity import measure_terminal_opportunity
from .opportunity_memory import append_terminal_outcome

_TERMINAL = {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED"}


def _closed_bars(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict) and item.get("timestamp")]
    return []


def _with_terminal_context(current: dict[str, Any]) -> dict[str, Any]:
    """Preserve only already-closed follow-up bars supplied by upstream code."""
    bars = _closed_bars(current.get("closed_followup_bars") or current.get("followup_bars"))
    if not bars:
        return current
    ordered = sorted(bars, key=lambda item: str(item.get("timestamp")))
    return {**current, "closed_followup_bars": ordered}


def _measure_transition(previous: dict[str, Any], current: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    previous_map = previous.get("opportunities") if isinstance(previous.get("opportunities"), dict) else {}
    current_map = current.get("opportunities") if isinstance(current.get("opportunities"), dict) else {}
    state = dict(current)
    measurements = list(state.get("missed_opportunity_outcomes") or [])

    for direction in ("BUY", "SELL"):
        prior = previous_map.get(direction) if isinstance(previous_map.get(direction), dict) else {}
        now = current_map.get(direction) if isinstance(current_map.get(direction), dict) else {}
        prior_state = str(prior.get("state") or "").upper()
        now_state = str(now.get("state") or "").upper()
        if prior_state not in {"WATCHING", "WAITING", "READY"} or now_state not in _TERMINAL:
            continue
        if not prior.get("opportunity_id"):
            continue
        if str(prior.get("direction") or direction).upper() != direction:
            continue
        measured = measure_terminal_opportunity(prior, now, _closed_bars(now.get("closed_followup_bars")))
        if not measured:
            continue
        changed, state = append_terminal_outcome(state, measured)
        if changed:
            measurements.append(measured)

    if measurements:
        state["last_missed_opportunity_outcome"] = measurements[-1]
    return state, measurements[-1] if measurements else None


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_TERMINAL_OPPORTUNITY_RUNTIME_BOUND", False):
        return
    original: Callable[..., Any] = pipeline_module.advance_opportunity_directions

    @wraps(original)
    def wrapped(previous: dict[str, Any] | None, current_by_direction: dict[str, dict[str, Any]], *, leader: str = "NEUTRAL", competition: str = "UNCONTESTED"):
        prepared = {direction: _with_terminal_context(dict(current_by_direction.get(direction) or {})) for direction in ("BUY", "SELL")}
        current = original(previous, prepared, leader=leader, competition=competition)
        if not isinstance(current, dict):
            return current
        enriched, outcome = _measure_transition(dict(previous or {}), current)
        if outcome:
            enriched["missed_opportunity_measurement"] = outcome
        enriched["missed_opportunity_count"] = len(enriched.get("missed_opportunity_outcomes") or [])
        return enriched

    pipeline_module.advance_opportunity_directions = wrapped
    pipeline_module._TERMINAL_OPPORTUNITY_RUNTIME_BOUND = True
