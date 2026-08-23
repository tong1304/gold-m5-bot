import logging
import os
import threading
import time
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

logger=logging.getLogger("signal_scheduler")
_RUNNING=False
_THREAD=None
_LAST_CLOSED_CANDLE={}
_LAST_TEST_SLOT=None
BANGKOK=ZoneInfo("Asia/Bangkok")
UTC=timezone.utc
DISPLAY_SYMBOLS=("BTC","GOLD")
GOLD_OPEN_SUNDAY_UTC=os.getenv("GOLD_OPEN_SUNDAY_UTC","23:00")
GOLD_CLOSE_FRIDAY_UTC=os.getenv("GOLD_CLOSE_FRIDAY_UTC","22:00")
GOLD_DAILY_BREAK_START_UTC=os.getenv("GOLD_DAILY_BREAK_START_UTC","22:00")
GOLD_DAILY_BREAK_END_UTC=os.getenv("GOLD_DAILY_BREAK_END_UTC","23:00")


def _interval_seconds():
    try: configured=int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS","300"))
    except ValueError: configured=300
    return max(300,configured)


def _symbols():
    out=[]
    for value in os.getenv("LIVE_SIGNAL_SYMBOLS","BTC,GOLD").split(","):
        symbol=value.strip().upper()
        if symbol in DISPLAY_SYMBOLS and symbol not in out: out.append(symbol)
    return out


def _parse_time(value,fallback):
    try:
        h,m=str(value).split(":",1); return dt_time(int(h),int(m))
    except (TypeError,ValueError): return fallback


def _asset_market_status(symbol,now_utc=None):
    now_utc=now_utc or datetime.now(UTC)
    if symbol=="BTC": return True,"OPEN_24_7"
    if symbol!="GOLD": return False,"UNKNOWN_MARKET_SESSION"
    current,weekday=now_utc.time(),now_utc.weekday()
    sunday=_parse_time(GOLD_OPEN_SUNDAY_UTC,dt_time(23,0)); friday=_parse_time(GOLD_CLOSE_FRIDAY_UTC,dt_time(22,0)); br_start=_parse_time(GOLD_DAILY_BREAK_START_UTC,dt_time(22,0)); br_end=_parse_time(GOLD_DAILY_BREAK_END_UTC,dt_time(23,0))
    if weekday==5: return False,"WEEKEND_CLOSED"
    if weekday==6: return (current>=sunday,"OPEN" if current>=sunday else "SUNDAY_CLOSED")
    if weekday==4: return (current<friday,"OPEN" if current<friday else "FRIDAY_CLOSED")
    if br_start<br_end and br_start<=current<br_end: return False,"DAILY_BREAK"
    return True,"OPEN"


def _scanner():
    import live_scanner
    return live_scanner


def _notify_error(exc,context):
    text=("❌ <b>ระบบ Scheduler ขัดข้อง</b>\n\n" f"🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (กรุงเทพฯ)\n" f"📍 {context}\n🔴 {type(exc).__name__}\n📝 {exc}\n\n🛑 ไม่มีการเปิดออเดอร์อัตโนมัติ")
    try: return _scanner().engine.send_telegram(text)
    except Exception: return None


