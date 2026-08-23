import logging
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from lse import LSE

logger = logging.getLogger("live_price")
BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = ("BTC/USD", "XAU/USD")

_LOCK = threading.RLock()
_THREAD = None
_WATCHDOG_THREAD = None
_RUNNING = False
_CLIENT = None
_LATEST = {}
_LAST_ERROR = None
_CONNECTED = False
_AUTHENTICATED = False
_TICKS_RECEIVED = 0
_LAST_TICK_AT = None
_STARTED_AT = None
_LOOP_STATE = "stopped"
_RESTART_COUNT = 0


def _api_key():
    return os.getenv("LSE_API_KEY", "").strip()


def _set_tick(tick):
    global _LAST_ERROR, _TICKS_RECEIVED, _LAST_TICK_AT, _CONNECTED, _LOOP_STATE
    symbol = str(getattr(tick, "symbol", "") or "").upper()
    if symbol not in SYMBOLS:
        return
    price = getattr(tick, "price", None)
    try:
        price = float(price)
    except (TypeError, ValueError):
        return
    if price <= 0:
        return
    timestamp = getattr(tick, "timestamp", None)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    received_at = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        _LATEST[symbol] = {
            "symbol": symbol,
            "price": price,
            "bid": getattr(tick, "bid", None),
            "ask": getattr(tick, "ask", None),
            "volume": getattr(tick, "volume", None),
            "timestamp": str(timestamp),
            "received_at": received_at,
            "replay": bool(getattr(tick, "replay", False)),
        }
        _LAST_ERROR = None
        _TICKS_RECEIVED += 1
        _LAST_TICK_AT = received_at
        _CONNECTED = True
        _LOOP_STATE = "receiving_ticks"
    logger.info("[LIVE PRICE] %s price=%s timestamp=%s replay=%s", symbol, price, timestamp, bool(getattr(tick, "replay", False)))


def _on_connected(*_args):
    global _CONNECTED, _LOOP_STATE
    with _LOCK:
        _CONNECTED = True
        _LOOP_STATE = "connected_waiting_for_tick"
    logger.info("[LIVE PRICE] LSE WebSocket connected")


def _on_authenticated(*_args):
    global _AUTHENTICATED, _LOOP_STATE
    with _LOCK:
        _AUTHENTICATED = True
        _LOOP_STATE = "authenticated_waiting_for_tick"
    logger.info("[LIVE PRICE] LSE WebSocket authenticated")


def _on_disconnected(*_args):
    global _CONNECTED, _AUTHENTICATED, _LOOP_STATE
    with _LOCK:
        _CONNECTED = False
        _AUTHENTICATED = False
        _LOOP_STATE = "disconnected_reconnecting" if _RUNNING else "stopped"
    logger.warning("[LIVE PRICE] LSE WebSocket disconnected")


def _on_error(error):
    global _LAST_ERROR, _LOOP_STATE
    with _LOCK:
        _LAST_ERROR = f"{type(error).__name__}: {error}"
        _LOOP_STATE = "error_reconnecting"
    logger.error("[LIVE PRICE] LSE WebSocket error: %s", error)


def _stream_loop():
    global _CLIENT, _LAST_ERROR, _CONNECTED, _AUTHENTICATED, _LOOP_STATE
    with _LOCK:
        _LOOP_STATE = "starting"
    logger.warning("[LIVE PRICE] Worker thread entered")

    while _RUNNING:
        key = _api_key()
        if not key:
            with _LOCK:
                _LAST_ERROR = "LSE_API_KEY is not configured"
                _CONNECTED = False
                _AUTHENTICATED = False
                _LOOP_STATE = "waiting_for_api_key"
            logger.error("[LIVE PRICE] LSE_API_KEY is not configured")
            time.sleep(10)
            continue

        client = None
        try:
            client = LSE(api_key=key)
            with _LOCK:
                _CLIENT = client
                _CONNECTED = False
                _AUTHENTICATED = False
                _LOOP_STATE = "connecting"
            logger.warning("[LIVE PRICE] Connecting LSE WebSocket: %s", ", ".join(SYMBOLS))

            # Official lse-data iterator streaming API.
            for tick in client.stream(list(SYMBOLS)):
                if not _RUNNING:
                    break
                _set_tick(tick)

            if _RUNNING:
                with _LOCK:
                    _LAST_ERROR = "LSE stream ended unexpectedly without an exception"
                    _LOOP_STATE = "stream_ended_reconnecting"
                logger.error("[LIVE PRICE] LSE stream ended unexpectedly; reconnecting")
        except Exception as exc:
            with _LOCK:
                _LAST_ERROR = f"{type(exc).__name__}: {exc}"
                _CONNECTED = False
                _AUTHENTICATED = False
                _LOOP_STATE = "exception_reconnecting"
            logger.exception("[LIVE PRICE] Stream failed")
        finally:
            with _LOCK:
                if _CLIENT is client:
                    _CLIENT = None
                _CONNECTED = False
                _AUTHENTICATED = False
            try:
                if client is not None:
                    client.disconnect()
            except Exception:
                pass
        if _RUNNING:
            time.sleep(5)

    with _LOCK:
        _LOOP_STATE = "stopped"
        _CONNECTED = False
        _AUTHENTICATED = False
    logger.warning("[LIVE PRICE] Worker thread exited")


