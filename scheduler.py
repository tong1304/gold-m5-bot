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
_WEB_REGISTERED = False
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
    try:
        configured = int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "300"))
    except ValueError:
        configured = 300
    return max(300, configured)


def _symbols():
    result = []
    for value in os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC,GOLD").split(","):
        symbol = LEGACY_SYMBOLS.get(value.strip().upper(), value.strip().upper())
        if symbol in DISPLAY_SYMBOLS and symbol not in result:
            result.append(symbol)
    return result


def _parse_time(value, fallback):
    try:
        h, m = str(value).strip().split(":", 1)
        return dt_time(int(h), int(m))
    except (TypeError, ValueError):
        return fallback


def _asset_market_status(symbol, now_utc=None):
    now_utc = now_utc or datetime.now(UTC)
    if symbol == "BTC":
        return True, "OPEN_24_7"
    if symbol != "GOLD":
        return False, "UNKNOWN_MARKET_SESSION"
    current, weekday = now_utc.time(), now_utc.weekday()
    sunday = _parse_time(GOLD_OPEN_SUNDAY_UTC, dt_time(23, 0))
    friday = _parse_time(GOLD_CLOSE_FRIDAY_UTC, dt_time(22, 0))
    br_start = _parse_time(GOLD_DAILY_BREAK_START_UTC, dt_time(22, 0))
    br_end = _parse_time(GOLD_DAILY_BREAK_END_UTC, dt_time(23, 0))
    if weekday == 5:
        return False, "WEEKEND_CLOSED"
    if weekday == 6:
        return (current >= sunday, "OPEN" if current >= sunday else "SUNDAY_CLOSED")
    if weekday == 4:
        return (current < friday, "OPEN" if current < friday else "FRIDAY_CLOSED")
    if br_start < br_end and br_start <= current < br_end:
        return False, "DAILY_BREAK"
    return True, "OPEN"


def _scanner():
    import live_scanner
    return live_scanner


def _notify_error(exc, context):
    text = ("❌ <b>ระบบ Scheduler ขัดข้อง</b>\n\n"
            f"🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (กรุงเทพฯ)\n"
            f"📍 {context}\n🔴 {type(exc).__name__}\n📝 {exc}\n\n"
            "🛑 ไม่มีการเปิดออเดอร์อัตโนมัติ")
    try:
        return _scanner().engine.send_telegram(text)
    except Exception:
        try:
            import engine_v5 as engine
            return engine.send_telegram(text)
        except Exception:
            logger.exception("Scheduler Telegram error notification failed")
            return None


def _closed_frame(symbol, limit=10):
    scanner = _scanner()
    frame = scanner.BINANCE.fetch_candles(DISPLAY_TO_MARKET[symbol], "5m", limit)
    frame = scanner.BINANCE.remove_incomplete_last_candle(frame, timeframe_minutes=5)
    if frame.empty:
        raise RuntimeError(f"ยังไม่มีแท่ง M5 ที่ปิดแล้วสำหรับ {symbol}")
    return frame


def _lse_history_frame(symbol, limit=200):
    """Fetch the same 5m market history from LSE for result evaluation.

    Signal history must be resolved against the provider used by the live system,
    not Binance.  lse-data 0.14 exposes candles() through the same API key used
    by the WebSocket feed.  The response shape changed across early SDK releases,
    so this parser accepts both a direct list and {data:[...]}.
    """
    from lse import LSE
    import pandas as pd

    market = DISPLAY_TO_MARKET[symbol]
    client = LSE(api_key=os.getenv("LSE_API_KEY"))
    raw = client.candles(market, "5m", limit=int(limit), order="asc")
    if isinstance(raw, dict):
        rows = raw.get("data") or raw.get("candles") or raw.get("rows") or []
    else:
        rows = raw or []
    if not isinstance(rows, list):
        rows = list(rows)
    if not rows:
        raise RuntimeError(f"LSE ไม่มีข้อมูล M5 สำหรับ {market}")
    frame = pd.DataFrame(rows)
    rename = {
        "timestamp": "datetime",
        "time": "datetime",
        "ts": "datetime",
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
    }
    frame = frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns})
    required = {"datetime", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise RuntimeError(f"LSE M5 response missing columns: {sorted(missing)}")
    frame["datetime"] = frame["datetime"].astype(str)
    for col in ("open", "high", "low", "close", "volume"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["high", "low", "close"]).reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"LSE M5 มีข้อมูลราคาไม่สมบูรณ์สำหรับ {market}")
    return frame


