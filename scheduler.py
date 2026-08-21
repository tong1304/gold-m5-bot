import os
import threading
import time
from datetime import datetime, timezone

import live_scanner

_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}


def _interval_seconds():
    return max(10, int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "15")))


def _symbols():
    raw = os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT,XAU/USDT")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _get_closed_candle_key(symbol):
    df = live_scanner.BINANCE.fetch_candles(symbol, "5m", 10)
    df = live_scanner.BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=5)
    if df.empty:
        raise RuntimeError(f"ยังไม่มีแท่ง M5 ที่ปิดแล้วสำหรับ {symbol}")
    row = df.iloc[-1]
    return str(row.get("datetime", row.name))


def run_scan_cycle():
    results = []
    for symbol in _symbols():
        try:
            if symbol not in live_scanner.SUPPORTED_SYMBOLS:
                raise RuntimeError(f"ไม่รองรับสินทรัพย์: {symbol}")
            closed_key = _get_closed_candle_key(symbol)
            previous = _LAST_CLOSED_CANDLE.get(symbol)
            if previous == closed_key:
                results.append({"status":"waiting_new_candle","symbol":symbol,"timeframe":"M5","closed_candle":closed_key,"message":"ยังไม่มีแท่ง M5 ใหม่ปิด ระบบรอแท่งถัดไป","telegram_alert_sent":False,"live_orders_allowed":False})
                continue
            result = live_scanner.scan_once(symbol)
            _LAST_CLOSED_CANDLE[symbol] = closed_key
            result["trigger"] = "NEW_CLOSED_M5_CANDLE"
            results.append(result)
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
    if _RUNNING and _THREAD and _THREAD.is_alive(): return False
    _RUNNING = True
    _THREAD = threading.Thread(target=_loop, name="m5-multi-asset-scanner", daemon=True)
    _THREAD.start()
    return True


def stop():
    global _RUNNING
    _RUNNING = False


def status():
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"exchange":"Binance","timeframe":"M5 trigger + H1/M15 confirmation","trigger":"ทุกครั้งที่มีแท่ง M5 ใหม่ปิด","last_closed_candle":dict(_LAST_CLOSED_CANDLE),"live_orders_allowed":False,"timestamp":datetime.now(timezone.utc).isoformat()}
