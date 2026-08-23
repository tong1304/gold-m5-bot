import os
import json
import math
import threading
import logging
from urllib.parse import parse_qs
from flask import Response, request
import engine_v9_2 as engine
engine.base=engine
os.environ["LIVE_SIGNAL_SYMBOLS"]="BTC,GOLD"
SUPPORTED_SYMBOLS=("BTC/USDT","XAU/USDT")
SYMBOL_LOCK=threading.RLock(); SERVICE_LOCK=threading.RLock(); _SERVICES_STARTED_PID=None; logger=logging.getLogger(__name__)
BASE={"BTC/USDT":{"MINIMUM_ATR":float(os.getenv("BTC_MINIMUM_ATR","0")),"MIN_STOP_ATR":float(os.getenv("BTC_MIN_STOP_ATR","0")),"MAX_STOP_ATR":float(os.getenv("BTC_MAX_STOP_ATR","4.0")),"SPREAD":float(os.getenv("BTC_SPREAD","5.0")),"SLIPPAGE":float(os.getenv("BTC_SLIPPAGE","2.0")),"HISTORY_POINTS":int(os.getenv("BTC_HISTORY_POINTS","200"))},"XAU/USDT":{"MINIMUM_ATR":float(os.getenv("XAU_MINIMUM_ATR","0")),"MIN_STOP_ATR":float(os.getenv("XAU_MIN_STOP_ATR","0")),"MAX_STOP_ATR":float(os.getenv("XAU_MAX_STOP_ATR","4.0")),"SPREAD":float(os.getenv("XAU_SPREAD","0.50")),"SLIPPAGE":float(os.getenv("XAU_SLIPPAGE","0.20")),"HISTORY_POINTS":int(os.getenv("XAU_HISTORY_POINTS","200"))}}
_original_risk_guard=engine.evaluate_live_risk_guard
def _runtime_risk_guard(**kwargs): return _original_risk_guard(**kwargs,price_jump_atr=float(os.getenv("LIVE_PRICE_JUMP_ATR","0")),daily_loss_r=float(os.getenv("LIVE_DAILY_LOSS_R","0")),consecutive_losses=int(os.getenv("LIVE_CONSECUTIVE_LOSSES","0")),trades_today=int(os.getenv("LIVE_TRADES_TODAY","0")),slippage=float(os.getenv("LIVE_SLIPPAGE",str(engine.SLIPPAGE))))
engine.evaluate_live_risk_guard=_runtime_risk_guard
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
def activate(symbol):
    symbol=(symbol or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"Unsupported symbol: {symbol}")
    cfg=BASE[symbol]
    for target in (engine,engine.base):
        target.SYMBOL=symbol; target.MINIMUM_ATR=cfg["MINIMUM_ATR"]; target.MIN_STOP_ATR=cfg["MIN_STOP_ATR"]; target.MAX_STOP_ATR=cfg["MAX_STOP_ATR"]; target.SPREAD=cfg["SPREAD"]; target.SLIPPAGE=cfg["SLIPPAGE"]; target.SIGNAL_HISTORY_POINTS=cfg["HISTORY_POINTS"]; target.MIN_RISK_REWARD=1.0; target.RISK_REWARD=max(float(os.getenv("RISK_REWARD","1.0")),1.0)
    return symbol
def _start_runtime_services():
    global _SERVICES_STARTED_PID
    pid=os.getpid()
    if _SERVICES_STARTED_PID==pid:return
    with SERVICE_LOCK:
        if _SERVICES_STARTED_PID==pid:return
        if os.getenv("ENABLE_SIGNAL_SCHEDULER","true").strip().lower()!="true": _SERVICES_STARTED_PID=pid; return
        try:
            import live_price; live_price.start(); import scheduler; scheduler.start(); logger.info("V9.2 Signal Scheduler + Live Price started in Gunicorn worker pid=%s",pid)
            try:
                from startup_notify import send_startup_notification; send_startup_notification(symbol="BTC + GOLD / LSE",engine_version=engine.ENGINE_VERSION)
            except Exception: logger.exception("Startup notification failed")
            _SERVICES_STARTED_PID=pid
        except Exception as exc: logger.exception("V9.2 Runtime services failed to start: %s",exc)
@engine.app.before_request
def _ensure_runtime_services(): _start_runtime_services()
@engine.app.route("/")
def health():
    try: import live_price; live=live_price.status()
    except Exception as exc: live={"running":False,"provider":"LSE","transport":"WebSocket","error":str(exc)}
    return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":"V9.2","exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"timeframe":"M5 trigger + H1/M15 confirmation","live_price":live,"live_orders_allowed":False})
