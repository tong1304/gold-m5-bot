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
_STATE_SINCE = None
_LOOP_STATE = "stopped"
_RESTART_COUNT = 0

# A websocket can stay inside connect() without raising an exception.  That
# previously made the worker look alive while no connection/tick ever arrived.
# Force a reconnect when the connection state does not advance in time.
CONNECT_TIMEOUT_SECONDS = max(10.0, float(os.getenv("LIVE_PRICE_CONNECT_TIMEOUT_SECONDS", "30")))
AUTH_TICK_TIMEOUT_SECONDS = max(15.0, float(os.getenv("LIVE_PRICE_AUTH_TICK_TIMEOUT_SECONDS", "45")))


def _api_key():
    return os.getenv("LSE_API_KEY", "").strip()


def _max_age():
    try:
        return max(5.0, float(os.getenv("MAX_LIVE_PRICE_AGE_SECONDS", "30")))
    except (TypeError, ValueError):
        return 30.0


def _set_state(state):
    global _LOOP_STATE, _STATE_SINCE
    _LOOP_STATE = state
    _STATE_SINCE = time.monotonic()


def _state_age():
    if _STATE_SINCE is None:
        return None
    return max(0.0, time.monotonic() - _STATE_SINCE)


def _set_tick(tick):
    global _LAST_ERROR, _TICKS_RECEIVED, _LAST_TICK_AT, _CONNECTED
    symbol = str(getattr(tick, "symbol", "") or "").upper()
    if symbol not in SYMBOLS:
        logger.warning("[LIVE PRICE] Ignoring unsupported tick symbol=%s", symbol)
        return
    try:
        price = float(getattr(tick, "price", None))
    except (TypeError, ValueError):
        return
    if price <= 0:
        return
    timestamp = getattr(tick, "timestamp", None) or datetime.now(timezone.utc).isoformat()
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
        _set_state("receiving_ticks")
    logger.info("[LIVE PRICE] TICK %s price=%s timestamp=%s replay=%s", symbol, price, timestamp, bool(getattr(tick, "replay", False)))


def _on_connected(*_args):
    global _CONNECTED
    with _LOCK:
        _CONNECTED = True
        _set_state("connected_waiting_for_authentication")
    logger.info("[LIVE PRICE] CONNECTED")


def _on_authenticated(*_args):
    global _AUTHENTICATED, _CONNECTED
    with _LOCK:
        _AUTHENTICATED = True
        _CONNECTED = True
        _set_state("authenticated_waiting_for_tick")
    logger.info("[LIVE PRICE] AUTHENTICATED; subscriptions=%s", ", ".join(SYMBOLS))


def _on_disconnected(*_args):
    global _CONNECTED, _AUTHENTICATED
    with _LOCK:
        _CONNECTED = False
        _AUTHENTICATED = False
        _set_state("disconnected_reconnecting" if _RUNNING else "stopped")
    logger.warning("[LIVE PRICE] DISCONNECTED")


def _on_error(error):
    global _LAST_ERROR
    with _LOCK:
        _LAST_ERROR = f"{type(error).__name__}: {error}"
        _set_state("error_reconnecting")
    logger.error("[LIVE PRICE] ERROR: %s", error)


def _stream_loop():
    global _CLIENT, _LAST_ERROR, _CONNECTED, _AUTHENTICATED
    with _LOCK:
        _set_state("starting")
    logger.warning("[LIVE PRICE] Worker thread entered")

    while _RUNNING:
        key = _api_key()
        if not key:
            with _LOCK:
                _LAST_ERROR = "LSE_API_KEY is not configured"
                _CONNECTED = False
                _AUTHENTICATED = False
                _set_state("waiting_for_api_key")
            logger.error("[LIVE PRICE] LSE_API_KEY is not configured")
            time.sleep(10)
            continue

        client = None
        try:
            client = LSE(api_key=key)
            client.on("tick", _set_tick)
            client.on("connected", _on_connected)
            client.on("authenticated", _on_authenticated)
            client.on("disconnected", _on_disconnected)
            client.on("error", _on_error)
            with _LOCK:
                _CLIENT = client
                _CONNECTED = False
                _AUTHENTICATED = False
                _set_state("connecting")
            logger.warning("[LIVE PRICE] Connecting LSE WebSocket: %s", ", ".join(SYMBOLS))
            # lse-data 0.14 supports connect(symbols=[...]) and emits
            # connected/authenticated/tick events on this same client.
            client.connect(symbols=list(SYMBOLS))
            if _RUNNING:
                with _LOCK:
                    _LAST_ERROR = _LAST_ERROR or "LSE connect() returned while service was running"
                    _set_state("connect_returned_reconnecting")
                logger.error("[LIVE PRICE] connect() returned unexpectedly; reconnecting")
        except Exception as exc:
            with _LOCK:
                _LAST_ERROR = f"{type(exc).__name__}: {exc}"
                _CONNECTED = False
                _AUTHENTICATED = False
                _set_state("exception_reconnecting")
            logger.exception("[LIVE PRICE] WebSocket connection failed")
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
        _set_state("stopped")
        _CONNECTED = False
        _AUTHENTICATED = False
    logger.warning("[LIVE PRICE] Worker thread exited")


