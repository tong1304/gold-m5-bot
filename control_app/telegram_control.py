from __future__ import annotations

from .state_store import StateStore


class TelegramControl:
    def __init__(self, store: StateStore):
        self.store = store

    def get_telegram_enabled(self) -> bool:
        return self.store.get_telegram_enabled()

    def set_telegram_enabled(self, enabled: bool) -> bool:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be boolean")
        return self.store.set_telegram_enabled(enabled)
