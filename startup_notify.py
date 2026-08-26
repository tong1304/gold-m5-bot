from __future__ import annotations

import threading

from production_v2_telegram import send_telegram, format_system_monitor_message

_LOCK = threading.Lock()
_SENT = False


def send_startup_notification(symbol="BTC + GOLD / LSE", engine_version=None):
    """Send the same approved Production-V2 status format at startup once."""
    global _SENT
    with _LOCK:
        if _SENT:
            return False
        try:
            result = send_telegram(format_system_monitor_message())
            if result.get("success"):
                _SENT = True
                return True
        except Exception:
            pass
        return False