def _history_frame(symbol, limit=200):
    """Prefer LSE history; fall back to the existing scanner source if LSE REST fails."""
    try:
        frame = _lse_history_frame(symbol, limit=limit)
        logger.warning("[SIGNAL HISTORY] LSE M5 history fetched: %s rows=%d", DISPLAY_TO_MARKET[symbol], len(frame))
        return frame, "LSE"
    except Exception as lse_exc:
        logger.warning("[SIGNAL HISTORY] LSE history unavailable for %s: %s", symbol, lse_exc)
        scanner = _scanner()
        frame = scanner.BINANCE.fetch_candles(DISPLAY_TO_MARKET[symbol], "5m", limit)
        frame = scanner.BINANCE.remove_incomplete_last_candle(frame, timeframe_minutes=5)
        if frame.empty:
            raise RuntimeError(f"ไม่มีแท่ง M5 สำหรับประเมิน {symbol}; LSE error: {lse_exc}")
        logger.warning("[SIGNAL HISTORY] fallback M5 history source=Binance: %s rows=%d", DISPLAY_TO_MARKET[symbol], len(frame))
        return frame, "Binance-fallback"


def _evaluate_signal_history():
    """Resolve previously Telegram-sent signals into WIN/LOSS/AMBIGUOUS."""
    try:
        from signal_history import history
        pending = history.pending(limit=200)
        if not pending:
            return 0
        resolved = 0
        for row in pending:
            try:
                symbol = str(row.get("symbol", "")).upper()
                if symbol not in DISPLAY_SYMBOLS:
                    logger.warning("[SIGNAL HISTORY] unsupported stored symbol=%s", symbol)
                    continue
                frame, source = _history_frame(symbol, 200)
                candles = frame.to_dict("records")
                before = row["result"]
                updated = history.evaluate_candles(row["signal_id"], candles)
                if updated and updated.get("result") != before:
                    resolved += 1
                    logger.warning("[SIGNAL HISTORY] %s -> %s r=%s source=%s", row["signal_id"], updated.get("result"), updated.get("r_multiple"), source)
            except Exception as exc:
                logger.warning("[SIGNAL HISTORY] evaluate failed for %s: %s", row.get("signal_id"), exc)
        return resolved
    except Exception as exc:
        logger.warning("[SIGNAL HISTORY] history evaluator unavailable: %s", exc)
        return 0


def _register_statistics_routes():
    global _WEB_REGISTERED
    if _WEB_REGISTERED:
        return
    try:
        import engine_v5 as engine
        from statistics_page import register
        register(engine.app)
        _WEB_REGISTERED = True
        logger.warning("Signal Statistics routes registered: /statistics /api/statistics /api/signals")
    except Exception as exc:
        logger.exception("Signal Statistics routes registration failed: %s", exc)


def _system_test(now_bkk):
    global _LAST_TEST_SLOT
    if now_bkk.minute % 15 != 0:
        return None
    slot = now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot == _LAST_TEST_SLOT:
        return None
    lines = ["🧪 <b>ทดสอบระบบทุก 15 นาที</b>", "", f"🕐 เวลา: {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)", ""]
    feed_ok = True
    live_ok = True
    try:
        import live_price
        live_status = live_price.status()
        for symbol in _symbols():
            open_, session = _asset_market_status(symbol, now_bkk.astimezone(UTC))
            if not open_:
                lines.append(f"⏸ {symbol}: ตลาดปิด ({session})")
                continue
            live = live_price.get(symbol)
            if not live or live.get("age_seconds") is None or float(live.get("age_seconds", 999999)) > float(os.getenv("MAX_LIVE_PRICE_AGE_SECONDS", "30")):
                live_ok = False
                lines.append(f"⚠️ {symbol}: ยังไม่มี Live Tick ที่สดพอ")
                continue
            lines.append(f"💹 {symbol}: <b>{float(live['price']):,.8f}</b> | Live age: {float(live['age_seconds']):.1f}s")
        if not live_status.get("running"):
            live_ok = False
    except Exception as exc:
        live_ok = False
        feed_ok = False
        logger.exception("LSE live price system test failed")
        lines.append(f"❌ LSE Live Price: {type(exc).__name__}: {exc}")
    lines += ["", "✅ Scheduler ทำงาน", "✅ LSE WebSocket Live Price" if live_ok else "⚠️ LSE WebSocket Live Price มีปัญหา", "✅ Telegram Monitor", "", "ℹ️ การทดสอบนี้ไม่ใช่สัญญาณ BUY/SELL"]
    try:
        scanner = _scanner()
        result = scanner.engine.send_telegram("\n".join(lines))
        sent = bool(isinstance(result, dict) and result.get("success"))
        if sent:
            _LAST_TEST_SLOT = slot
        return {"sent": sent, "slot": slot, "telegram_result": result, "timezone": "Asia/Bangkok", "live_price_ok": live_ok, "feed_ok": feed_ok}
    except Exception as exc:
        logger.exception("15-minute system test Telegram send failed")
        return {"sent": False, "slot": slot, "error_type": type(exc).__name__, "error": str(exc), "live_price_ok": live_ok, "feed_ok": feed_ok}


