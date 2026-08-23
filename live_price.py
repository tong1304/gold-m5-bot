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


def _api_key():
    return os.getenv("LSE_API_KEY", "").strip()


def _set_tick(tick):
    global _LAST_ERROR
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
    with _LOCK:
        _LATEST[symbol] = {
            "symbol": symbol,
            "price": price,
            "bid": getattr(tick, "bid", None),
            "ask": getattr(tick, "ask", None),
            "volume": getattr(tick, "volume", None),
            "timestamp": str(timestamp),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "replay": bool(getattr(tick, "replay", False)),
        }
        _LAST_ERROR = None
    logger.info("[LIVE PRICE] %s price=%s timestamp=%s", symbol, price, timestamp)


def _on_connected(*_args):
    logger.info("[LIVE PRICE] LSE WebSocket connected")


def _on_authenticated(*_args):
    logger.info("[LIVE PRICE] LSE WebSocket authenticated")


def _on_disconnected(*_args):
    logger.warning("[LIVE PRICE] LSE WebSocket disconnected")


def _on_error(error):
    global _LAST_ERROR
    with _LOCK:
        _LAST_ERROR = f"{type(error).__name__}: {error}"
    logger.error("[LIVE PRICE] LSE WebSocket error: %s", error)


def _stream_loop():
    global _CLIENT, _LAST_ERROR
    while _RUNNING:
        key = _api_key()
        if not key:
            with _LOCK:
                _LAST_ERROR = "LSE_API_KEY is not configured"
            logger.error("[LIVE PRICE] LSE_API_KEY is not configured")
            time.sleep(30)
            continue
        client = None
        try:
            client = LSE(api_key=key)
            with _LOCK:
                _CLIENT = client
            client.on("tick", _set_tick)
            client.on("connected", _on_connected)
            client.on("authenticated", _on_authenticated)
            client.on("disconnected", _on_disconnected)
            client.on("error", _on_error)
            logger.info("[LIVE PRICE] Starting LSE stream: %s", ", ".join(SYMBOLS))
            client.connect(list(SYMBOLS))
        except Exception as exc:
            with _LOCK:
                _LAST_ERROR = f"{type(exc).__name__}: {exc}"
            logger.exception("[LIVE PRICE] Stream failed")
        finally:
            with _LOCK:
                if _CLIENT is client:
                    _CLIENT = None
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
    global _RUNNING, _CLIENT
    _RUNNING = False
    with _LOCK:
        client = _CLIENT
        _CLIENT = None
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


def status():
    with _LOCK:
        latest = {symbol: dict(value) for symbol, value in _LATEST.items()}
        error = _LAST_ERROR
        thread_alive = bool(_THREAD and _THREAD.is_alive())
    for value in latest.values():
        value["age_seconds"] = _age_seconds(value.get("received_at"))
        value["received_at_bangkok"] = datetime.fromisoformat(value["received_at"].replace("Z", "+00:00")).astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
    return {
        "running": bool(_RUNNING and thread_alive),
        "provider": "LSE",
        "transport": "WebSocket",
        "symbols": list(SYMBOLS),
        "latest": latest,
        "last_error": error,
    }


def get(symbol):
    symbol = str(symbol or "").strip().upper()
    market = {"BTC": "BTC/USD", "BTC/USD": "BTC/USD", "GOLD": "XAU/USD", "XAU/USD": "XAU/USD"}.get(symbol)
    if not market:
        return None
    with _LOCK:
        value = dict(_LATEST.get(market, {}))
    if value:
        value["age_seconds"] = _age_seconds(value.get("received_at"))
    return value or None
