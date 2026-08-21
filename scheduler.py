import os
import threading
import time
from datetime import datetime, timezone

import live_scanner

_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}


def _interval_seconds():
    # Polling only checks whether a NEW 5-minute candle has closed.
    # 15 seconds gives enough margin for the exchange candle to settle.
    return max(10, int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "15")))


def _symbols():
    raw = os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC/USDT")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _get_closed_candle_key(symbol):
    """Fetch enough data to identify the latest CLOSED M5 candle.

    The scanner itself fetches the full history again when a new candle is
    detected. This lightweight check prevents repeatedly re-analyzing the same
    candle every polling interval.
    """
    from binance_data import BinanceMarketData

    market = live_scanner.BINANCE
    df = market.fetch_candles(symbol, "5m", 10)
    df = market.remove_incomplete_last_candle(df, timeframe_minutes=5)
    if df.empty:
        raise RuntimeError("ยังไม่มีแท่ง M5 ที่ปิดแล้ว")
    row = df.iloc[-1]
    return str(row.get("datetime", row.name))


def run_scan_cycle():
    results = []
    for symbol in _symbols():
        try:
            closed_key = _get_closed_candle_key(symbol)
            previous = _LAST_CLOSED_CANDLE.get(symbol)
            if previous == closed_key:
                results.append({
                    "status": "waiting_new_candle",
                    "symbol": symbol,
                    "timeframe": "M5",
                    "closed_candle": closed_key,
                    "message": "ยังไม่มีแท่ง M5 ใหม่ปิด ระบบรอแท่งถัดไป",
                    "telegram_alert_sent": False,
                    "live_orders_allowed": False,
                })
                continue

            # Mark only after the scan starts. A failed scan can therefore be
            # retried on the next poll rather than silently losing the signal.
            result = live_scanner.scan_once(symbol)
            _LAST_CLOSED_CANDLE[symbol] = closed_key
            result["trigger"] = "NEW_CLOSED_M5_CANDLE"
            results.append(result)
        except Exception as exc:
            results.append({
                "status": "scan_error",
                "symbol": symbol,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "telegram_alert_sent": False,
                "live_orders_allowed": False,
            })
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
    _THREAD = threading.Thread(target=_loop, name="m5-binance-candle-scanner", daemon=True)
    _THREAD.start()
    return True


def stop():
    global _RUNNING
    _RUNNING = False


def status():
    return {
        "running": bool(_RUNNING and _THREAD and _THREAD.is_alive()),
        "interval_seconds": _interval_seconds(),
        "symbols": _symbols(),
        "exchange": "Binance",
        "timeframe": "M5",
        "trigger": "ทุกครั้งที่มีแท่ง M5 ใหม่ปิด",
        "last_closed_candle": dict(_LAST_CLOSED_CANDLE),
        "live_orders_allowed": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
