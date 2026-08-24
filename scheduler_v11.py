from __future__ import annotations
import logging,os,threading,time
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from v11.telegram import send_telegram
import live_scanner_v11
logger=logging.getLogger("signal_scheduler");ENGINE_VERSION="12.1-M5-ONLY-REGIME-8-ENGINE-REENTRY";BANGKOK=ZoneInfo("Asia/Bangkok");UTC=timezone.utc;DISPLAY_SYMBOLS=("BTC","GOLD");_RUNNING=False;_THREAD=None;_MONITOR_THREAD=None;_LAST_CLOSED_CANDLE={};_LAST_MONITOR_SLOT=None;_STARTED_AT=None;_LAST_CYCLE_AT=None;_LAST_RESULTS=[];_CYCLE_COUNT=0
STRATEGIES=["E1_TREND","E2_TREND_PULLBACK","E3_BREAKOUT","E4_BREAKOUT_RETEST","E5_MOMENTUM","E6_MEAN_REVERSION","E7_LIQUIDITY_REVERSAL","E8_RANGE"]
def _interval_seconds():
    try:return max(300,int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS","300")))
    except ValueError:return 300
def _symbols():return [s for s in dict.fromkeys(x.strip().upper() for x in os.getenv("LIVE_SIGNAL_SYMBOLS","BTC,GOLD").split(",")) if s in DISPLAY_SYMBOLS]
def _asset_market_status(symbol,now_utc=None):
    now_utc=now_utc or datetime.now(UTC)
    if symbol=="BTC":return True,"OPEN_24_7"
    wd=now_utc.weekday();t=now_utc.time()
    if symbol!="GOLD":return False,"UNKNOWN_MARKET_SESSION"
    if wd==5:return False,"WEEKEND_CLOSED"
    if wd==6:return (t.hour>=23,"OPEN" if t.hour>=23 else "SUNDAY_CLOSED")
    if wd==4:return (t.hour<22,"OPEN" if t.hour<22 else "FRIDAY_CLOSED")
    if 22<=t.hour<23:return False,"DAILY_BREAK"
    return True,"OPEN"
def _notify_error(exc,context):
    try:return send_telegram(f"❌ <b>เกิดข้อผิดพลาดในระบบ V12.1 M5-only</b>\n\n🕐 {datetime.now(UTC).astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M:%S')} (ประเทศไทย)\n📍 {context}\n🔴 {type(exc).__name__}: {exc}\n\n🛑 ระบบจะไม่เปิดออเดอร์อัตโนมัติ")
    except Exception:return None
def _fmt_price(value):
    try:return f"{float(value):,.2f}" if float(value)>0 else "N/A"
    except (TypeError,ValueError):return "N/A"
def _live_price_line(symbol):
    try:
        import live_price;tick=live_price.get(symbol);label="₿ BTC" if symbol=="BTC" else "🟠 GOLD";return f"{label}: <b>{_fmt_price(tick.get('price')) if tick else 'N/A'}</b>"
    except Exception:return f"{'₿ BTC' if symbol=='BTC' else '🟠 GOLD'}: <b>N/A</b>"
def _send_15m_system_monitor(now_bkk=None):
    global _LAST_MONITOR_SLOT
    now_bkk=now_bkk or datetime.now(UTC).astimezone(BANGKOK)
    if now_bkk.minute not in (0,15,30,45):return False
    slot=now_bkk.strftime("%Y-%m-%d %H:%M")
    if slot==_LAST_MONITOR_SLOT:return False
    try:
        import live_price;status=live_price.status();connected="เชื่อมต่อแล้ว" if status.get("connected") else "ขาดการเชื่อมต่อ";authenticated="ยืนยันตัวตนแล้ว" if status.get("authenticated") else "ยังไม่ยืนยันตัวตน";ticks=status.get("ticks_received",0);msg=(f"🟢 <b>สถานะระบบ V12.1 M5-only</b>\n\n🕐 {now_bkk.strftime('%d/%m/%Y %H:%M:%S')} (ประเทศไทย)\n⚙️ Engine: <b>{ENGINE_VERSION}</b>\n🧠 Architecture: <b>M5 REGIME + 8 ENGINES + RE-ENTRY</b>\n⏱ Scheduler: <b>ทำงานอยู่</b>\n📡 LSE: <b>{connected}</b>\n🔐 Authentication: <b>{authenticated}</b>\n📥 Live ticks: <b>{ticks:,}</b>\n\n📊 <b>ราคาสินทรัพย์ปัจจุบัน</b>\n{_live_price_line('GOLD')}\n{_live_price_line('BTC')}\n\nℹ️ แจ้งเตือนสถานะระบบ ไม่ใช่สัญญาณ BUY/SELL");result=send_telegram(msg);_LAST_MONITOR_SLOT=slot;logger.warning("[V12 TELEGRAM] แจ้งสถานะทุก 15 นาที slot=%s result=%s",slot,result);return True
    except Exception as exc:logger.warning("[V12 TELEGRAM] แจ้งสถานะ 15 นาทีไม่สำเร็จ: %s",exc);return False
def _seconds_to_next_monitor_slot():
    now=datetime.now(UTC).astimezone(BANGKOK);minute=((now.minute//15)+1)*15;target=(now+timedelta(hours=1)).replace(minute=0,second=0,microsecond=0) if minute>=60 else now.replace(minute=minute,second=0,microsecond=0);return max(.5,(target-now).total_seconds())
def _monitor_loop():
    logger.warning("[V12 TELEGRAM] เริ่ม Monitor ทุก 15 นาที timezone=Asia/Bangkok slots=00,15,30,45")
    while _RUNNING:
        time.sleep(_seconds_to_next_monitor_slot())
        if _RUNNING:_send_15m_system_monitor(datetime.now(UTC).astimezone(BANGKOK))
def run_scan_cycle():
    global _LAST_CYCLE_AT,_LAST_RESULTS,_CYCLE_COUNT
    now_utc=datetime.now(UTC);now_bkk=now_utc.astimezone(BANGKOK);results=[];_CYCLE_COUNT+=1;_LAST_CYCLE_AT=now_utc.isoformat();logger.warning("[V12 SCHEDULER] Scan cycle #%s started at %s Bangkok symbols=%s mode=M5-only",_CYCLE_COUNT,now_bkk.strftime('%Y-%m-%d %H:%M:%S'),_symbols())
    for symbol in _symbols():
        try:
            opened,session=_asset_market_status(symbol,now_utc)
            if not opened:results.append({"status":"market_closed","symbol":symbol,"session":session,"live_orders_allowed":False});continue
            frame=live_scanner_v11._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            if frame.empty:raise RuntimeError("NO_CLOSED_M5_CANDLES")
            closed_key=str(frame.iloc[-1].datetime)
            if _LAST_CLOSED_CANDLE.get(symbol)==closed_key:results.append({"status":"waiting_new_candle","symbol":symbol,"closed_candle":closed_key});continue
            result=live_scanner_v11.scan_once(symbol);_LAST_CLOSED_CANDLE[symbol]=closed_key;result.update({"trigger":"NEW_CLOSED_M5_CANDLE","candle_consumed":True,"market_session":session,"engine_version":ENGINE_VERSION,"timeframe_mode":"M5-only"});results.append(result);logger.warning("[V12 SCHEDULER] %s result status=%s strategy=%s side=%s",symbol,result.get("status"),result.get("strategy"),result.get("signal"))
        except Exception as exc:_notify_error(exc,f"การสแกน {symbol}");results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})
    _LAST_RESULTS=results;return results
def _seconds_to_next_boundary():
    # M5 boundaries are aligned to UTC epoch. Add a small grace period so the
    # newly closed candle is fully available from LSE before the scan begins.
    remaining=300-(datetime.now(UTC).timestamp()%300)
    return max(0.5,remaining+1.0)
def _loop():
    logger.warning("[V12 SCHEDULER] Thread entered; performing initial M5 scan on latest closed candle")
    # Do not wait five minutes after every Render restart. The scanner itself
    # selects the latest CLOSED M5 candle, so an immediate startup scan is safe.
    if _RUNNING:
        try:run_scan_cycle()
        except Exception as exc:logger.exception("[V12 SCHEDULER] Initial scan failed: %s",exc)
    while _RUNNING:
        wait=_seconds_to_next_boundary();logger.warning("[V12 SCHEDULER] Waiting %.1fs for next closed M5 boundary",wait);time.sleep(wait)
        if _RUNNING:
            try:run_scan_cycle()
            except Exception as exc:logger.exception("[V12 SCHEDULER] Scheduled scan failed: %s",exc)
def start():
    global _RUNNING,_THREAD,_MONITOR_THREAD,_STARTED_AT
    if _RUNNING and _THREAD and _THREAD.is_alive():return False
    _RUNNING=True;_STARTED_AT=datetime.now(UTC).isoformat();_THREAD=threading.Thread(target=_loop,name="v12-m5-scheduler",daemon=True);_THREAD.start();_MONITOR_THREAD=threading.Thread(target=_monitor_loop,name="v12-telegram-15m-monitor",daemon=True);_MONITOR_THREAD.start();logger.warning("[V12 SCHEDULER] STARTED engine=%s interval=%ss symbols=%s timezone=Asia/Bangkok mode=M5-only",ENGINE_VERSION,_interval_seconds(),_symbols());return True
def stop():
    global _RUNNING;_RUNNING=False
def status():
    try:import live_price;live=live_price.status()
    except Exception as exc:live={"running":False,"error":str(exc)}
    return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"interval_seconds":_interval_seconds(),"symbols":_symbols(),"monitor_slots":"00,15,30,45","timezone":"Asia/Bangkok","provider":"LSE","engine_version":ENGINE_VERSION,"scanner":"live_scanner_v11","multi_strategy":True,"strategies":STRATEGIES,"timeframes":["M5"],"started_at":_STARTED_AT,"last_cycle_at":_LAST_CYCLE_AT,"cycle_count":_CYCLE_COUNT,"last_results":_LAST_RESULTS,"live_price":live,"telegram_monitor_running":bool(_RUNNING and _MONITOR_THREAD and _MONITOR_THREAD.is_alive()),"telegram_monitor":"00,15,30,45 Asia/Bangkok","last_monitor_slot":_LAST_MONITOR_SLOT,"live_orders_allowed":False}