@engine.app.route("/live-price")
def live_price_status():
    try: import live_price; payload=live_price.status(); payload["status"]="ok"; return _json_response(payload)
    except Exception as exc:return _json_response({"status":"live_price_error","provider":"LSE","transport":"WebSocket","error_type":type(exc).__name__,"message":str(exc)},502)
@engine.app.route("/live-price/<symbol>")
def live_price_symbol(symbol):
    try:
        import live_price; value=live_price.get(symbol)
        if value is None:return _json_response({"status":"waiting","provider":"LSE","transport":"WebSocket","symbol":symbol.upper(),"message":"ยังไม่ได้รับ live tick จาก LSE"},202)
        return _json_response({"status":"ok","provider":"LSE","transport":"WebSocket","latest":value})
    except Exception as exc:return _json_response({"status":"live_price_error","provider":"LSE","transport":"WebSocket","error_type":type(exc).__name__,"message":str(exc)},502)
@engine.app.route("/symbols")
def symbols():return _json_response({"status":"ok","engine_version":"V9.2","exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"mt5_symbols":{"BTC":os.getenv("MT5_BTC_SYMBOL","BTCUSD"),"GOLD":os.getenv("MT5_GOLD_SYMBOL","XAUUSD")},"timeframe":"M5 trigger + H1/M15 confirmation","market_data":"LSE historical + LSE WebSocket live price","live_orders_allowed":False})
@engine.app.route("/signal")
def live_signal():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:
        import live_scanner_v9_2
        with SYMBOL_LOCK: activate(symbol); return _json_response(live_scanner_v9_2.scan_once("BTC" if symbol=="BTC/USDT" else "GOLD"))
    except Exception as exc:return _json_response({"status":"signal_error","engine_version":engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False},502)
@engine.app.route("/validation")
def validation():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:bars=max(100,min(int(request.args.get("bars","1000")),1000))
    except Exception:return _json_response({"status":"error","message":"bars must be an integer between 100 and 1000","live_orders_allowed":False},400)
    try:
        import validate_v5
        with SYMBOL_LOCK: activate(symbol); report=validate_v5.run(symbol,bars)
        report["endpoint"]="/validation"; report["request"]={"symbol":symbol,"bars":bars}; report["live_orders_allowed"]=False; return _json_response(report)
    except Exception as exc:return _json_response({"status":"validation_error","engine_version":engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
@engine.app.route("/validation-v92")
def validation_v92():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:return _json_response({"status":"error","message":f"Unsupported symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:bars=max(150,min(int(request.args.get("bars","1000")),1000))
    except Exception:return _json_response({"status":"error","message":"bars must be an integer between 150 and 1000","live_orders_allowed":False},400)
    try:
        import validate_v9_2
        with SYMBOL_LOCK:
            activate(symbol); report=validate_v9_2.run(symbol,bars)
        report["endpoint"]="/validation-v92"; report["request"]={"symbol":symbol,"bars":bars}; report["live_orders_allowed"]=False
        return _json_response(report)
    except Exception as exc:return _json_response({"status":"validation_error","engine_version":engine.ENGINE_VERSION,"exchange":"LSE","symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
@engine.app.route("/scheduler/status")
def scheduler_status():
    try:import scheduler; return _json_response({"status":"ok",**scheduler.status()})
    except Exception as exc:return _json_response({"status":"scheduler_error","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)
try:
    import statistics_page; statistics_page.register(engine.app)
except Exception: logger.exception("Failed to register Signal Statistics routes")
class MultiSymbolMiddleware:
    def __init__(self,application):self.application=application
    def __call__(self,environ,start_response):
        requested=parse_qs(environ.get("QUERY_STRING",""),keep_blank_values=True).get("symbol",["BTC/USDT"])[0]
        with SYMBOL_LOCK:
            try:activate(requested); return self.application(environ,start_response)
            except ValueError as exc:
                body=json.dumps(_json_safe({"status":"error","engine_version":"V9.2","symbol":requested,"message":str(exc),"live_orders_allowed":False})).encode(); start_response("400 BAD REQUEST",[("Content-Type","application/json"),("Content-Length",str(len(body)))]); return [body]
app=MultiSymbolMiddleware(engine.app)
if __name__=="__main__":
    from werkzeug.serving import run_simple; run_simple("0.0.0.0",int(os.getenv("PORT","10000")),app)