def run_scan_cycle():
    now_bkk = datetime.now(UTC).astimezone(BANGKOK)
    now_utc = now_bkk.astimezone(UTC)
    symbols = _symbols()
    logger.warning("[HEARTBEAT] Scheduler cycle START: %s | symbols=%s | interval=%ss | test_slots=every_15_minutes Asia/Bangkok | provider=LSE", now_bkk.strftime("%d/%m/%Y %H:%M:%S"), symbols, _interval_seconds())
    heartbeat = _system_test(now_bkk)
    history_resolved = _evaluate_signal_history()
    results = []
    try:
        scanner = _scanner()
    except Exception as exc:
        logger.warning("LSE scanner unavailable: %s", exc)
        _notify_error(exc, "เริ่มต้น market-data scanner")
        return [{"status": "lse_unavailable", "error_type": type(exc).__name__, "message": str(exc)}]

    for symbol in symbols:
        try:
            if symbol not in scanner.SUPPORTED_SYMBOLS:
                raise RuntimeError(f"ไม่รองรับสินทรัพย์: {symbol}")
            open_, session = _asset_market_status(symbol, now_utc)
            if not open_:
                results.append({"status": "market_closed", "symbol": symbol, "session": session, "live_orders_allowed": False})
                continue
            frame = _closed_frame(symbol)
            closed_key = str(frame.iloc[-1]["datetime"])
            if _LAST_CLOSED_CANDLE.get(symbol) == closed_key:
                results.append({"status": "waiting_new_candle", "symbol": symbol, "timeframe": "M5", "closed_candle": closed_key, "live_orders_allowed": False})
                continue
            result = scanner.scan_once(symbol)
            valid = bool(isinstance(result, dict) and result.get("valid"))
            telegram_sent = bool(isinstance(result, dict) and result.get("telegram_alert_sent"))
            if not (valid and not telegram_sent):
                _LAST_CLOSED_CANDLE[symbol] = closed_key
            if telegram_sent and valid:
                try:
                    from signal_history import history
                    history.record_signal(result)
                    logger.warning("[SIGNAL HISTORY] recorded %s %s %s", result.get("signal_id"), symbol, result.get("signal"))
                except Exception as exc:
                    logger.exception("[SIGNAL HISTORY] record failed: %s", exc)
            result["trigger"] = "NEW_CLOSED_M5_CANDLE"
            result["candle_consumed"] = not (valid and not telegram_sent)
            result["market_session"] = session
            results.append(result)
        except Exception as exc:
            logger.exception("[%s] Scan failed", symbol)
            _notify_error(exc, f"การสแกน {symbol}")
            results.append({"status": "scan_error", "symbol": symbol, "error_type": type(exc).__name__, "message": str(exc), "live_orders_allowed": False})
    if heartbeat is not None:
        results.append({"status": "price_heartbeat", "heartbeat": heartbeat, "timezone": "Asia/Bangkok"})
    if history_resolved:
        results.append({"status": "signal_history_resolved", "count": history_resolved})
    logger.warning("[HEARTBEAT] Scheduler cycle END: processed=%d symbol(s) | provider=LSE", len(results))
    return results


def _seconds_to_next_five_minute():
    now = datetime.now(UTC)
    epoch = now.timestamp()
    return max(1, 300 - (epoch % 300))


def _loop():
    global _RUNNING
    wait = _seconds_to_next_five_minute()
    logger.warning("M5 Signal Scheduler thread started; first_cycle_in=%.1fs; interval=%ss; test_slots=00,15,30,45 Asia/Bangkok; provider=LSE", wait, _interval_seconds())
    time.sleep(wait)
    while _RUNNING:
        started = time.monotonic()
        try:
            run_scan_cycle()
        except Exception as exc:
            logger.exception("Fatal scheduler cycle error")
            _notify_error(exc, "รอบการทำงานหลักของ Scheduler")
        elapsed = time.monotonic() - started
        wait = max(1, 300 - (time.time() % 300))
        logger.warning("[HEARTBEAT] Scheduler cycle returned; elapsed=%.2fs; next_cycle_in=%.1fs; test_slots=00,15,30,45 Asia/Bangkok; provider=LSE", elapsed, wait)
        time.sleep(wait)
    logger.warning("M5 Signal Scheduler thread stopped")


def start():
    global _RUNNING, _THREAD
    _register_statistics_routes()
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
    try:
        import live_price
        live = live_price.status()
    except Exception as exc:
        live = {"running": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"running": bool(_RUNNING and _THREAD and _THREAD.is_alive()), "interval_seconds": _interval_seconds(), "symbols": _symbols(), "test_slots": "00,15,30,45", "timezone": "Asia/Bangkok", "provider": "LSE", "live_price": live, "statistics_page": "/statistics", "statistics_api": "/api/statistics", "market_sessions": {s: {"open": _asset_market_status(s, now)[0], "session": _asset_market_status(s, now)[1]} for s in _symbols()}}
