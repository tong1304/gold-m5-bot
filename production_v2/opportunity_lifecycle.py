"""Compatibility facade for the canonical opportunity lifecycle domain."""

from .opportunity.lifecycle import (
    ACTIVE_STATES,
    MAX_WATCH_BARS,
    TERMINAL_STATES,
    VALID_DIRECTIONS,
    WATCH_SETUPS,
    advance_opportunity,
)

# Historical callers used TERMINAL; retain it as an alias during migration.
TERMINAL = TERMINAL_STATES

__all__ = [
    "ACTIVE_STATES",
    "MAX_WATCH_BARS",
    "TERMINAL",
    "TERMINAL_STATES",
    "VALID_DIRECTIONS",
    "WATCH_SETUPS",
    "advance_opportunity",
]
