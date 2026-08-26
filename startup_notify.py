from __future__ import annotations

import threading

from production_v2_telegram import send_telegram

_LOCK = threading.Lock()
_SENT = False


def _startup_message() -> str:
    return (
        "<b>✅ ระบบ 9-Engine เริ่มทำงาน</b>\n\n"
        "⚙️ ระบบ: PRODUCTION-V2\n"
        "🧠 โครงสร้าง: E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9\n"
        "📊 สินทรัพย์: GOLD, BTC\n"
        "⏱ Timeframe: M5\n\n"
        "✅ ระบบพร้อมทำงาน"
    )


def send_startup_notification(symbol="BTC + GOLD / LSE", engine_version=None):
    """Send the approved Production-V2 startup notification once per process."""
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