def _watchdog_loop():
    global _THREAD, _RESTART_COUNT, _LAST_ERROR, _LOOP_STATE
    logger.warning("[LIVE PRICE] Watchdog started")
    while _RUNNING:
        time.sleep(10)
        if not _RUNNING:
            break
        with _LOCK:
            alive = bool(_THREAD and _THREAD.is_alive())
            if alive:
                continue
            _RESTART_COUNT += 1
            restart_no = _RESTART_COUNT
            _LAST_ERROR = _LAST_ERROR or "Live price worker stopped unexpectedly"
            _LOOP_STATE = "watchdog_restarting"
            _THREAD = threading.Thread(target=_stream_loop, name="lse-live-price", daemon=True)
            _THREAD.start()
        logger.error("[LIVE PRICE] Watchdog restarted worker; restart_count=%s", restart_no)
    logger.warning("[LIVE PRICE] Watchdog exited")


def start():
    global _RUNNING, _THREAD, _WATCHDOG_THREAD, _STARTED_AT, _LOOP_STATE
    with _LOCK:
        if _RUNNING and _THREAD and _THREAD.is_alive():
            return False
        _RUNNING = True
        _STARTED_AT = datetime.now(timezone.utc).isoformat()
        _LOOP_STATE = "starting"
        _THREAD = threading.Thread(target=_stream_loop, name="lse-live-price", daemon=True)
        _THREAD.start()
        if not _WATCHDOG_THREAD or not _WATCHDOG_THREAD.is_alive():
            _WATCHDOG_THREAD = threading.Thread(target=_watchdog_loop, name="lse-live-price-watchdog", daemon=True)
            _WATCHDOG_THREAD.start()
    logger.warning("[LIVE PRICE] Service started; symbols=%s; provider=LSE WebSocket", SYMBOLS)
    return True


def stop():
    global _RUNNING, _CLIENT, _CONNECTED, _AUTHENTICATED, _LOOP_STATE
    _RUNNING = False
    with _LOCK:
        client = _CLIENT
        _CLIENT = None
        _CONNECTED = False
        _AUTHENTICATED = False
        _LOOP_STATE = "stopping"
    try:
        if client is not None:
            client.disconnect()
    except Exception:
        pass


def _age_seconds(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def _decorate(value):
    value = dict(value)
    value["age_seconds"] = _age_seconds(value.get("received_at"))
    try:
        value["received_at_bangkok"] = datetime.fromisoformat(value["received_at"].replace("Z", "+00:00")).astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
    except (KeyError, TypeError, ValueError):
        value["received_at_bangkok"] = None
    return value


def status():
    with _LOCK:
        latest = {symbol: _decorate(value) for symbol, value in _LATEST.items()}
        error = _LAST_ERROR
        thread_alive = bool(_THREAD and _THREAD.is_alive())
        watchdog_alive = bool(_WATCHDOG_THREAD and _WATCHDOG_THREAD.is_alive())
        running = bool(_RUNNING and thread_alive)
        connected = bool(_CONNECTED)
        authenticated = bool(_AUTHENTICATED)
        ticks = _TICKS_RECEIVED
        last_tick_at = _LAST_TICK_AT
        started_at = _STARTED_AT
        loop_state = _LOOP_STATE
        restart_count = _RESTART_COUNT
    return {
        "running": running,
        "connected": connected,
        "authenticated": authenticated,
        "provider": "LSE",
        "transport": "WebSocket",
        "symbols": list(SYMBOLS),
        "latest": latest,
        "ticks_received": ticks,
        "last_tick_at": last_tick_at,
        "last_error": error,
        "api_key_configured": bool(_api_key()),
        "max_live_price_age_seconds": float(os.getenv("MAX_LIVE_PRICE_AGE_SECONDS", "30")),
        "worker_thread_alive": thread_alive,
        "watchdog_alive": watchdog_alive,
        "loop_state": loop_state,
        "restart_count": restart_count,
        "started_at": started_at,
    }


def get(symbol):
    symbol = str(symbol or "").strip().upper()
    market = {"BTC": "BTC/USD", "BTC/USD": "BTC/USD", "GOLD": "XAU/USD", "XAU/USD": "XAU/USD"}.get(symbol)
    if not market:
        return None
    with _LOCK:
        value = dict(_LATEST.get(market, {}))
    if value:
        return _decorate(value)
    return None
