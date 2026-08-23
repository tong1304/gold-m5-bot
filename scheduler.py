import logging
import os
import threading
import time
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

logger = logging.getLogger("signal_scheduler")
_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}
_LAST_TEST_SLOT = None
BANGKOK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc
DISPLAY_SYMBOLS = ("BTC", "GOLD")
DISPLAY_TO_MARKET = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}
LEGACY_SYMBOLS = {"BTC/USDT": "BTC", "XAU/USDT": "GOLD"}

GOLD_OPEN_SUNDAY_UTC = os.getenv("GOLD_OPEN_SUNDAY_UTC", "23:00")
GOLD_CLOSE_FRIDAY_UTC = os.getenv("GOLD_CLOSE_FRIDAY_UTC", "22:00")
GOLD_DAILY_BREAK_START_UTC = os.getenv("GOLD_DAILY_BREAK_START_UTC", "22:00")
GOLD_DAILY_BREAK_END_UTC = os.getenv("GOLD_DAILY_BREAK_END_UTC", "23:00")


def _interval_seconds():
    # One cycle per 5-minute candle keeps the free Twelve Data allowance safe.
    # A configured value may increase the interval, but never decrease it.
    try:
        configured = int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "300"))
    except ValueError:
        configured = 300
    return max(300, configured)


def _symbols():
    raw = os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC,GOLD")
    result = []
    for value in raw.split(","):
        symbol = LEGACY_SYMBOLS.get(value.strip().upper(), value.strip().upper())
        if symbol in DISPLAY_SYMBOLS and symbol not in result:
            result.append(symbol)
    return result


def _parse_utc_time(value, fallback):
    try:
        hour, minute = str(value).strip().split(":", 1)
        return dt_time(int(hour), int(minute))
    except (TypeError, ValueError):
        return fallback


def _asset_market_status(symbol, now_utc=None):
    now_utc = now_utc or datetime.now(UTC)
    symbol = (symbol or "").upper()
    if symbol == "BTC":
        return True, "OPEN_24_7"
    if symbol != "GOLD":
        return False, "UNKNOWN_MARKET_SESSION"
    sunday_open = _parse_utc_time(GOLD_OPEN_SUNDAY_UTC, dt_time(23, 0))
    friday_close = _parse_utc_time(GOLD_CLOSE_FRIDAY_UTC, dt_time(22, 0))
    break_start = _parse_utc_time(GOLD_DAILY_BREAK_START_UTC, dt_time(22, 0))
    break_end = _parse_utc_time(GOLD_DAILY_BREAK_END_UTC, dt_time(23, 0))
    weekday, current = now_utc.weekday(), now_utc.time()
    if weekday == 5:
        return False, "WEEKEND_CLOSED"
    if weekday == 6:
        return (current >= sunday_open, "OPEN" if current >= sunday_open else "SUNDAY_CLOSED")
    if weekday == 4:
        return (current < friday_close, "OPEN" if current < friday_close else "FRIDAY_CLOSED")
    if break_start < break_end and break_start <= current < break_end:
        return False, "DAILY_BREAK"
    return True, "OPEN"


def _scanner():
    import live_scanner
    return live_scanner


def _notify_error(exc, context):
    message = (
        "❌ <b>ระบบ Scheduler ขัดข้อง</b>\n\n"
        f"🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (กรุงเทพฯ)\n"
        f"📍 {context}\n🔴 {type(exc).__name__}\n📝 {exc}\n\n"
        "🛑 ไม่มีการเปิดออเดอร์อัตโนมัติ"
    )
    try:
        return _scanner().engine.send_telegram(message)
    except Exception:
        try:
            import engine_v5 as engine
            return engine.send_telegram(message)
        except Exception:
            logger.exception("Scheduler Telegram error notification failed")
            return None


def _closed_frame(symbol):
    scanner = _scanner()
    market = DISPLAY_TO_MARKET[symbol]
    frame = scanner.BINANCE.fetch_candles(market, "5m", 10)
    frame = scanner.BINANCE.remove_incomplete_last_candle(frame, timeframe_minutes=5)
    if frame.empty:
        raise RuntimeError(f"ยังไม่มีแท่ง M5 ที่ปิดแล้วสำหรับ {symbol}")
    return frame


