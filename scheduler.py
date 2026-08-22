import os
import threading
import time
import logging
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

import live_scanner

logger = logging.getLogger("signal_scheduler")

_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}
_LAST_PRICE_HEARTBEAT = None
BANGKOK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc

DISPLAY_SYMBOLS = ("BTC", "GOLD")
DISPLAY_TO_MARKET = {"BTC": "BTC/USDT", "GOLD": "XAU/USDT"}
LEGACY_SYMBOLS = {"BTC/USDT": "BTC", "XAU/USDT": "GOLD"}

GOLD_OPEN_SUNDAY_UTC = os.getenv("GOLD_OPEN_SUNDAY_UTC", "23:00")
GOLD_CLOSE_FRIDAY_UTC = os.getenv("GOLD_CLOSE_FRIDAY_UTC", "22:00")
GOLD_DAILY_BREAK_START_UTC = os.getenv("GOLD_DAILY_BREAK_START_UTC", "22:00")
GOLD_DAILY_BREAK_END_UTC = os.getenv("GOLD_DAILY_BREAK_END_UTC", "23:00")


def _interval_seconds():
    return max(10, int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "15")))


def _symbols():
    # Hard-limit the scheduler to BTC + GOLD even if old environment settings contain ETH/SOL.
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
        logger.warning("Invalid UTC session time %r; using %s", value, fallback)
        return fallback


def _gold_market_status(now_utc):
    sunday_open = _parse_utc_time(GOLD_OPEN_SUNDAY_UTC, dt_time(23, 0))
    friday_close = _parse_utc_time(GOLD_CLOSE_FRIDAY_UTC, dt_time(22, 0))
    break_start = _parse_utc_time(GOLD_DAILY_BREAK_START_UTC, dt_time(22, 0))
    break_end = _parse_utc_time(GOLD_DAILY_BREAK_END_UTC, dt_time(23, 0))
    weekday = now_utc.weekday()
    current = now_utc.time()
    if weekday == 5:
        return False, "WEEKEND_CLOSED"
    if weekday == 6:
        return (current >= sunday_open, "OPEN" if current >= sunday_open else "SUNDAY_CLOSED")
    if weekday == 4:
        return (current < friday_close, "OPEN" if current < friday_close else "FRIDAY_CLOSED")
    if break_start < break_end and break_start <= current < break_end:
        return False, "DAILY_BREAK"
    return True, "OPEN"


def _asset_market_status(symbol, now_utc=None):
    now_utc = now_utc or datetime.now(UTC)
    symbol = (symbol or "").upper()
    if symbol == "BTC":
        return True, "OPEN_24_7"
    if symbol == "GOLD":
        return _gold_market_status(now_utc)
    return False, "UNKNOWN_MARKET_SESSION"


def _notify_scheduler_error(exc, context="Scheduler"):
    try:
        now_bkk = datetime.now(UTC).astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
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
    logger.warning("[%s] Fetching latest closed M5 candle from %s", symbol, market_symbol)
    df = live_scanner.BINANCE.fetch_candles(market_symbol, "5m", 10)
    df = live_scanner.BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=5)
    if df.empty:
        raise RuntimeError(f"ยังไม่มีแท่ง M5 ที่ปิดแล้วสำหรับ {symbol}")
    row = df.iloc[-1]
    key = str(row.get("datetime", row.name))
    logger.warning("[%s] Latest closed M5 candle: %s", symbol, key)
    return key


