from __future__ import annotations

import threading

from production_v2_telegram import format_system_monitor_message, send_telegram

_LOCK = threading.Lock()
_SENT = False

STARTUP_FORMAT = "PRODUCTION-V2-E1-E9-STATUS"


def _startup_message() -> str:
    """Use the single Production-V2 status contract for startup as well."""
    return format_system_monitor_message()


def send_startup_notification(symbol="BTC + GOLD / LSE", engine_version=None):
    """Send the Production-V2 startup/status notification once per process."""
    global _SENT
    with _LOCK:
        if _SENT:
            return False
        try:
            result = send_telegram(_startup_message())
            if result.get("success"):
                _SENT = True
                return True
        except Exception:
            pass
        return False
