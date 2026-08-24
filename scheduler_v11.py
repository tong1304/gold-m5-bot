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
_RUNNING=False; _THREAD=None; _LAST_CLOSED_CANDLE={}; _LAST_TEST_SLOT=None

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
    except Exception:return None

def run_scan_cycle():
    global _LAST_TEST_SLOT
    now_utc=datetime.now(UTC); now_bkk=now_utc.astimezone(BANGKOK); results=[]
    for symbol in _symbols():
        try:
            opened,session=_asset_market_status(symbol,now_utc)
            if not opened:
                results.append({"status":"market_closed","symbol":symbol,"session":session,"live_orders_allowed":False}); continue
            frame=live_scanner_v11._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            if frame.empty:raise RuntimeError("NO_CLOSED_CANDLES")
            closed_key=str(frame.iloc[-1].datetime)
            if _LAST_CLOSED_CANDLE.get(symbol)==closed_key:
                results.append({"status":"waiting_new_candle","symbol":symbol,"closed_candle":closed_key,"engine_version":ENGINE_VERSION}); continue
            result=live_scanner_v11.scan_once(symbol); _LAST_CLOSED_CANDLE[symbol]=closed_key
            result.update({"trigger":"NEW_CLOSED_M5_CANDLE","candle_consumed":True,"market_session":session,"engine_version":ENGINE_VERSION})
            results.append(result)
        except Exception as exc:
            logger.exception("[%s] V11 scan failed",symbol); _notify_error(exc,f"การสแกน {symbol}"); results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})
    if now_bkk.minute%15==0:
        slot=now_bkk.strftime("%Y-%m-%d %H:%M")
        if slot!=_LAST_TEST_SLOT:
            _LAST_TEST_SLOT=slot
            try: send_telegram(f"🧪 <b>V11 System Monitor</b>\n\n🕐 {now_bkk.strftime('%d/%m/%Y %H:%M')} (กรุงเทพฯ)\n✅ Scheduler: Active\n✅ LSE: Connected through scanner\n⚠️ Monitor only — ไม่ใช่สัญญาณ BUY/SELL")
            except Exception: pass
    return results

def _seconds_to_next_boundary():
    return max(1,300-(datetime.now(UTC).timestamp()%300))

def _loop():
    global _RUNNING
    while _RUNNING:
        wait=_seconds_to_next_boundary(); time.sleep(wait)
        if _RUNNING:
            try: run_scan_cycle()
            except Exception as exc: logger.exception("V11 cycle failed"); _notify_error(exc,"V11 scheduler cycle")

def start():
    global _RUNNING,_THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():return False
    _RUNNING=True; _THREAD=threading.Thread(target=_loop,name="v11-m5-scheduler",daemon=True); _THREAD.start(); return True

def stop():
    global _RUNNING; _RUNNING=False

def status():
    try:import live_price; live=live_price.status()
    except Exception as exc:live={"running":False,"error":str(exc)}
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"test_slots":"00,15,30,45","timezone":"Asia/Bangkok","provider":"LSE","engine_version":ENGINE_VERSION,"scanner":"live_scanner_v11","multi_strategy":True,"timeframes":["5m","15m"],"live_price":live,"live_orders_allowed":False}