def _watchdog_loop():
    global _THREAD, _RESTART_COUNT, _LAST_ERROR, _CONNECTED, _AUTHENTICATED, _CLIENT
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

            # The critical fix: connect() can block while the thread remains
            # alive.  If no connected/authenticated/tick progress occurs within
            # the timeout, forcibly disconnect and recreate the worker.
            if not alive:
                restart = True
                reason = "worker_not_alive"
            elif _LOOP_STATE == "connecting" and state_age is not None and state_age > CONNECT_TIMEOUT_SECONDS:
                restart = True
                reason = f"connect_timeout_{state_age:.1f}s"
            elif _LOOP_STATE in ("connected_waiting_for_authentication", "authenticated_waiting_for_tick") and state_age is not None and state_age > AUTH_TICK_TIMEOUT_SECONDS:
                restart = True
                reason = f"tick_timeout_{state_age:.1f}s"
            elif _TICKS_RECEIVED > 0 and last_age is not None and last_age > _max_age():
                restart = True
                reason = f"stale_ticks_{last_age:.1f}s"

            if restart:
                _RESTART_COUNT += 1
                restart_no = _RESTART_COUNT
                _LAST_ERROR = f"Live price watchdog restart: {reason}"
                _CONNECTED = False
                _AUTHENTICATED = False
                _set_state("watchdog_restarting")
                client = _CLIENT
                _CLIENT = None
                if not alive:
                    _THREAD = threading.Thread(target=_stream_loop, name="lse-live-price", daemon=True)
                    _THREAD.start()
        if restart:
            try:
                if client is not None:
                    client.disconnect()
            except Exception:
                pass
            logger.warning("[LIVE PRICE] Watchdog restart=%s reason=%s", restart_no, reason)
    logger.warning("[LIVE PRICE] Watchdog exited")


def start():
    global _RUNNING, _THREAD, _WATCHDOG_THREAD, _STARTED_AT
    with _LOCK:
        if _RUNNING and _THREAD and _THREAD.is_alive():
            return False
        _RUNNING = True
        _STARTED_AT = datetime.now(timezone.utc).isoformat()
        _set_state("starting")
        _THREAD = threading.Thread(target=_stream_loop, name="lse-live-price", daemon=True)
        _THREAD.start()
        if not _WATCHDOG_THREAD or not _WATCHDOG_THREAD.is_alive():
            _WATCHDOG_THREAD = threading.Thread(target=_watchdog_loop, name="lse-live-price-watchdog", daemon=True)
            _WATCHDOG_THREAD.start()
    logger.warning("[LIVE PRICE] Service started; symbols=%s; provider=LSE WebSocket", SYMBOLS)
    return True


def stop():
    global _RUNNING, _CLIENT, _CONNECTED, _AUTHENTICATED
    _RUNNING = False
    with _LOCK:
        client = _CLIENT
        _CLIENT = None
        _CONNECTED = False
        _AUTHENTICATED = False
        _set_state("stopping")
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
        last_tick_at = _LAST_TICK_AT
        last_age = _age_seconds(last_tick_at) if last_tick_at else None
        state_age = _state_age()
        fresh = last_age is None or last_age <= _max_age()
        connected = bool(running and _CONNECTED and fresh)
        authenticated = bool(running and _AUTHENTICATED and fresh)
        ticks = _TICKS_RECEIVED
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
        "max_live_price_age_seconds": _max_age(),
        "worker_thread_alive": thread_alive,
        "watchdog_alive": watchdog_alive,
        "loop_state": loop_state,
        "state_age_seconds": state_age,
        "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
        "auth_tick_timeout_seconds": AUTH_TICK_TIMEOUT_SECONDS,
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
