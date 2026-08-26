from __future__ import annotations
import json,math,os,threading,logging
from datetime import datetime,timezone
from flask import Flask,Response,request
from zoneinfo import ZoneInfo
from v11 import engine as v12_engine
from v11.validation import validate as validate_v12
app=Flask(__name__);logger=logging.getLogger("v12_app");SUPPORTED_SYMBOLS=("BTC/USDT","XAU/USDT");SERVICE_LOCK=threading.RLock();_SERVICES_STARTED=False;SCHEDULER_LOCK_FILE=os.getenv("V12_SCHEDULER_LOCK_FILE","/tmp/gold-m5-v12-scheduler.lock");UTC=timezone.utc;NEW_YORK=ZoneInfo("America/New_York")
def _json_safe(value):
    if value is None or isinstance(value,(str,bool,int)):return value
    if isinstance(value,float):return value if math.isfinite(value) else None
    if isinstance(value,dict):return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,set)):return [_json_safe(v) for v in value]
    try:return _json_safe(value.item())
    except Exception:pass
    try:return _json_safe(value.tolist())
    except Exception:return str(value)
def _json_response(payload,status=200):return Response(json.dumps(_json_safe(payload),ensure_ascii=False,allow_nan=False),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})
def _acquire_scheduler_lock():
    try:
        fd=os.open(SCHEDULER_LOCK_FILE,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd);return True
    except FileExistsError:
        try:
            with open(SCHEDULER_LOCK_FILE,"r",encoding="utf-8") as f:pid=int(f.read().strip())
            os.kill(pid,0);return False
        except Exception:
            try:os.unlink(SCHEDULER_LOCK_FILE)
            except OSError:return False
            return _acquire_scheduler_lock()
def _gold_market_open(now_utc=None):
    now_utc=now_utc or datetime.now(UTC);ny=now_utc.astimezone(NEW_YORK);wd=ny.weekday();minutes=ny.hour*60+ny.minute
    if wd==5:return False,"WEEKEND_CLOSED"
    if wd==6:return (minutes>=1080,"OPEN" if minutes>=1080 else "SUNDAY_CLOSED")
    if wd==4:return (minutes<1020,"OPEN" if minutes<1020 else "FRIDAY_CLOSED")
    if 1020<=minutes<1080:return False,"DAILY_BREAK"
    return True,"OPEN"
def _startup_probe_worker():
    try:
        import live_scanner_v11;results={};now_utc=datetime.now(UTC)
        for symbol in ("BTC","GOLD"):
            try:
                if symbol=="GOLD":
                    opened,session=_gold_market_open(now_utc)
                    if not opened:
                        results[symbol]=False;logger.warning("[PRODUCTION-V2 STARTUP] LSE_REST_PROBE %s=SKIPPED session=%s",symbol,session);continue
                frames=live_scanner_v11._load_frames(symbol);ok=all(frames.get(k) is not None and not frames[k].empty for k in ("1h","15m","5m"));results[symbol]=ok;logger.warning("[PRODUCTION-V2 STARTUP] LSE_REST_PROBE %s=%s H1=%s M15=%s M5=%s","READY" if ok else "FAILED",len(frames.get("1h",[])),len(frames.get("15m",[])),len(frames.get("5m",[])))
            except Exception as exc:results[symbol]=False;logger.error("[PRODUCTION-V2 STARTUP] LSE_REST_PROBE %s=FAILED error=%s",symbol,exc)
        logger.warning("[PRODUCTION-V2 STARTUP] LSE REST readiness probe BTC=%s GOLD=%s","READY" if results.get("BTC") else "FAILED","READY" if results.get("GOLD") else "SKIPPED/CLOSED")
    except Exception:logger.exception("[PRODUCTION-V2 STARTUP] LSE REST readiness probe failed")
def _start_runtime_services():
    global _SERVICES_STARTED
    if _SERVICES_STARTED or os.getenv("ENABLE_SIGNAL_SCHEDULER","true").lower()!="true":return
    with SERVICE_LOCK:
        if _SERVICES_STARTED:return
        if not _acquire_scheduler_lock():logger.warning("[PRODUCTION-V2 STARTUP] Scheduler lock already owned by another process; this worker will not start runtime services");_SERVICES_STARTED=True;return
        try:
            import live_price;live_started=live_price.start()
            import scheduler_v11 as scheduler;scheduler_started=scheduler.start();live_status=live_price.status();scheduler_status=scheduler.status()
            logger.warning("[PRODUCTION-V2 STARTUP] ENGINE=%s SCHEDULER=%s LIVE_PRICE=%s PROVIDER=LSE",v12_engine.ENGINE_VERSION,"RUNNING" if scheduler_status.get("running") else "NOT_RUNNING","RUNNING" if live_status.get("running") else "NOT_RUNNING")
            logger.warning("[PRODUCTION-V2 STARTUP] scheduler_started=%s live_started=%s live_state=%s api_key=%s",scheduler_started,live_started,live_status.get("loop_state"),live_status.get("api_key_configured"))
            try:
                import production_v2_monitor;monitor_started=production_v2_monitor.start();logger.warning("[PRODUCTION-V2 STARTUP] Telegram monitor=%s", "RUNNING" if monitor_started else "ALREADY_RUNNING")
            except Exception as exc:
                logger.warning("[PRODUCTION-V2 STARTUP] Telegram monitor failed to start: %s",exc)
            threading.Thread(target=_startup_probe_worker,name="production-v2-lse-startup-probe",daemon=True).start()
            try:
                from startup_notify import send_startup_notification;send_startup_notification(symbol="BTC + GOLD / LSE",engine_version=v12_engine.ENGINE_VERSION)
            except Exception as exc:logger.warning("[PRODUCTION-V2 STARTUP] Telegram startup notification failed: %s",exc)
            _SERVICES_STARTED=True
        except Exception:
            try:os.unlink(SCHEDULER_LOCK_FILE)
            except OSError:pass
            logger.exception("[PRODUCTION-V2 STARTUP] Runtime service startup failed");raise
