from __future__ import annotations
import json, math, os, threading, logging
from flask import Flask, Response, request
from v11 import engine as v11_engine
from v11.validation import validate as validate_v11

app=Flask(__name__)
logger=logging.getLogger("v11_app")
SUPPORTED_SYMBOLS=("BTC/USDT","XAU/USDT")
SERVICE_LOCK=threading.RLock(); _SERVICES_STARTED=False
SCHEDULER_LOCK_FILE=os.getenv("V11_SCHEDULER_LOCK_FILE","/tmp/gold-m5-v11-scheduler.lock")

def _json_safe(value):
    if value is None or isinstance(value,(str,bool,int)): return value
    if isinstance(value,float): return value if math.isfinite(value) else None
    if isinstance(value,dict): return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,set)): return [_json_safe(v) for v in value]
    try:return _json_safe(value.item())
    except Exception: pass
    try:return _json_safe(value.tolist())
    except Exception:return str(value)

def _json_response(payload,status=200): return Response(json.dumps(_json_safe(payload),ensure_ascii=False,allow_nan=False),status=status,mimetype="application/json")

def _acquire_scheduler_lock():
    try:
        fd=os.open(SCHEDULER_LOCK_FILE,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        os.write(fd,str(os.getpid()).encode()); os.close(fd); return True
    except FileExistsError:
        try:
            with open(SCHEDULER_LOCK_FILE,"r",encoding="utf-8") as f: pid=int(f.read().strip())
            os.kill(pid,0); return False
        except Exception:
            try: os.unlink(SCHEDULER_LOCK_FILE)
            except OSError: return False
            return _acquire_scheduler_lock()

def _start_runtime_services():
    global _SERVICES_STARTED
    if _SERVICES_STARTED or os.getenv("ENABLE_SIGNAL_SCHEDULER","true").lower()!="true":
        return
    with SERVICE_LOCK:
        if _SERVICES_STARTED: return
        if not _acquire_scheduler_lock():
            logger.warning("[V11 STARTUP] Scheduler lock already owned by another process; this worker will not start runtime services")
            _SERVICES_STARTED=True
            return
        try:
            import live_price
            live_started=live_price.start()
            import scheduler_v11 as scheduler
            scheduler_started=scheduler.start()
            live_status=live_price.status()
            scheduler_status=scheduler.status()
            logger.warning("[V11 STARTUP] ENGINE=%s SCHEDULER=%s LIVE_PRICE=%s PROVIDER=LSE",v11_engine.ENGINE_VERSION,"RUNNING" if scheduler_status.get("running") else "NOT_RUNNING","RUNNING" if live_status.get("running") else "NOT_RUNNING")
            logger.warning("[V11 STARTUP] scheduler_started=%s live_started=%s live_state=%s api_key=%s",scheduler_started,live_started,live_status.get("loop_state"),live_status.get("api_key_configured"))
            try:
                from startup_notify import send_startup_notification
                send_startup_notification(symbol="BTC + GOLD / LSE",engine_version=v11_engine.ENGINE_VERSION)
            except Exception as exc:
                logger.warning("[V11 STARTUP] Telegram startup notification failed: %s",exc)
            _SERVICES_STARTED=True
        except Exception:
            try: os.unlink(SCHEDULER_LOCK_FILE)
            except OSError: pass
            logger.exception("[V11 STARTUP] Runtime service startup failed")
            raise

@app.before_request
def ensure_runtime_services():
    try: _start_runtime_services()
    except Exception: logger.exception("[V11 STARTUP] ensure_runtime_services failed")

@app.route("/")
def health():
    try: import live_price; live=live_price.status()
    except Exception as exc: live={"running":False,"provider":"LSE","error":str(exc)}
    try: import scheduler_v11; scheduler=scheduler_v11.status()
    except Exception as exc: scheduler={"running":False,"error":str(exc)}
    return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":v11_engine.ENGINE_VERSION,"exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"timeframe":"M5 trigger + M15 trend","analysis_windows":{"M15_context_bars":100,"M5_setup_bars":50},"live_price":live,"scheduler":scheduler,"live_orders_allowed":False})

@app.route("/live-price")
def live_price_status():
    try: import live_price; payload=live_price.status(); payload["status"]="ok"; return _json_response(payload)
    except Exception as exc:return _json_response({"status":"live_price_error","provider":"LSE","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)

@app.route("/live-price/<symbol>")
def live_price_symbol(symbol):
    try:
        import live_price; value=live_price.get(symbol)
        if value is None:return _json_response({"status":"waiting","provider":"LSE","symbol":symbol.upper(),"message":"ยังไม่ได้รับ live tick จาก LSE"},202)
        return _json_response({"status":"ok","provider":"LSE","latest":value})
    except Exception as exc:return _json_response({"status":"live_price_error","provider":"LSE","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)

@app.route("/symbols")
def symbols():
    return _json_response({"status":"ok","engine_version":v11_engine.ENGINE_VERSION,"exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"mt5_symbols":{"BTC":os.getenv("MT5_BTC_SYMBOL","BTCUSD"),"GOLD":os.getenv("MT5_GOLD_SYMBOL","XAUUSD")},"timeframe":"M5 trigger + M15 trend","market_data":"LSE historical + LSE WebSocket live price","live_orders_allowed":False})

@app.route("/signal")
def live_signal():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper(); mapped="BTC" if symbol=="BTC/USDT" else "GOLD" if symbol=="XAU/USDT" else None
    if not mapped:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:
        import live_scanner_v11
        return _json_response(live_scanner_v11.scan_once(mapped))
    except Exception as exc:return _json_response({"status":"signal_error","engine_version":v11_engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False},502)

@app.route("/validation")
def validation():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper(); mapped="BTC" if symbol=="BTC/USDT" else "GOLD" if symbol=="XAU/USDT" else None
    if not mapped:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:bars=max(100,min(int(request.args.get("bars","1000")),1000))
    except Exception:return _json_response({"status":"error","message":"bars must be an integer between 100 and 1000","live_orders_allowed":False},400)
    try:
        import live_scanner_v11
        m5=live_scanner_v11._lse_frame(mapped,"5m",max(bars,100)); m15=live_scanner_v11._lse_frame(mapped,"15m",max(bars,100))
        report=validate_v11(m5,m15,mapped,limit=bars); report.update({"endpoint":"/validation","request":{"symbol":symbol,"bars":bars}})
        return _json_response(report)
    except Exception as exc:return _json_response({"status":"validation_error","engine_version":v11_engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)

@app.route("/validation-v92")
def validation_v92():
    return _json_response({"status":"deprecated","message":"Legacy V9.2 validation is intentionally isolated from V11. Use /validation.","engine_version":v11_engine.ENGINE_VERSION,"live_orders_allowed":False},410)

@app.route("/scheduler/status")
def scheduler_status():
    try: import scheduler_v11 as scheduler; return _json_response({"status":"ok",**scheduler.status()})
    except Exception as exc:return _json_response({"status":"scheduler_error","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)

try:
    import statistics_page; statistics_page.register(app)
except Exception:
    pass

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