def _evaluate_signal_history():
    from signal_history import history
    pending=history.pending(limit=200)
    if not pending: return 0
    scanner=_scanner(); resolved=0
    for row in pending:
        try:
            symbol=str(row.get("symbol","")).upper()
            if symbol not in DISPLAY_SYMBOLS: continue
            frame=scanner._lse_frame(symbol,"5m",max(200,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            before=row["result"]
            updated=history.evaluate_candles(row["signal_id"],frame.to_dict("records"))
            if updated and updated.get("result")!=before:
                resolved+=1; logger.warning("[SIGNAL HISTORY] %s -> %s r=%s source=LSE",row["signal_id"],updated.get("result"),updated.get("r_multiple"))
        except Exception as exc:
            logger.warning("[SIGNAL HISTORY] evaluate failed for %s: %s",row.get("signal_id"),exc)
    return resolved


def _system_test(now_bkk):
    global _LAST_TEST_SLOT
    if now_bkk.minute%15!=0: return None
    slot=now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot==_LAST_TEST_SLOT: return None
    lines=["🧪 <b>ทดสอบระบบทุก 15 นาที</b>","",f"🕐 เวลา: {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)",""]
    live_ok=True
    try:
        import live_price
        status=live_price.status()
        for symbol in _symbols():
            open_,session=_asset_market_status(symbol,now_bkk.astimezone(UTC))
            if not open_: lines.append(f"⏸ {symbol}: ตลาดปิด ({session})"); continue
            live=live_price.get(symbol)
            if not live or live.get("age_seconds") is None or float(live.get("age_seconds",999999))>float(os.getenv("MAX_LIVE_PRICE_AGE_SECONDS","30")):
                live_ok=False; lines.append(f"⚠️ {symbol}: ยังไม่มี Live Tick ที่สดพอ"); continue
            lines.append(f"💹 {symbol}: <b>{float(live['price']):,.8f}</b> | Live age: {float(live['age_seconds']):.1f}s")
        if not status.get("running"): live_ok=False
    except Exception as exc:
        live_ok=False; lines.append(f"❌ LSE Live Price: {type(exc).__name__}: {exc}")
    lines += ["","✅ Scheduler ทำงาน","✅ LSE WebSocket Live Price" if live_ok else "⚠️ LSE WebSocket Live Price มีปัญหา","✅ Telegram Monitor","","ℹ️ การทดสอบนี้ไม่ใช่สัญญาณ BUY/SELL"]
    try:
        result=_scanner().engine.send_telegram("\n".join(lines)); sent=bool(isinstance(result,dict) and result.get("success"))
        if sent: _LAST_TEST_SLOT=slot
        return {"sent":sent,"slot":slot,"telegram_result":result,"timezone":"Asia/Bangkok","live_price_ok":live_ok}
    except Exception as exc: return {"sent":False,"slot":slot,"error_type":type(exc).__name__,"error":str(exc),"live_price_ok":live_ok}


def run_scan_cycle():
    now_bkk=datetime.now(UTC).astimezone(BANGKOK); now_utc=now_bkk.astimezone(UTC); symbols=_symbols()
    logger.warning("[HEARTBEAT] Scheduler cycle START: %s | symbols=%s | interval=%ss | provider=LSE",now_bkk.strftime("%d/%m/%Y %H:%M:%S"),symbols,_interval_seconds())
    heartbeat=_system_test(now_bkk); history_resolved=_evaluate_signal_history(); results=[]; scanner=_scanner()
    for symbol in symbols:
        try:
            open_,session=_asset_market_status(symbol,now_utc)
            if not open_: results.append({"status":"market_closed","symbol":symbol,"session":session,"live_orders_allowed":False}); continue
            frame=scanner._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            if frame.empty: raise RuntimeError(f"ไม่มีแท่ง M5 จาก LSE สำหรับ {symbol}")
            closed_key=str(frame.iloc[-1]["datetime"])
            if _LAST_CLOSED_CANDLE.get(symbol)==closed_key:
                results.append({"status":"waiting_new_candle","symbol":symbol,"timeframe":"M5","closed_candle":closed_key,"live_orders_allowed":False}); continue
            result=scanner.scan_once(symbol)
            _LAST_CLOSED_CANDLE[symbol]=closed_key
            result["trigger"]="NEW_CLOSED_M5_CANDLE"; result["candle_consumed"]=True; result["market_session"]=session
            results.append(result)
        except Exception as exc:
            logger.exception("[%s] Scan failed",symbol); _notify_error(exc,f"การสแกน {symbol}"); results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})
    if heartbeat is not None: results.append({"status":"price_heartbeat","heartbeat":heartbeat,"timezone":"Asia/Bangkok"})
    if history_resolved: results.append({"status":"signal_history_resolved","count":history_resolved})
    logger.warning("[HEARTBEAT] Scheduler cycle END: processed=%d symbol(s) | provider=LSE",len(results))
    return results


def _seconds_to_next_five_minute():
    return max(1,300-(datetime.now(UTC).timestamp()%300))


def _loop():
    global _RUNNING
    wait=_seconds_to_next_five_minute(); logger.warning("M5 Signal Scheduler thread started; first_cycle_in=%.1fs; interval=%ss; provider=LSE",wait,_interval_seconds()); time.sleep(wait)
    while _RUNNING:
        started=time.monotonic()
        try: run_scan_cycle()
        except Exception as exc: logger.exception("Fatal scheduler cycle error"); _notify_error(exc,"รอบการทำงานหลักของ Scheduler")
        elapsed=time.monotonic()-started; wait=_seconds_to_next_five_minute(); logger.warning("[HEARTBEAT] Scheduler cycle returned; elapsed=%.2fs; next_cycle_in=%.1fs; provider=LSE",elapsed,wait); time.sleep(wait)


def start():
    global _RUNNING,_THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive(): return False
    _RUNNING=True; _THREAD=threading.Thread(target=_loop,name="m5-btc-gold-scanner",daemon=True); _THREAD.start(); logger.warning("Signal Scheduler started successfully; thread=%s",_THREAD.name); return True


def stop():
    global _RUNNING
    _RUNNING=False


def status():
    now=datetime.now(UTC)
    try:
        import live_price; live=live_price.status()
    except Exception as exc: live={"running":False,"error":f"{type(exc).__name__}: {exc}"}
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"test_slots":"00,15,30,45","timezone":"Asia/Bangkok","provider":"LSE","live_price":live,"statistics_page":"/statistics","statistics_api":"/api/statistics","market_sessions":{s:{"open":_asset_market_status(s,now)[0],"session":_asset_market_status(s,now)[1]} for s in _symbols()}}
