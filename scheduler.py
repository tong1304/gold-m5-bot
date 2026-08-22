import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import live_scanner

_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}
_LAST_PRICE_HEARTBEAT = None
BANGKOK = ZoneInfo("Asia/Bangkok")


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


def _send_price_heartbeat(now_bkk):
    global _LAST_PRICE_HEARTBEAT
    if now_bkk.minute % 10 != 5:
        return None
    slot = now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot == _LAST_PRICE_HEARTBEAT:
        return None

    lines = ["🧪 <b>ทดสอบระบบ Price Monitor</b>", "", f"🕐 เวลา: {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)", ""]
    feed_ok = True
    for symbol in _symbols():
        try:
            price, market_symbol = live_scanner.BINANCE.fetch_price(symbol)
            label = f"{symbol} (Binance: {market_symbol})" if market_symbol != symbol else symbol
            lines.append(f"📊 {label}: <b>{price:,.8f}</b>")
        except Exception as exc:
            feed_ok = False
            lines.append(f"❌ {symbol}: ดึงราคาไม่ได้")
            lines.append(f"   └ {type(exc).__name__}: {str(exc)}")

    lines.extend([
        "",
        "✅ Scheduler ทำงาน",
        "✅ Binance Price Feed" if feed_ok else "⚠️ Binance Price Feed มีข้อผิดพลาด",
        "✅ Telegram Monitor",
        "",
        "ℹ️ ข้อความนี้เป็นการทดสอบระบบ",
        "⛔ ไม่ใช่สัญญาณ BUY/SELL",
    ])
    result = live_scanner.engine.send_telegram("\n".join(lines))
    sent = bool(isinstance(result, dict) and result.get("success"))
    if sent:
        _LAST_PRICE_HEARTBEAT = slot
    return {"sent": sent, "slot": slot, "telegram_result": result, "timezone": "Asia/Bangkok"}


def run_scan_cycle():
    now_bkk = datetime.now(timezone.utc).astimezone(BANGKOK)
    heartbeat = _send_price_heartbeat(now_bkk)
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
    if heartbeat is not None:
        results.append({"status":"price_heartbeat","heartbeat":heartbeat,"timezone":"Asia/Bangkok"})
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
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"exchange":"Binance","timeframe":"M5 trigger + H1/M15 confirmation","trigger":"ทุกครั้งที่มีแท่ง M5 ใหม่ปิด","price_heartbeat":"นาทีลงท้ายด้วย 5 ตามเวลา Asia/Bangkok","last_closed_candle":dict(_LAST_CLOSED_CANDLE),"live_orders_allowed":False,"timestamp":datetime.now(timezone.utc).isoformat()}
