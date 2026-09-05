"""Canonical opportunity-memory boundary.

The storage implementation remains in the legacy module during the migration;
callers depend on this domain boundary instead of its physical location.
"""

from ..opportunity_memory import backend, last_error, load, load_all, remove, save

__all__ = ["backend", "last_error", "load", "load_all", "remove", "save"]
