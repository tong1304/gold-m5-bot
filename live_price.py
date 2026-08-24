from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_RUNNING = False
_THREAD = None
_WATCHDOG = None
_CLIENT = None
_CONNECTED = False
_AUTHENTICATED = False
_LOOP_STATE = "stopped"
_LAST_ERROR = None
_LAST_TICK_AT = None
_LAST_HEARTBEAT = 0.0
_RESTART_COUNT = 0
_TICKS_RECEIVED = 0
_STATE_CHANGED_AT = time.monotonic()

HEARTBEAT_SECONDS = float(os.getenv("LIVE_PRICE_HEARTBEAT_SECONDS", "30"))
CONNECT_TIMEOUT_SECONDS = float(os.getenv("LIVE_PRICE_CONNECT_TIMEOUT_SECONDS", "30"))
AUTH_TICK_TIMEOUT_SECONDS = float(os.getenv("LIVE_PRICE_AUTH_TICK_TIMEOUT_SECONDS", "45"))
TICK_STALE_SECONDS = float(os.getenv("LIVE_PRICE_TICK_STALE_SECONDS", "90"))


def _set_state(state: str):
    global _LOOP_STATE, _STATE_CHANGED_AT
    _LOOP_STATE = state
    _STATE_CHANGED_AT = time.monotonic()


def _age_seconds(value):
    if value is None:
        return None
    return max(0.0, time.monotonic() - value)


def _state_age():
    return max(0.0, time.monotonic() - _STATE_CHANGED_AT)


def _max_age():
    return TICK_STALE_SECONDS


def _watchdog_loop():
    global _WATCHDOG, _RESTART_COUNT, _LAST_ERROR, _CONNECTED, _AUTHENTICATED, _CLIENT, _LAST_HEARTBEAT
    logger.warning("[LIVE PRICE] Watchdog started")
    while _RUNNING:
        time.sleep(10)
        if not _RUNNING:
            break
        restart = False
        reason = None
        client = None
        with _LOCK:
            alive = bool(_THREAD and _THREAD.is_alive())
            state_age = _state_age()
            last_age = _age_seconds(_LAST_TICK_AT) if _LAST_TICK_AT else None
            now = time.monotonic()
            if alive and now - _LAST_HEARTBEAT >= HEARTBEAT_SECONDS:
                _LAST_HEARTBEAT = now
                logger.warning("[LIVE PRICE] Heartbeat state=%s connected=%s authenticated=%s ticks=%s state_age=%.1fs last_tick_age=%s", _LOOP_STATE, _CONNECTED, _AUTHENTICATED, _TICKS_RECEIVED, state_age or 0.0, "none" if last_age is None else f"{last_age:.1f}s")
            if not alive:
                restart = True
                reason = "worker_not_alive"
            elif _LOOP_STATE == "connecting" and state_age > CONNECT_TIMEOUT_SECONDS:
                restart = True
                reason = f"connect_timeout_{state_age:.1f}s"
            elif _LOOP_STATE in ("connected_waiting_for_authentication", "authenticated_waiting_for_tick") and state_age > AUTH_TICK_TIMEOUT_SECONDS:
                restart = True
                reason = f"tick_timeout_{state_age:.1f}s"
            elif _TICKS_RECEIVED > 0 and last_age is not None and last_age > _max_age():
                restart = True
                reason = f"stale_ticks_{last_age:.1f}s"
            if restart:
                _RESTART_COUNT += 1
                _LAST_ERROR = f"Live price watchdog restart: {reason}"
                _CONNECTED = False
                _AUTHENTICATED = False
                _set_state("watchdog_restarting")
                client = _CLIENT
                _CLIENT = None
                logger.error("[LIVE PRICE] Watchdog restart #%s reason=%s", _RESTART_COUNT, reason)
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                logger.exception("[LIVE PRICE] Error disconnecting stale client")


def get_status():
    with _LOCK:
        return {
            "running": _RUNNING,
            "worker_alive": bool(_THREAD and _THREAD.is_alive()),
            "watchdog_alive": bool(_WATCHDOG and _WATCHDOG.is_alive()),
            "state": _LOOP_STATE,
            "connected": _CONNECTED,
            "authenticated": _AUTHENTICATED,
            "ticks_received": _TICKS_RECEIVED,
            "restart_count": _RESTART_COUNT,
            "last_error": _LAST_ERROR,
            "last_tick_at": _LAST_TICK_AT,
            "heartbeat_at": _LAST_HEARTBEAT,
            "state_age_seconds": round(_state_age(), 2),
        }
