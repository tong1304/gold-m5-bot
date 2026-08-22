import os
import threading
import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import live_scanner

logger = logging.getLogger("signal_scheduler")

_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}
_LAST_PRICE_HEARTBEAT = None
BANGKOK = ZoneInfo("Asia/Bangkok")

DISPLAY_SYMBOLS = ("BTC", "ETH", "SOL", "GOLD")
DISPLAY_TO_MARKET = {"BTC": "BTC/USDT", "ETH": "ETH/USDT", "SOL": "SOL/USDT", "GOLD": "XAU/USDT"}
LEGACY_SYMBOLS = {"BTC/USDT": "BTC", "ETH/USDT": "ETH", "SOL/USDT": "SOL", "XAU/USDT": "GOLD"}


def _interval_seconds():
    return max(10, int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "15")))


def _symbols():
    raw = os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC,ETH,SOL,GOLD")
    result = []
    for value in raw.split(","):
        symbol = LEGACY_SYMBOLS.get(value.strip().upper(), value.strip().upper())
        if symbol in DISPLAY_SYMBOLS and symbol not in result:
            result.append(symbol)
    return result


def _notify_scheduler_error(exc, context="Scheduler"):
    """Send one human-readable Thai error alert without hiding the original exception."""
    try:
        now_bkk = datetime.now(timezone.utc).astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
        message = (
            "❌ <b>ระบบ Scheduler ขัดข้อง</b>\n\n"
            f"🕐 เวลา: {now_bkk} (กรุงเทพฯ)\n"
            f"📍 จุดที่เกิดปัญหา: {context}\n"
            f"🔴 ประเภทข้อผิดพลาด: {type(exc).__name__}\n"
            f"📝 รายละเอียด: {str(exc)}\n\n"
            "🛑 ระบบสแกนสัญญาณอัตโนมัติอาจหยุดทำงาน\n"
            "🖐️ ไม่มีการเปิดออเดอร์อัตโนมัติ"
        )
        result = live_scanner.engine.send_telegram(message)
        logger.warning("Scheduler error Telegram notification result: %s", result)
        return result
    except Exception as telegram_exc:
        logger.exception("Scheduler error Telegram notification failed: %s", telegram_exc)
        return None


def _get_closed_candle_key(symbol):
    market_symbol = DISPLAY_TO_MARKET[symbol]
    df = live_scanner.BINANCE.fetch_candles(market_symbol, "5m", 10)
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
            price, _ = live_scanner.BINANCE.fetch_price(DISPLAY_TO_MARKET[symbol])
            lines.append(f"📊 {symbol}: <b>{price:,.8f}</b>")
        except Exception as exc:
            feed_ok = False
            logger.exception("Price monitor failed for %s", symbol)
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
    else:
        logger.warning("Price monitor Telegram send failed: %s", result)
    return {"sent": sent, "slot": slot, "telegram_result": result, "timezone": "Asia/Bangkok"}


def run_scan_cycle():
    now_bkk = datetime.now(timezone.utc).astimezone(BANGKOK)
    logger.info("Scheduler scan cycle started: %s", now_bkk.strftime("%d/%m/%Y %H:%M:%S"))
    heartbeat = _send_price_heartbeat(now_bkk)
    results = []
    symbols = _symbols()
    if not symbols:
        raise RuntimeError("ไม่มีสินทรัพย์ที่เปิดใช้งานใน LIVE_SIGNAL_SYMBOLS")

    for symbol in symbols:
        try:
            if symbol not in live_scanner.SUPPORTED_SYMBOLS:
                raise RuntimeError(f"ไม่รองรับสินทรัพย์: {symbol}")
            closed_key = _get_closed_candle_key(symbol)
            previous = _LAST_CLOSED_CANDLE.get(symbol)
            if previous == closed_key:
                results.append({"status":"waiting_new_candle","symbol":symbol,"timeframe":"M5","closed_candle":closed_key,"message":"ยังไม่มีแท่ง M5 ใหม่ปิด ระบบรอแท่งถัดไป","telegram_alert_sent":False,"live_orders_allowed":False})
                continue
            logger.info("New closed M5 candle detected: %s %s", symbol, closed_key)
            result = live_scanner.scan_once(symbol)
            _LAST_CLOSED_CANDLE[symbol] = closed_key
            logger.info("Scan result: symbol=%s candle=%s signal=%s telegram_alert_sent=%s", symbol, closed_key, result.get("signal"), result.get("telegram_alert_sent"))
            result["trigger"] = "NEW_CLOSED_M5_CANDLE"
            results.append(result)
        except Exception as exc:
            logger.exception("Scan failed for %s", symbol)
            _notify_scheduler_error(exc, context=f"การสแกน {symbol}")
            results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False})
    if heartbeat is not None:
        results.append({"status":"price_heartbeat","heartbeat":heartbeat,"timezone":"Asia/Bangkok"})
    logger.info("Scheduler scan cycle finished: %d symbol(s)", len(symbols))
    return results


def _loop():
    global _RUNNING
    logger.warning("M5 Multi-Asset Signal Scheduler thread started; interval=%ss; symbols=%s", _interval_seconds(), _symbols())
    while _RUNNING:
        try:
            run_scan_cycle()
        except Exception as exc:
            logger.exception("Fatal scheduler cycle error")
            _notify_scheduler_error(exc, context="รอบการทำงานหลักของ Scheduler")
            # Keep the scheduler alive after a cycle-level failure.
        time.sleep(_interval_seconds())
    logger.warning("M5 Multi-Asset Signal Scheduler thread stopped")


def start():
    global _RUNNING, _THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():
        logger.info("Signal Scheduler already running; thread=%s", _THREAD.name)
        return False
    _RUNNING = True
    _THREAD = threading.Thread(target=_loop, name="m5-multi-asset-scanner", daemon=True)
    _THREAD.start()
    logger.warning("Signal Scheduler started successfully; thread=%s", _THREAD.name)
    return True


def stop():
    global _RUNNING
    _RUNNING = False
    logger.warning("Signal Scheduler stop requested")


def status():
    alive = bool(_RUNNING and _THREAD and _THREAD.is_alive())
    return {"running":alive,"interval_seconds":_interval_seconds(),"symbols":_symbols(),"symbol_mapping":DISPLAY_TO_MARKET,"exchange":"Binance","timeframe":"M5 trigger + H1/M15 confirmation","trigger":"ทุกครั้งที่มีแท่ง M5 ใหม่ปิด","price_heartbeat":"นาทีลงท้ายด้วย 5 ตามเวลา Asia/Bangkok","last_closed_candle":dict(_LAST_CLOSED_CANDLE),"thread_name":_THREAD.name if _THREAD else None,"live_orders_allowed":False,"timestamp":datetime.now(timezone.utc).isoformat()}
