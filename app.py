from __future__ import annotations
import json,math,os,threading,logging
from datetime import datetime,timezone
from flask import Flask,Response,request
from zoneinfo import ZoneInfo
from professional_engine_core import ENGINE_VERSION
import professional_live_scanner as live_scanner
import professional_scheduler as scheduler

app=Flask(__name__); logger=logging.getLogger("production_v2_app")
SUPPORTED_SYMBOLS=("BTC/USDT","XAU/USDT"); SERVICE_LOCK=threading.RLock(); _SERVICES_STARTED=False
SCHEDULER_LOCK_FILE=os.getenv("PROFESSIONAL_SCHEDULER_LOCK_FILE","/tmp/production-v2-professional.lock"); UTC=timezone.utc; NEW_YORK=ZoneInfo("America/New_York")

def _json_safe(v):
    if v is None or isinstance(v,(str,bool,int)):return v
    if isinstance(v,float):return v if math.isfinite(v) else None
    if isinstance(v,dict):return {str(k):_json_safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple,set)):return [_json_safe(x) for x in v]
    try:return _json_safe(v.item())
    except Exception:return str(v)

def _json_response(payload,status=200):return Response(json.dumps(_json_safe(payload),ensure_ascii=False,allow_nan=False),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})

def _acquire_lock():
    try:
        fd=os.open(SCHEDULER_LOCK_FILE,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd);return True
    except FileExistsError:return False

def _gold_market_open(now=None):
    n=(now or datetime.now(UTC)).astimezone(NEW_YORK);m=n.hour*60+n.minute
    if n.weekday()==5:return False,"WEEKEND_CLOSED"
    if n.weekday()==6:return (m>=1080,"OPEN" if m>=1080 else "SUNDAY_CLOSED")
    if n.weekday()==4:return (m<1020,"OPEN" if m<1020 else "FRIDAY_CLOSED")
    if 1020<=m<1080:return False,"DAILY_BREAK"
    return True,"OPEN"

def _start_runtime_services():
    global _SERVICES_STARTED
    if _SERVICES_STARTED or os.getenv("ENABLE_SIGNAL_SCHEDULER","true").lower()!="true":return
    with SERVICE_LOCK:
        if _SERVICES_STARTED:return
        if not _acquire_lock(): _SERVICES_STARTED=True; return
        try:
            import live_price; live_price.start(); scheduler.start()
            try:
                import production_v2_monitor; production_v2_monitor.start()
            except Exception: logger.exception("Telegram monitor startup failed")
            _SERVICES_STARTED=True
        except Exception:
            try:os.unlink(SCHEDULER_LOCK_FILE)
            except OSError:pass
            raise

@app.before_request
def ensure_runtime_services():
    try:_start_runtime_services()
    except Exception:logger.exception("runtime startup failed")

@app.route("/health")
def health_check():return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":ENGINE_VERSION,"architecture":"E1→E2→E3→E4→E5→E6→E7→E8→E9","timeframe_mode":"MTF:H1→M15→M5","decision_authority":"E9"})
@app.route("/ping")
def ping():return Response("pong",mimetype="text/plain",headers={"Cache-Control":"no-store"})
@app.route("/")
def health():
    try:import live_price; live=live_price.status()
    except Exception as exc:live={"running":False,"provider":"LSE","error":str(exc)}
    return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":ENGINE_VERSION,"architecture":"E1→E2→E3→E4→E5→E6→E7→E8→E9","exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"timeframe":"MTF:H1→M15→M5","live_price":live,"scheduler":scheduler.status(),"live_orders_allowed":False})
@app.route("/live-price")
def live_price_status():
    try:import live_price; p=live_price.status();p["status"]="ok";return _json_response(p)
    except Exception as exc:return _json_response({"status":"live_price_error","error_type":type(exc).__name__,"message":str(exc)},502)
@app.route("/live-price/<symbol>")
def live_price_symbol(symbol):
    try:
        import live_price; value=live_price.get(symbol)
        return _json_response({"status":"ok" if value is not None else "waiting","latest":value,"symbol":symbol.upper()})
    except Exception as exc:return _json_response({"status":"live_price_error","error_type":type(exc).__name__,"message":str(exc)},502)
@app.route("/symbols")
def symbols():return _json_response({"status":"ok","engine_version":ENGINE_VERSION,"architecture":"E1→E2→E3→E4→E5→E6→E7→E8→E9","exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"timeframe":"MTF:H1→M15→M5","live_orders_allowed":False})
@app.route("/signal")
def live_signal():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper(); mapped="BTC" if symbol=="BTC/USDT" else "GOLD" if symbol=="XAU/USDT" else None
    if not mapped:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS)},400)
    if mapped=="GOLD":
        opened,session=_gold_market_open()
        if not opened:return _json_response({"status":"market_closed","symbol":symbol,"market_session":session,"engine_version":ENGINE_VERSION,"live_orders_allowed":False})
    try:return _json_response(live_scanner.scan_once(mapped))
    except Exception as exc:return _json_response({"status":"signal_error","engine_version":ENGINE_VERSION,"symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False},502)
@app.route("/validation")
def validation():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper(); mapped="BTC" if symbol=="BTC/USDT" else "GOLD" if symbol=="XAU/USDT" else None
    if not mapped:return _json_response({"status":"error","message":"Unsupported symbol"},400)
    try:bars=max(100,min(int(request.args.get("bars","200")),1000)); frame=live_scanner._lse_frame(mapped,"5m",bars); return _json_response({"status":"ok","engine_version":ENGINE_VERSION,"symbol":symbol,"bars":len(frame),"latest_closed_candle":str(frame.iloc[-1].datetime),"data_quality":"PASS"})
    except Exception as exc:return _json_response({"status":"validation_error","engine_version":ENGINE_VERSION,"symbol":symbol,"error_type":type(exc).__name__,"message":str(exc)},502)
@app.route("/scheduler/status")
def scheduler_status():return _json_response({"status":"ok",**scheduler.status()})
try:
    import statistics_page; statistics_page.register(app)
except Exception:pass
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