@app.before_request
def ensure_runtime_services():
    try:_start_runtime_services()
    except Exception:logger.exception("[PRODUCTION-V2 STARTUP] ensure_runtime_services failed")
@app.route("/health")
def health_check():return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":v12_engine.ENGINE_VERSION,"timeframe_mode":"MTF:H1→M15→M5"})
@app.route("/ping")
def ping():return Response("pong",mimetype="text/plain",headers={"Cache-Control":"no-store"})
@app.route("/")
def health():
    try:import live_price;live=live_price.status()
    except Exception as exc:live={"running":False,"provider":"LSE","error":str(exc)}
    try:import scheduler_v11;scheduler=scheduler_v11.status()
    except Exception as exc:scheduler={"running":False,"error":str(exc)}
    try:import production_v2_monitor;telegram_monitor=production_v2_monitor.status()
    except Exception as exc:telegram_monitor={"running":False,"error":str(exc)}
    return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":v12_engine.ENGINE_VERSION,"exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"timeframe":"MTF:H1→M15→M5","analysis_windows":{"H1_context_bars":100,"M15_context_bars":100,"M5_context_bars":100,"entry_trigger":"M5"},"live_price":live,"scheduler":scheduler,"telegram_monitor":telegram_monitor,"live_orders_allowed":False})
@app.route("/live-price")
def live_price_status():
    try:import live_price;payload=live_price.status();payload["status"]="ok";return _json_response(payload)
    except Exception as exc:return _json_response({"status":"live_price_error","provider":"LSE","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
@app.route("/live-price/<symbol>")
def live_price_symbol(symbol):
    try:
        import live_price;value=live_price.get(symbol)
        if value is None:return _json_response({"status":"waiting","provider":"LSE","symbol":symbol.upper(),"message":"ยังไม่ได้รับ live tick จาก LSE"},202)
        return _json_response({"status":"ok","provider":"LSE","latest":value})
    except Exception as exc:return _json_response({"status":"live_price_error","provider":"LSE","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
@app.route("/symbols")
def symbols():return _json_response({"status":"ok","engine_version":v12_engine.ENGINE_VERSION,"exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"mt5_symbols":{"BTC":os.getenv("MT5_BTC_SYMBOL","BTCUSD"),"GOLD":os.getenv("MT5_GOLD_SYMBOL","XAUUSD")},"timeframe":"MTF:H1→M15→M5","market_data":"LSE historical H1/M15/M5 + LSE WebSocket live price","live_orders_allowed":False})
@app.route("/signal")
def live_signal():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper();mapped="BTC" if symbol=="BTC/USDT" else "GOLD" if symbol=="XAU/USDT" else None
    if not mapped:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    if mapped=="GOLD":
        opened,session=_gold_market_open()
        if not opened:return _json_response({"status":"market_closed","symbol":symbol,"market_session":session,"message":"GOLD market is closed; no signal scan performed","live_orders_allowed":False},200)
    try:
        import live_scanner_v11;return _json_response(live_scanner_v11.scan_once(mapped))
    except Exception as exc:return _json_response({"status":"signal_error","engine_version":v12_engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False},502)
@app.route("/validation")
def validation():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper();mapped="BTC" if symbol=="BTC/USDT" else "GOLD" if symbol=="XAU/USDT" else None
    if not mapped:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:bars=max(100,min(int(request.args.get("bars","1000")),1000))
    except Exception:return _json_response({"status":"error","message":"bars must be an integer between 100 and 1000","live_orders_allowed":False},400)
    try:import live_scanner_v11;m5=live_scanner_v11._lse_frame(mapped,"5m",max(bars,100));report=validate_v12(m5,None,mapped,limit=bars);report.update({"endpoint":"/validation","request":{"symbol":symbol,"bars":bars},"timeframe_mode":"MTF:H1→M15→M5","note":"Validation endpoint remains M5 data-quality validation; live signal path uses H1/M15/M5."});return _json_response(report)
    except Exception as exc:return _json_response({"status":"validation_error","engine_version":v12_engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
@app.route("/validation-v92")
def validation_v92():return _json_response({"status":"deprecated","message":"Legacy validation is intentionally isolated from V12. Use /validation.","engine_version":v12_engine.ENGINE_VERSION,"live_orders_allowed":False},410)
@app.route("/scheduler/status")
def scheduler_status():
    try:import scheduler_v11 as scheduler;return _json_response({"status":"ok",**scheduler.status()})
    except Exception as exc:return _json_response({"status":"scheduler_error","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
try:
    import statistics_page;statistics_page.register(app)
except Exception:pass
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