def _send_price_heartbeat(now_bkk):
    """Send the system test exactly on :00 and :30 Bangkok time, once per slot."""
    global _LAST_PRICE_HEARTBEAT
    if now_bkk.minute not in (0, 30):
        return None

    slot = now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot == _LAST_PRICE_HEARTBEAT:
        return None

    now_utc = now_bkk.astimezone(UTC)
    lines = [
        "🧪 <b>ทดสอบระบบทุก 30 นาที</b>",
        "",
        f"🕐 เวลา: {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)",
        "",
    ]
    feed_ok = True

    for symbol in _symbols():
        market_open, session = _asset_market_status(symbol, now_utc)
        if not market_open:
            lines.append(f"⏸ {symbol}: ตลาดปิด ({session})")
            continue
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
    now_bkk = datetime.now(UTC).astimezone(BANGKOK)
    now_utc = now_bkk.astimezone(UTC)
    symbols = _symbols()
    logger.warning(
        "[HEARTBEAT] Scheduler scan cycle START: %s | symbols=%s | interval=%ss | test_slots=:00/:30",
        now_bkk.strftime("%d/%m/%Y %H:%M:%S"), symbols, _interval_seconds()
    )
    heartbeat = _send_price_heartbeat(now_bkk)
    results = []
    if not symbols:
        raise RuntimeError("ไม่มีสินทรัพย์ที่เปิดใช้งานใน LIVE_SIGNAL_SYMBOLS")

    for symbol in symbols:
        try:
            logger.warning("[%s] Scan step START", symbol)
            if symbol not in live_scanner.SUPPORTED_SYMBOLS:
                raise RuntimeError(f"ไม่รองรับสินทรัพย์: {symbol}")

            market_open, session = _asset_market_status(symbol, now_utc)
            if not market_open:
                logger.warning(
                    "[%s] MARKET CLOSED; skip scan. session=%s utc=%s bkk=%s",
                    symbol, session, now_utc.strftime("%Y-%m-%d %H:%M:%S"), now_bkk.strftime("%Y-%m-%d %H:%M:%S")
                )
                results.append({
                    "status": "market_closed", "symbol": symbol,
                    "market_symbol": DISPLAY_TO_MARKET[symbol], "session": session,
                    "telegram_alert_sent": False, "live_orders_allowed": False,
                    "scan_skipped": True,
                    "message": "ตลาดปิดตามเวลาทำการ ระบบข้ามการวิเคราะห์และรอ Session ถัดไป",
                })
                continue

            logger.warning("[%s] MARKET OPEN; session=%s", symbol, session)
            closed_key = _get_closed_candle_key(symbol)
            previous = _LAST_CLOSED_CANDLE.get(symbol)
            if previous == closed_key:
                logger.warning("[%s] No new closed M5 candle; waiting. candle=%s", symbol, closed_key)
                results.append({
                    "status":"waiting_new_candle", "symbol":symbol, "timeframe":"M5",
                    "closed_candle":closed_key, "message":"ยังไม่มีแท่ง M5 ใหม่ปิด ระบบรอแท่งถัดไป",
                    "telegram_alert_sent":False, "live_orders_allowed":False,
                })
                continue

            logger.warning("[%s] NEW closed M5 candle detected: %s", symbol, closed_key)
            result = live_scanner.scan_once(symbol)
            telegram_sent = bool(isinstance(result, dict) and result.get("telegram_alert_sent"))
            valid_signal = bool(isinstance(result, dict) and result.get("valid"))
            if valid_signal and not telegram_sent:
                logger.warning("[%s] VALID signal detected but Telegram alert was not confirmed; candle=%s will be retried", symbol, closed_key)
            else:
                _LAST_CLOSED_CANDLE[symbol] = closed_key

            logger.warning(
                "[%s] Scan result: signal=%s telegram_alert_sent=%s status=%s",
                symbol, result.get("signal"), result.get("telegram_alert_sent"), result.get("status")
            )
            result["trigger"] = "NEW_CLOSED_M5_CANDLE"
            result["candle_consumed"] = not (valid_signal and not telegram_sent)
            result["market_session"] = session
            results.append(result)
        except Exception as exc:
            logger.exception("[%s] Scan failed", symbol)
            _notify_scheduler_error(exc, context=f"การสแกน {symbol}")
            results.append({
                "status":"scan_error", "symbol":symbol, "error_type":type(exc).__name__,
                "message":str(exc), "telegram_alert_sent":False, "live_orders_allowed":False,
            })

    if heartbeat is not None:
        results.append({"status":"price_heartbeat","heartbeat":heartbeat,"timezone":"Asia/Bangkok"})
    logger.warning("[HEARTBEAT] Scheduler scan cycle END: processed=%d symbol(s)", len(symbols))
    return results


def _loop():
    global _RUNNING
    logger.warning(
        "M5 Signal Scheduler thread started; interval=%ss; symbols=%s; test_slots=:00/:30 Asia/Bangkok",
        _interval_seconds(), _symbols()
    )
    while _RUNNING:
        cycle_started = time.monotonic()
        try:
            run_scan_cycle()
        except Exception as exc:
            logger.exception("Fatal scheduler cycle error")
            _notify_scheduler_error(exc, context="รอบการทำงานหลักของ Scheduler")
        elapsed = time.monotonic() - cycle_started
        logger.warning(
            "[HEARTBEAT] Scheduler cycle returned; elapsed=%.2fs; next_scan_in=%ss; test_slots=:00/:30",
            elapsed, _interval_seconds()
        )
        time.sleep(_interval_seconds())
    logger.warning("M5 Signal Scheduler thread stopped")


def start():
    global _RUNNING, _THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():
        logger.info("Signal Scheduler already running; thread=%s", _THREAD.name)
        return False
    _RUNNING = True
    _THREAD = threading.Thread(target=_loop, name="m5-btc-gold-scanner", daemon=True)
    _THREAD.start()
    logger.warning("Signal Scheduler started successfully; thread=%s", _THREAD.name)
    return True


def stop():
    global _RUNNING
    _RUNNING = False
    logger.warning("Signal Scheduler stop requested")


def status():
    alive = bool(_RUNNING and _THREAD and _THREAD.is_alive())
    now_utc = datetime.now(UTC)
    market_sessions = {
        symbol: {
            "open": _asset_market_status(symbol, now_utc)[0],
            "session": _asset_market_status(symbol, now_utc)[1],
        }
        for symbol in _symbols()
    }
    return {
        "running": alive,
        "interval_seconds": _interval_seconds(),
        "symbols": _symbols(),
        "symbol_mapping": DISPLAY_TO_MARKET,
        "exchange": "Binance + Kraken fallback",
        "timeframe": "M5 trigger + H1/M15 confirmation",
        "trigger": "ทุกครั้งที่มีแท่ง M5 ใหม่ปิด และตลาดเปิด",
        "market_sessions": market_sessions,
        "gold_session_utc": {
            "sunday_open": GOLD_OPEN_SUNDAY_UTC,
            "friday_close": GOLD_CLOSE_FRIDAY_UTC,
            "daily_break": f"{GOLD_DAILY_BREAK_START_UTC}-{GOLD_DAILY_BREAK_END_UTC}",
        },
        "system_test": "ทุก 30 นาที เวลา :00 และ :30 ตาม Asia/Bangkok",
        "price_heartbeat": "นาทีลงท้ายด้วย 00/30 ตามเวลา Asia/Bangkok",
        "last_closed_candle": dict(_LAST_CLOSED_CANDLE),
        "thread_name": _THREAD.name if _THREAD else None,
        "live_orders_allowed": False,
        "timestamp": now_utc.isoformat(),
    }