def _system_test(now_bkk):
    global _LAST_TEST_SLOT
    if now_bkk.minute % 5 != 0:
        return None
    slot = now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot == _LAST_TEST_SLOT:
        return None

    lines = [
        "🧪 <b>ทดสอบระบบทุก 5 นาที</b>",
        "",
        f"🕐 เวลา: {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)",
        "",
    ]
    scanner = None
    feed_ok = True
    frames = {}
    try:
        scanner = _scanner()
        for symbol in _symbols():
            market_open, session = _asset_market_status(symbol, now_bkk.astimezone(UTC))
            if not market_open:
                lines.append(f"⏸ {symbol}: ตลาดปิด ({session})")
                continue
            frame = _closed_frame(symbol)
            frames[symbol] = frame
            price = float(frame.iloc[-1]["close"])
            candle = str(frame.iloc[-1]["datetime"])
            lines.append(f"📊 {symbol}: <b>{price:,.8f}</b> | M5 ปิด: {candle}")
    except Exception as exc:
        feed_ok = False
        logger.exception("Twelve Data 5-minute system test failed")
        lines.append(f"❌ Twelve Data: {type(exc).__name__}: {exc}")

    lines.extend([
        "",
        "✅ Scheduler ทำงาน",
        "✅ Twelve Data Price Feed" if feed_ok else "⚠️ Twelve Data Price Feed มีข้อผิดพลาด",
        "✅ Telegram Monitor",
        "",
        "ℹ️ การทดสอบนี้ไม่ใช่สัญญาณ BUY/SELL",
    ])
    try:
        result = (scanner.engine.send_telegram("\n".join(lines)) if scanner is not None
                  else __import__("engine_v5").send_telegram("\n".join(lines)))
        sent = bool(isinstance(result, dict) and result.get("success"))
        if sent:
            _LAST_TEST_SLOT = slot
        return {"sent": sent, "slot": slot, "telegram_result": result, "timezone": "Asia/Bangkok"}
    except Exception as exc:
        logger.exception("5-minute system test Telegram send failed")
        return {"sent": False, "slot": slot, "error_type": type(exc).__name__, "error": str(exc)}


def run_scan_cycle():
    now_bkk = datetime.now(UTC).astimezone(BANGKOK)
    now_utc = now_bkk.astimezone(UTC)
    symbols = _symbols()
    logger.warning(
        "[HEARTBEAT] Scheduler cycle START: %s | symbols=%s | interval=%ss | test_slots=every_5_minutes Asia/Bangkok",
        now_bkk.strftime("%d/%m/%Y %H:%M:%S"), symbols, _interval_seconds(),
    )
    heartbeat = _system_test(now_bkk)
    results = []
    try:
        scanner = _scanner()
    except Exception as exc:
        logger.warning("Twelve Data scanner unavailable: %s", exc)
        _notify_error(exc, "เริ่มต้น market-data scanner")
        return [{"status": "twelve_data_unavailable", "error_type": type(exc).__name__, "message": str(exc)}]

    for symbol in symbols:
        try:
            if symbol not in scanner.SUPPORTED_SYMBOLS:
                raise RuntimeError(f"ไม่รองรับสินทรัพย์: {symbol}")
            market_open, session = _asset_market_status(symbol, now_utc)
            if not market_open:
                results.append({"status": "market_closed", "symbol": symbol, "session": session, "live_orders_allowed": False})
                continue
            frame = _closed_frame(symbol)
            closed_key = str(frame.iloc[-1]["datetime"])
            if _LAST_CLOSED_CANDLE.get(symbol) == closed_key:
                results.append({"status": "waiting_new_candle", "symbol": symbol, "timeframe": "M5", "closed_candle": closed_key, "live_orders_allowed": False})
                continue
            result = scanner.scan_once(symbol)
            valid_signal = bool(isinstance(result, dict) and result.get("valid"))
            telegram_sent = bool(isinstance(result, dict) and result.get("telegram_alert_sent"))
            if not (valid_signal and not telegram_sent):
                _LAST_CLOSED_CANDLE[symbol] = closed_key
            result["trigger"] = "NEW_CLOSED_M5_CANDLE"
            result["candle_consumed"] = not (valid_signal and not telegram_sent)
            result["market_session"] = session
            results.append(result)
        except Exception as exc:
            logger.exception("[%s] Scan failed", symbol)
            _notify_error(exc, f"การสแกน {symbol}")
            results.append({"status": "scan_error", "symbol": symbol, "error_type": type(exc).__name__, "message": str(exc), "live_orders_allowed": False})

    if heartbeat is not None:
        results.append({"status": "price_heartbeat", "heartbeat": heartbeat, "timezone": "Asia/Bangkok"})
    logger.warning("[HEARTBEAT] Scheduler cycle END: processed=%d symbol(s)", len(results))
    return results


def _loop():
    global _RUNNING
    logger.warning("M5 Signal Scheduler thread started; interval=%ss; symbols=%s; test_slots=every_5_minutes Asia/Bangkok", _interval_seconds(), _symbols())
    while _RUNNING:
        started = time.monotonic()
        try:
            run_scan_cycle()
        except Exception as exc:
            logger.exception("Fatal scheduler cycle error")
            _notify_error(exc, "รอบการทำงานหลักของ Scheduler")
        time.sleep(max(1, _interval_seconds() - int(time.monotonic() - started)))
    logger.warning("M5 Signal Scheduler thread stopped")


def start():
    global _RUNNING, _THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():
        return False
    _RUNNING = True
    _THREAD = threading.Thread(target=_loop, name="m5-btc-gold-scanner", daemon=True)
    _THREAD.start()
    logger.warning("Signal Scheduler started successfully; thread=%s", _THREAD.name)
    return True


def stop():
    global _RUNNING
    _RUNNING = False


def status():
    now = datetime.now(UTC)
    return {
        "running": bool(_RUNNING and _THREAD and _THREAD.is_alive()),
        "interval_seconds": _interval_seconds(),
        "symbols": _symbols(),
        "test_slots": "every_5_minutes",
        "timezone": "Asia/Bangkok",
        "provider": "twelve_data",
        "market_sessions": {s: {"open": _asset_market_status(s, now)[0], "session": _asset_market_status(s, now)[1]} for s in _symbols()},
    }
