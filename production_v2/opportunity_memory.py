"""Compatibility facade for the canonical opportunity-memory storage boundary."""

from .opportunity.memory import backend, last_error, load, load_all, remove, save

__all__ = ["backend", "last_error", "load", "load_all", "remove", "save"]
