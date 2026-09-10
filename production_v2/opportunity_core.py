from __future__ import annotations

"""Canonical opportunity record boundary.

The production-v2 runtime historically carries a wide compatibility dictionary.
This module gives downstream consumers one stable semantic view without
removing or rewriting those legacy fields.
"""

from dataclasses import asdict, dataclass
from typing import Any

from .opportunity_state_machine import VALID_STAGES

_PLACEHOLDER = {"", "NONE", "UNKNOWN", "NO_SETUP", "NO_PLAUSIBLE_SETUP", "UNRESOLVED"}


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text.upper() if text else default


def _meaningful(value: Any) -> str:
    text = _text(value)
    return "" if text in _PLACEHOLDER else text


def canonical_stage(lifecycle: dict[str, Any] | None, *, e9_decision: str | None = None) -> str:
    """Map compatibility lifecycle fields into the canonical opportunity vocabulary."""
    data = dict(lifecycle or {})
    decision = _text(e9_decision)
    state = _text(data.get("state"))
    phase = _text(data.get("opportunity_phase"))
    invalidation = _text(data.get("invalidation_reason"))
    if decision in {"BUY", "SELL", "TRADE"} and decision == "TRADE":
        return "TRADE"
    if state in {"INVALIDATED", "REPLACED"} or phase == "INVALIDATED" or invalidation:
        return "INVALIDATED"
    if state == "EXPIRED" or phase == "EXPIRED":
        return "EXPIRED"
    if state in {"TOO_LATE", "LATE"} or phase in {"TOO_LATE", "LATE_OPPORTUNITY"}:
        return "TOO_LATE"
    if state == "READY" or phase in {"EXECUTABLE", "ACTIONABLE"}:
        return "ACTIONABLE"
    if state == "WAITING":
        return "CONFIRMING" if bool(data.get("thesis_proven") or data.get("e6_thesis_proven")) else "THESIS"
    if state == "WATCHING" or phase in {"OPPORTUNITY_WATCH", "FORMING", "DEVELOPING"}:
        return "WATCH"
    if state == "EXECUTED":
        return "TRADE"
    return "IDLE"


@dataclass(frozen=True)
class OpportunityRecord:
    opportunity_id: str | None
    symbol: str
    timeframe: str
    direction: str
    setup: str
    event_anchor: dict[str, Any]
    origin_candle: Any
    last_evaluated_candle: Any
    age_bars: int
    stage: str
    thesis_state: str
    confirmation_state: str
    invalidation_reason: str | None
    execution_zone: dict[str, Any]
    edge_remaining: float | None
    decision_authority: str = "E9_ONLY"

    @classmethod
    def from_lifecycle(
        cls,
        lifecycle: dict[str, Any] | None,
        symbol: str,
        timeframe: str,
        *,
        edge_remaining: float | None = None,
        e9_decision: str | None = None,
    ) -> "OpportunityRecord":
        data = dict(lifecycle or {})
        stage = canonical_stage(data, e9_decision=e9_decision)

        # Compatibility dictionaries frequently carry placeholders from a
        # downstream brain. Never let those placeholders erase meaningful
        # lifecycle evidence already present in the same record.
        thesis = _meaningful(data.get("thesis_state"))
        if not thesis:
            for key in ("thesis_lifecycle", "maturity", "setup_state", "opportunity_stage"):
                thesis = _meaningful(data.get(key))
                if thesis:
                    break
        if not thesis:
            thesis = "PROVEN" if bool(data.get("thesis_proven") or data.get("e6_thesis_proven")) else (
                "INVALIDATED" if stage == "INVALIDATED" else "PENDING"
            )

        confirmation = _meaningful(data.get("confirmation_state"))
        if not confirmation:
            confirmation = _meaningful(data.get("e7_confirmation_state")) or "PENDING"

        zone = data.get("execution_zone")
        if not isinstance(zone, dict):
            zone = data.get("entry_zone") if isinstance(data.get("entry_zone"), dict) else {}
        edge = edge_remaining
        if edge is None:
            raw_edge = data.get("edge_remaining")
            try:
                edge = float(raw_edge) if raw_edge is not None else None
            except (TypeError, ValueError):
                edge = None
        age = data.get("age_bars", data.get("bars_waited", 0))
        try:
            age = max(0, int(age or 0))
        except (TypeError, ValueError):
            age = 0
        anchor = data.get("causal_event_anchor")
        if not isinstance(anchor, dict):
            anchor = {}

        setup = _meaningful(data.get("setup"))
        if not setup:
            for key in ("candidate_setup", "setup_family", "setup_type", "thesis_setup", "selected_hypothesis"):
                setup = _meaningful(data.get(key))
                if setup:
                    break
        setup = setup or "UNKNOWN"

        return cls(
            opportunity_id=data.get("opportunity_id"),
            symbol=_text(symbol, "UNKNOWN"),
            timeframe=_text(timeframe, "M5"),
            direction=_text(data.get("direction"), "NEUTRAL"),
            setup=setup,
            event_anchor=dict(anchor),
            origin_candle=data.get("origin_candle"),
            last_evaluated_candle=data.get("last_evaluated_candle"),
            age_bars=age,
            stage=stage,
            thesis_state=thesis,
            confirmation_state=confirmation,
            invalidation_reason=data.get("invalidation_reason"),
            execution_zone=dict(zone),
            edge_remaining=edge,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Defensive contract check: a malformed stage should never leave the
        # canonical boundary silently.
        if data["stage"] not in VALID_STAGES:
            raise ValueError(f"Invalid canonical opportunity stage: {data['stage']}")
        return data
