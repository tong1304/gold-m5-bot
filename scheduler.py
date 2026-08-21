import os
import threading
import time
from datetime import datetime, timezone

import live_scanner

_RUNNING = False
_THREAD = None


def _interval_seconds():
    return max(30, int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "60")))


def _symbols():
    raw = os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC/USDT")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def run_scan_cycle():
    results = []
    for symbol in _symbols():
        try:
            results.append(live_scanner.scan_once(symbol))
        except Exception as exc:
            results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False})
    return results


def _loop():
    global _RUNNING
    while _RUNNING:
        run_scan_cycle()
        time.sleep(_interval_seconds())


def start():
    global _RUNNING, _THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():
        return False
    _RUNNING = True
    _THREAD = threading.Thread(target=_loop, name="m5-binance-signal-scanner", daemon=True)
    _THREAD.start()
    return True


def stop():
    global _RUNNING
    _RUNNING = False


def status():
    return {"running": bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds": _interval_seconds(),"symbols": _symbols(),"exchange":"Binance","timeframe":"M5","live_orders_allowed":False,"timestamp":datetime.now(timezone.utc).isoformat()}
