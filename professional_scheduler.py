from __future__ import annotations
import logging,os,threading,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import professional_live_scanner as scanner
from professional_engine_core import ENGINE_VERSION

logger=logging.getLogger("professional_scheduler"); BANGKOK=ZoneInfo("Asia/Bangkok"); NEW_YORK=ZoneInfo("America/New_York"); UTC=timezone.utc
_RUNNING=False; _THREAD=None; _LAST_CLOSED={}; _LAST_RESULTS=[]; _CYCLE=0; _LAST_AT=None
SYMBOLS=("BTC","GOLD")

def _symbols(): return [x for x in dict.fromkeys(s.strip().upper() for s in os.getenv("LIVE_SIGNAL_SYMBOLS","BTC,GOLD").split(",")) if x in SYMBOLS]

def _market(symbol,now=None):
    now=now or datetime.now(UTC)
    if symbol=="BTC":return True,"OPEN_24_7"
    n=now.astimezone(NEW_YORK); m=n.hour*60+n.minute
    if n.weekday()==5:return False,"WEEKEND_CLOSED"
    if n.weekday()==6:return (m>=1080,"OPEN" if m>=1080 else "SUNDAY_CLOSED")
    if n.weekday()==4:return (m<1020,"OPEN" if m<1020 else "FRIDAY_CLOSED")
    if 1020<=m<1080:return False,"DAILY_BREAK"
    return True,"OPEN"

def run_scan_cycle():
    global _LAST_RESULTS,_LAST_AT,_CYCLE
    now=datetime.now(UTC); _CYCLE+=1; _LAST_AT=now.isoformat(); results=[]
    for symbol in _symbols():
        try:
            opened,session=_market(symbol,now)
            if not opened: results.append({"status":"market_closed","symbol":symbol,"session":session,"engine_version":ENGINE_VERSION}); continue
            frame=scanner._lse_frame(symbol,"5m",max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))))
            key=str(frame.iloc[-1].datetime)
            if _LAST_CLOSED.get(symbol)==key:
                results.append({"status":"waiting_new_candle","symbol":symbol,"closed_candle":key,"engine_version":ENGINE_VERSION}); continue
            result=scanner.scan_once(symbol); result.update({"trigger":"NEW_CLOSED_M5_CANDLE","candle_consumed":True,"market_session":session,"engine_version":ENGINE_VERSION,"timeframe_mode":"MTF:H1→M15→M5"}); results.append(result); _LAST_CLOSED[symbol]=key
        except Exception as exc:
            results.append({"status":"scan_error","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"engine_version":ENGINE_VERSION})
    _LAST_RESULTS=results; return results

def _loop():
    while _RUNNING:
        try: run_scan_cycle()
        except Exception: logger.exception("professional scheduler cycle failed")
        time.sleep(max(300,300-(int(datetime.now(UTC).timestamp())%300)+1))

def start():
    global _RUNNING,_THREAD
    if _RUNNING and _THREAD and _THREAD.is_alive():return False
    _RUNNING=True; _THREAD=threading.Thread(target=_loop,name="professional-decision-scheduler",daemon=True); _THREAD.start(); return True

def stop():
    global _RUNNING; _RUNNING=False

def status(): return {"running":bool(_RUNNING and _THREAD and _THREAD.is_alive()),"engine_version":ENGINE_VERSION,"scanner":"professional_live_scanner","symbols":_symbols(),"timezone":"Asia/Bangkok","timeframe_mode":"MTF:H1→M15→M5","cycle_count":_CYCLE,"last_cycle_at":_LAST_AT,"last_results":_LAST_RESULTS,"live_orders_allowed":False}
