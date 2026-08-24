"""Native V11 scheduler. One scan loop on closed M5 boundaries + Thai 15-minute monitor."""
from __future__ import annotations
import logging,os,threading,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from v11.telegram import send_telegram
import live_scanner_v11
logger=logging.getLogger("signal_scheduler")
ENGINE_VERSION="11.1-HARDENED"; BANGKOK=ZoneInfo("Asia/Bangkok"); UTC=timezone.utc; DISPLAY_SYMBOLS=("BTC","GOLD")
_RUNNING=False; _THREAD=None; _MONITOR_THREAD=None; _LAST_CLOSED_CANDLE={}; _LAST_MONITOR_SLOT=None; _STARTED_AT=None; _LAST_CYCLE_AT=None; _LAST_RESULTS=[]; _CYCLE_COUNT=0

def _interval_seconds():
    try:return max(300,int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS","300")))
    except ValueError:return 300
def _symbols():return [s for s in dict.fromkeys(x.strip().upper() for x in os.getenv("LIVE_SIGNAL_SYMBOLS","BTC,GOLD").split(",")) if s in DISPLAY_SYMBOLS]
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
    try:return send_telegram(f"❌ <b>เกิดข้อผิดพลาดในระบบ V11</b>\n\n🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (ประเทศไทย)\n📍 {context}\n🔴 {type(exc).__name__}: {exc}\n\n🛑 ระบบจะไม่เปิดออเดอร์อัตโนมัติ")
    except Exception:return None
def _fmt_price(value):
    try:
        price=float(value); return f"{price:,.2f}" if price>0 else "N/A"
    except (TypeError,ValueError):return "N/A"
def _live_price_line(symbol):
    try:
        import live_price
        tick=live_price.get(symbol); label="₿ BTC" if symbol=="BTC" else "🟠 GOLD"
        if not tick:return f"{label}: <b>N/A</b> (กำลังรอ live tick)"
        age=tick.get("age_seconds"); age_text=f" · {age:.1f} วินาที" if isinstance(age,(int,float)) else ""
        return f"{label}: <b>{_fmt_price(tick.get('price'))}</b>{age_text}"
    except Exception as exc:
        logger.warning("[V11 TELEGRAM] อ่านราคาปัจจุบันไม่สำเร็จ symbol=%s: %s",symbol,exc); return f"{'₿ BTC' if symbol=='BTC' else '🟠 GOLD'}: <b>N/A</b>"

def _send_15m_system_monitor(now_bkk=None):
    global _LAST_MONITOR_SLOT
    now_bkk=now_bkk or datetime.now(UTC).astimezone(BANGKOK)
    if now_bkk.minute not in (0,15,30,45):return False
    slot=now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot==_LAST_MONITOR_SLOT:return False
    try:
        import live_price
        status=live_price.status(); connected="เชื่อมต่อแล้ว" if status.get("connected") else "ขาดการเชื่อมต่อ"; authenticated="ยืนยันตัวตนแล้ว" if status.get("authenticated") else "ยังไม่ยืนยันตัวตน"; ticks=status.get("ticks_received",0)
        msg=(f"🟢 <b>สถานะระบบ V11</b>\n\n🕐 {now_bkk.strftime('%d/%m/%Y %H:%M:%S')} (ประเทศไทย)\n⚙️ Engine: <b>{ENGINE_VERSION}</b>\n⏱ Scheduler: <b>ทำงานอยู่</b>\n📡 LSE: <b>{connected}</b>\n🔐 Authentication: <b>{authenticated}</b>\n📥 Live ticks: <b>{ticks:,}</b>\n\n📊 <b>ราคาสินทรัพย์ปัจจุบัน</b>\n{_live_price_line('GOLD')}\n{_live_price_line('BTC')}\n\nℹ️ นี่คือการแจ้งเตือนสถานะระบบ ไม่ใช่สัญญาณ BUY/SELL")
        result=send_telegram(msg); _LAST_MONITOR_SLOT=slot; logger.warning("[V11 TELEGRAM] แจ้งสถานะทุก 15 นาที slot=%s result=%s",slot,result); return True
    except Exception as exc:logger.warning("[V11 TELEGRAM] แจ้งสถานะ 15 นาทีไม่สำเร็จ: %s",exc); return False

def _seconds_to_next_monitor_slot():
    now=datetime.now(UTC).astimezone(BANGKOK); minute=((now.minute//15)+1)*15
    if minute>=60:
        from datetime import timedelta
        target=(now+timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
    else:target=now.replace(minute=minute,second=0,microsecond=0)
    return max(.5,(target-now).total_seconds())
def _monitor_loop():
    logger.warning("[V11 TELEGRAM] เริ่ม Monitor ทุก 15 นาที timezone=Asia/Bangkok slots=00,15,30,45")
    while _RUNNING:
        time.sleep(_seconds_to_next_monitor_slot())
        if _RUNNING:
            try:_send_15m_system_monitor(datetime.now(UTC).astimezone(BANGKOK))
            except Exception as exc:_notify_error(exc,"ระบบแจ้งเตือน Telegram ทุก 15 นาที")

def run_scan_cycle():
    global _LAST_CYCLE_AT,_LAST_RESULTS,_CYCLE_COUNT
    now_utc=datetime.now(UTC); now_bkk=now_utc.astimezone(BANGKOK); results=[]; _CYCLE_COUNT+=1; _LAST_CYCLE_AT=now_utc.isoformat(); logger.warning("[V11 SCHEDULER] Scan cycle #%s started at %s Bangkok symbols=%s",_CYCLE_COUNT,now_bkk.strftime('%Y-%m-%d %H:%M:%S'),_symbols())
    for symbol in _symbols():
        try:
            opened,session=_asset_market_status(symbol,now_utc)
            if not opened:results.append({"status":"market_closed","symbol":symbol,"session":session,"live_orders_allowed":False});continue
            frame=live_scanner_v11._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            if frame.empty:raise RuntimeError("NO_CLOSED_CANDLES")
            closed_key=str(frame.iloc[-1].datetime)
            if _LAST_CLOSED_CANDLE.get(symbol)==closed_key:results.append({"status":"waiting_new_candle","symbol":symbol,"closed_candle":closed_key});continue
            result=live_scanner_v11.scan_once(symbol); _LAST_CLOSED_CANDLE[symbol]=closed_key; result.update({"trigger":"NEW_CLOSED_M5_CANDLE","candle_consumed":True,"market_session":session,"engine_version":ENGINE_VERSION}); results.append(result); logger.warning("[V11 SCHEDULER] %s result status=%s strategy=%s side=%s",symbol,result.get("status"),result.get("strategy"),result.get("side"))
        except Exception as exc:_notify_error(exc,f"การสแกน {symbol}");results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})
    _LAST_RESULTS=results; return results

def _seconds_to_next_boundary():return max(1,300-(datetime.now(UTC).timestamp()%300))
def _loop():
    logger.warning("[V11 SCHEDULER] Thread entered; waiting for next closed M5 boundary")
    while _RUNNING:
        time.sleep(_seconds_to_next_boundary())
        if _RUNNING:
            try:run_scan_cycle()
            except Exception as exc:_notify_error(exc,"รอบการทำงาน V11 scheduler")
def start():
    global _RUNNING,_THREAD,_MONITOR_THREAD,_STARTED_AT
    if _RUNNING and _THREAD and _THREAD.is_alive():return False
    _RUNNING=True; _STARTED_AT=datetime.now(UTC).isoformat(); _THREAD=threading.Thread(target=_loop,name="v11-m5-scheduler",daemon=True); _THREAD.start(); _MONITOR_THREAD=threading.Thread(target=_monitor_loop,name="v11-telegram-15m-monitor",daemon=True); _MONITOR_THREAD.start(); logger.warning("[V11 SCHEDULER] STARTED engine=%s interval=%ss symbols=%s timezone=Asia/Bangkok",ENGINE_VERSION,_interval_seconds(),_symbols()); return True
def stop():
    global _RUNNING; _RUNNING=False
def status():
    try:import live_price;live=live_price.status()
    except Exception as exc:live={"running":False,"error":str(exc)}
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"test_slots":"00,15,30,45","timezone":"Asia/Bangkok","provider":"LSE","engine_version":ENGINE_VERSION,"scanner":"live_scanner_v11","multi_strategy":True,"strategies":["TREND_PULLBACK","LIQUIDITY_SWEEP","MSS_PULLBACK","BREAKOUT_RETEST","OPENING_RANGE_BREAKOUT","VWAP_MEAN_REVERSION","SWEEP_MSS_FVG"],"timeframes":["5m","15m"],"started_at":_STARTED_AT,"last_cycle_at":_LAST_CYCLE_AT,"cycle_count":_CYCLE_COUNT,"last_results":_LAST_RESULTS,"live_price":live,"telegram_monitor_running":bool(_RUNNING and _MONITOR_THREAD and _MONITOR_THREAD.is_alive()),"telegram_monitor":"00,15,30,45 Asia/Bangkok","last_monitor_slot":_LAST_MONITOR_SLOT,"live_orders_allowed":False}
