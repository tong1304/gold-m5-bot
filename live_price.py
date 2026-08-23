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
_RUNNING = False
_CLIENT = None
_LATEST = {}
_LAST_ERROR = None
_CONNECTED = False
_AUTHENTICATED = False
_TICKS_RECEIVED = 0
_LAST_TICK_AT = None


def _api_key():
    return os.getenv("LSE_API_KEY", "").strip()


def _set_tick(tick):
    global _LAST_ERROR, _TICKS_RECEIVED, _LAST_TICK_AT, _CONNECTED
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
    logger.info("[LIVE PRICE] %s price=%s timestamp=%s replay=%s", symbol, price, timestamp, bool(getattr(tick, "replay", False)))


def _on_connected(*_args):
    global _CONNECTED
    with _LOCK:
        _CONNECTED = True
    logger.info("[LIVE PRICE] LSE WebSocket connected")


def _on_authenticated(*_args):
    global _AUTHENTICATED
    with _LOCK:
        _AUTHENTICATED = True
    logger.info("[LIVE PRICE] LSE WebSocket authenticated")


def _on_disconnected(*_args):
    global _CONNECTED, _AUTHENTICATED
    with _LOCK:
        _CONNECTED = False
        _AUTHENTICATED = False
    logger.warning("[LIVE PRICE] LSE WebSocket disconnected")


def _on_error(error):
    global _LAST_ERROR
    with _LOCK:
        _LAST_ERROR = f"{type(error).__name__}: {error}"
    logger.error("[LIVE PRICE] LSE WebSocket error: %s", error)


def _stream_loop():
    global _CLIENT, _LAST_ERROR, _CONNECTED, _AUTHENTICATED
    while _RUNNING:
        key = _api_key()
        if not key:
            with _LOCK:
                _LAST_ERROR = "LSE_API_KEY is not configured"
                _CONNECTED = False
                _AUTHENTICATED = False
            logger.error("[LIVE PRICE] LSE_API_KEY is not configured")
            time.sleep(30)
            continue

        client = None
        try:
            # Use the SDK's documented iterator streaming API. It keeps the
            # WebSocket receive loop inside the SDK and is less error-prone
            # than manually managing callback/connect lifecycle.
            client = LSE(api_key=key)
            with _LOCK:
                _CLIENT = client
                _CONNECTED = False
                _AUTHENTICATED = False
            logger.info("[LIVE PRICE] Connecting LSE WebSocket: %s", ", ".join(SYMBOLS))
            for tick in client.stream(list(SYMBOLS)):
                if not _RUNNING:
                    break
                _set_tick(tick)
        except Exception as exc:
            with _LOCK:
                _LAST_ERROR = f"{type(exc).__name__}: {exc}"
                _CONNECTED = False
                _AUTHENTICATED = False
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


def start():
    global _RUNNING, _THREAD
    with _LOCK:
        if _RUNNING and _THREAD and _THREAD.is_alive():
            return False
        _RUNNING = True
        _THREAD = threading.Thread(target=_stream_loop, name="lse-live-price", daemon=True)
        _THREAD.start()
    logger.info("[LIVE PRICE] Service started; symbols=%s; provider=LSE WebSocket", SYMBOLS)
    return True


def stop():
    global _RUNNING, _CLIENT, _CONNECTED, _AUTHENTICATED
    _RUNNING = False
    with _LOCK:
        client = _CLIENT
        _CLIENT = None
        _CONNECTED = False
        _AUTHENTICATED = False
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
        running = bool(_RUNNING and thread_alive)
        connected = bool(_CONNECTED)
        authenticated = bool(_AUTHENTICATED)
        ticks = _TICKS_RECEIVED
        last_tick_at = _LAST_TICK_AT
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
