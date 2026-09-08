from __future__ import annotations

"""Canonical lifecycle vocabulary for production-v2 opportunities.

This module is deliberately small: it owns stage semantics, not evidence
collection or trade authorization. E9 remains the execution authority.
"""

from typing import Final

VALID_STAGES: Final[frozenset[str]] = frozenset(
    {
        "IDLE",
        "WATCH",
        "THESIS",
        "CONFIRMING",
        "ACTIONABLE",
        "TRADE",
        "INVALIDATED",
        "EXPIRED",
        "TOO_LATE",
    }
)

# Terminal states cannot move back into an opportunity. ACTIONABLE can become
# TOO_LATE because timing can decay without invalidating the original thesis.
ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "IDLE": frozenset({"IDLE", "WATCH"}),
    "WATCH": frozenset({"WATCH", "THESIS", "CONFIRMING", "INVALIDATED", "EXPIRED", "TOO_LATE"}),
    "THESIS": frozenset({"THESIS", "CONFIRMING", "INVALIDATED", "EXPIRED", "TOO_LATE"}),
    "CONFIRMING": frozenset({"CONFIRMING", "ACTIONABLE", "INVALIDATED", "EXPIRED", "TOO_LATE"}),
    "ACTIONABLE": frozenset({"ACTIONABLE", "TRADE", "INVALIDATED", "EXPIRED", "TOO_LATE"}),
    "TRADE": frozenset({"TRADE"}),
    "INVALIDATED": frozenset({"INVALIDATED"}),
    "EXPIRED": frozenset({"EXPIRED"}),
    "TOO_LATE": frozenset({"TOO_LATE"}),
}


def can_transition(previous_stage: str, next_stage: str) -> bool:
    previous = str(previous_stage or "IDLE").upper().strip()
    next_value = str(next_stage or "IDLE").upper().strip()
    if previous not in VALID_STAGES or next_value not in VALID_STAGES:
        return False
    return next_value in ALLOWED_TRANSITIONS[previous]


def transition(previous_stage: str, next_stage: str) -> str:
    previous = str(previous_stage or "IDLE").upper().strip()
    next_value = str(next_stage or "IDLE").upper().strip()
    if not can_transition(previous, next_value):
        raise ValueError(f"Invalid opportunity transition: {previous} -> {next_value}")
    return next_value
