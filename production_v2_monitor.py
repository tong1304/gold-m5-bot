from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from production_v2_telegram import send_system_monitor

logger = logging.getLogger("production_v2_monitor")
BANGKOK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc
_SLOTS = (0, 15, 30, 45)
_RUNNING = False
_THREAD = None
_LAST_SLOT = None


def _seconds_to_next_slot() -> float:
    now = datetime.now(UTC).astimezone(BANGKOK)
    next_minute = ((now.minute // 15) + 1) * 15
    if next_minute >= 60:
        target = (now.replace(second=0, microsecond=0, minute=0)).replace(hour=(now.hour + 1) % 24)
        if now.hour == 23:
            from datetime import timedelta
            target = now.replace(second=0, microsecond=0, minute=0) + timedelta(hours=1)
    else:
        target = now.replace(minute=next_minute, second=0, microsecond=0)
    return max(0.5, (target - now).total_seconds())


def run_once(now_bkk: datetime | None = None):
    global _LAST_SLOT
    now_bkk = now_bkk or datetime.now(UTC).astimezone(BANGKOK)
    if now_bkk.minute not in _SLOTS:
        return False
    slot = now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot == _LAST_SLOT:
        return False
    result = send_system_monitor(now_bkk)
    if result:
        _LAST_SLOT = slot
    return bool(result)


def _loop():
    logger.warning("[PRODUCTION-V2 TELEGRAM] 15-minute monitor started timezone=Asia/Bangkok slots=00,15,30,45")
    while _RUNNING:
        time.sleep(_seconds_to_next_slot())
        if _RUNNING:
            try:
                run_once(datetime.now(UTC).astimezone(BANGKOK))
            except Exception:
                logger.exception("[PRODUCTION-V2 TELEGRAM] monitor cycle failed")


def start() -> bool:
    global _RUNNING, _THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():
        return False
    _RUNNING = True
    _THREAD = threading.Thread(target=_loop, name="production-v2-telegram-15m", daemon=True)
    _THREAD.start()
    return True


def stop():
    global _RUNNING
    _RUNNING = False


def status() -> dict:
    return {
        "running": bool(_RUNNING and _THREAD and _THREAD.is_alive()),
        "slots": "00,15,30,45",
        "timezone": "Asia/Bangkok",
        "last_slot": _LAST_SLOT,
    }
