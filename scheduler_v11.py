"""Native V11 scheduler. Exactly one loop scans on closed M5 boundaries."""
from __future__ import annotations
import logging, os, threading, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from v11.telegram import send_telegram
import live_scanner_v11

logger=logging.getLogger("signal_scheduler")
ENGINE_VERSION="11.1-HARDENED"
BANGKOK=ZoneInfo("Asia/Bangkok"); UTC=timezone.utc; DISPLAY_SYMBOLS=("BTC","GOLD")
_RUNNING=False; _THREAD=None; _MONITOR_THREAD=None; _LAST_CLOSED_CANDLE={}; _LAST_MONITOR_SLOT=None; _STARTED_AT=None; _LAST_CYCLE_AT=None; _LAST_RESULTS=[]; _CYCLE_COUNT=0

def _interval_seconds():
    try:return max(300,int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS","300")))
    except ValueError:return 300

def _symbols():
    return [s for s in dict.fromkeys(x.strip().upper() for x in os.getenv("LIVE_SIGNAL_SYMBOLS","BTC,GOLD").split(",")) if s in DISPLAY_SYMBOLS]

def _asset_market_status(symbol,now_utc=None):
    now_utc=now_utc or datetime.now(UTC)
    if symbol=="BTC":return True,"OPEN_24_7"
    if symbol!="GOLD":return False,"UNKNOWN_MARKET_SESSION"
    wd=now_utc.weekday(); t=now_utc.time()
    if wd==5:return False,"WEEKEND_CLOSED"
    if wd==6:return (t.hour>=23,"OPEN" if t.hour>=23 else "SUNDAY_CLOSED")
    if wd==4:return (t.hour<22,"OPEN" if t.hour<22 else "FRIDAY_CLOSED")
    if 22<=t.hour<23:return False,"DAILY_BREAK"
    return True,"OPEN"

def _notify_error(exc,context):
    try:return send_telegram(f"❌ <b>{ENGINE_VERSION} Scheduler</b>\n\n🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (กรุงเทพฯ)\n📍 {context}\n🔴 {type(exc).__name__}: {exc}\n\n🛑 ไม่มีการเปิดออเดอร์อัตโนมัติ")
    except Exception as notify_exc:
        logger.warning("[V11 TELEGRAM] Error notification failed: %s",notify_exc)
        return None

def _fmt_price(value):
    try:
        price=float(value)
        if price<=0:return "N/A"
        return f"{price:,.2f}"
    except (TypeError,ValueError):
        return "N/A"

def _live_price_line(symbol):
    try:
        import live_price
        tick=live_price.get(symbol)
        label="₿ BTC" if symbol=="BTC" else "🟠 GOLD"
        if not tick:
            return f"{label}: <b>N/A</b> (รอ live tick)"
        price=_fmt_price(tick.get("price"))
        age=tick.get("age_seconds")
        age_text=f" · {age:.1f}s" if isinstance(age,(int,float)) else ""
        return f"{label}: <b>{price}</b>{age_text}"
    except Exception as exc:
        logger.warning("[V11 TELEGRAM] Live price read failed symbol=%s: %s",symbol,exc)
        return f"{'₿ BTC' if symbol=='BTC' else '🟠 GOLD'}: <b>N/A</b>"

def _send_15m_system_monitor(now_bkk=None):
    global _LAST_MONITOR_SLOT
    now_bkk=now_bkk or datetime.now(UTC).astimezone(BANGKOK)
    if now_bkk.minute not in (0,15,30,45):
        return False
    slot=now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot==_LAST_MONITOR_SLOT:
        return False
    try:
        import live_price
        status=live_price.status()
        connected="CONNECTED" if status.get("connected") else "DISCONNECTED"
        authenticated="AUTHENTICATED" if status.get("authenticated") else "NOT AUTHENTICATED"
        ticks=status.get("ticks_received",0)
        msg=(
            f"🟢 <b>V11 SYSTEM STATUS</b>\n\n"
            f"🕐 {now_bkk.strftime('%d/%m/%Y %H:%M:%S')} (กรุงเทพฯ)\n"
            f"⚙️ Engine: <b>{ENGINE_VERSION}</b>\n"
            f"⏱ Scheduler: <b>RUNNING</b>\n"
            f"📡 LSE: <b>{connected}</b>\n"
            f"🔐 Auth: <b>{authenticated}</b>\n"
            f"📥 Live ticks: <b>{ticks}</b>\n\n"
            f"📊 <b>ราคาปัจจุบัน</b>\n"
            f"{_live_price_line('GOLD')}\n"
            f"{_live_price_line('BTC')}\n\n"
            f"⚠️ Monitor only — ไม่ใช่สัญญาณ BUY/SELL"
        )
        result=send_telegram(msg)
        _LAST_MONITOR_SLOT=slot
        logger.warning("[V11 TELEGRAM] 15m system monitor sent slot=%s result=%s",slot,result)
        return True
    except Exception as exc:
        logger.warning("[V11 TELEGRAM] 15m system monitor failed slot=%s: %s",slot,exc)
        return False

def _seconds_to_next_monitor_slot():
    now=datetime.now(UTC).astimezone(BANGKOK)
    minute=((now.minute//15)+1)*15
    if minute>=60:
        target=now.replace(hour=(now.hour+1)%24,minute=0,second=0,microsecond=0)
        if now.hour==23: target=target.replace(day=now.day)+__import__('datetime').timedelta(days=1)
    else:
        target=now.replace(minute=minute,second=0,microsecond=0)
    return max(0.5,(target-now).total_seconds())

def _monitor_loop():
    global _MONITOR_THREAD
    logger.warning("[V11 TELEGRAM] 15m monitor thread entered; timezone=Asia/Bangkok slots=00,15,30,45")
    while _RUNNING:
        wait=_seconds_to_next_monitor_slot()
        time.sleep(wait)
        if not _RUNNING:break
        try:
            now_bkk=datetime.now(UTC).astimezone(BANGKOK)
            _send_15m_system_monitor(now_bkk)
        except Exception as exc:
            logger.exception("[V11 TELEGRAM] 15m monitor loop failed")
            _notify_error(exc,"15m Telegram system monitor")
    logger.warning("[V11 TELEGRAM] 15m monitor thread exited")

def run_scan_cycle():
    global _LAST_CYCLE_AT,_LAST_RESULTS,_CYCLE_COUNT
    now_utc=datetime.now(UTC); now_bkk=now_utc.astimezone(BANGKOK); results=[]; _CYCLE_COUNT+=1; _LAST_CYCLE_AT=now_utc.isoformat()
    logger.warning("[V11 SCHEDULER] Scan cycle #%s started at %s Bangkok symbols=%s",_CYCLE_COUNT,now_bkk.strftime('%Y-%m-%d %H:%M:%S'),_symbols())
    for symbol in _symbols():
        try:
            opened,session=_asset_market_status(symbol,now_utc)
            logger.info("[V11 SCHEDULER] %s market=%s session=%s",symbol,opened,session)
            if not opened:
                results.append({"status":"market_closed","symbol":symbol,"session":session,"live_orders_allowed":False}); continue
            frame=live_scanner_v11._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            if frame.empty:raise RuntimeError("NO_CLOSED_CANDLES")
            closed_key=str(frame.iloc[-1].datetime)
            logger.info("[V11 SCHEDULER] %s latest_closed_m5=%s rows=%s",symbol,closed_key,len(frame))
            if _LAST_CLOSED_CANDLE.get(symbol)==closed_key:
                results.append({"status":"waiting_new_candle","symbol":symbol,"closed_candle":closed_key,"engine_version":ENGINE_VERSION}); continue
            result=live_scanner_v11.scan_once(symbol); _LAST_CLOSED_CANDLE[symbol]=closed_key
            result.update({"trigger":"NEW_CLOSED_M5_CANDLE","candle_consumed":True,"market_session":session,"engine_version":ENGINE_VERSION})
            logger.warning("[V11 SCHEDULER] %s result status=%s strategy=%s side=%s",symbol,result.get("status"),result.get("strategy"),result.get("side"))
            results.append(result)
        except Exception as exc:
            logger.exception("[V11 SCHEDULER] %s scan failed",symbol); _notify_error(exc,f"การสแกน {symbol}"); results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})
    _LAST_RESULTS=results
    logger.warning("[V11 SCHEDULER] Scan cycle #%s finished results=%s",_CYCLE_COUNT,len(results))
    return results

def _seconds_to_next_boundary():
    return max(1,300-(datetime.now(UTC).timestamp()%300))

def _loop():
    global _RUNNING
    logger.warning("[V11 SCHEDULER] Thread entered; waiting for next closed M5 boundary")
    while _RUNNING:
        wait=_seconds_to_next_boundary(); logger.info("[V11 SCHEDULER] Next scan in %.1fs",wait); time.sleep(wait)
        if _RUNNING:
            try: run_scan_cycle()
            except Exception as exc: logger.exception("[V11 SCHEDULER] cycle failed"); _notify_error(exc,"V11 scheduler cycle")
    logger.warning("[V11 SCHEDULER] Thread exited")

def start():
    global _RUNNING,_THREAD,_MONITOR_THREAD,_STARTED_AT
    if _RUNNING and _THREAD and _THREAD.is_alive():return False
    _RUNNING=True; _STARTED_AT=datetime.now(UTC).isoformat(); _THREAD=threading.Thread(target=_loop,name="v11-m5-scheduler",daemon=True); _THREAD.start(); _MONITOR_THREAD=threading.Thread(target=_monitor_loop,name="v11-telegram-15m-monitor",daemon=True); _MONITOR_THREAD.start(); logger.warning("[V11 SCHEDULER] STARTED engine=%s interval=%ss symbols=%s timezone=Asia/Bangkok",ENGINE_VERSION,_interval_seconds(),_symbols()); return True

def stop():
    global _RUNNING; _RUNNING=False; logger.warning("[V11 SCHEDULER] STOP requested")

def status():
    try:import live_price; live=live_price.status()
    except Exception as exc:live={"running":False,"error":str(exc)}
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"test_slots":"00,15,30,45","timezone":"Asia/Bangkok","provider":"LSE","engine_version":ENGINE_VERSION,"scanner":"live_scanner_v11","multi_strategy":True,"timeframes":["5m","15m"],"started_at":_STARTED_AT,"last_cycle_at":_LAST_CYCLE_AT,"cycle_count":_CYCLE_COUNT,"last_results":_LAST_RESULTS,"live_price":live,"telegram_monitor_running":bool(_RUNNING and _MONITOR_THREAD and _MONITOR_THREAD.is_alive()),"telegram_monitor":"00,15,30,45 Asia/Bangkok","last_monitor_slot":_LAST_MONITOR_SLOT,"live_orders_allowed":False}
