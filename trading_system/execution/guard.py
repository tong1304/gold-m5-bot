from __future__ import annotations

import os


class ExecutionGuard:
    """Execution boundary. Default is fail-closed until explicitly enabled."""

    def __init__(self, live_enabled: bool | None = None):
        self.live_enabled = (os.getenv('TRADING_SYSTEM_LIVE_ENABLED', 'false').lower() == 'true') if live_enabled is None else live_enabled

    def authorize(self, decision_event: dict) -> bool:
        if not self.live_enabled:
            return False
        return decision_event.get('decision') in {'EXECUTE_LONG', 'EXECUTE_SHORT'}
