import os
import json
import math
import threading
import logging
from urllib.parse import parse_qs
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Response, request
import engine_v9_core as engine
os.environ["LIVE_SIGNAL_SYMBOLS"] = "BTC,GOLD"
SUPPORTED_SYMBOLS = ("BTC/USDT", "XAU/USDT")
SYMBOL_LOCK = threading.RLock(); SERVICE_LOCK = threading.RLock(); _SERVICES_STARTED_PID = None; logger = logging.getLogger(__name__)
BASE = {"BTC/USDT": {"MINIMUM_ATR": float(os.getenv("BTC_MINIMUM_ATR", "0")), "MIN_STOP_ATR": float(os.getenv("BTC_MIN_STOP_ATR", "0")), "MAX_STOP_ATR": float(os.getenv("BTC_MAX_STOP_ATR", "4.0")), "SPREAD": float(os.getenv("BTC_SPREAD", "5.0")), "SLIPPAGE": float(os.getenv("BTC_SLIPPAGE", "2.0")), "HISTORY_POINTS": int(os.getenv("BTC_HISTORY_POINTS", "200"))}, "XAU/USDT": {"MINIMUM_ATR": float(os.getenv("XAU_MINIMUM_ATR", "0")), "MIN_STOP_ATR": float(os.getenv("XAU_MIN_STOP_ATR", "0")), "MAX_STOP_ATR": float(os.getenv("XAU_MAX_STOP_ATR", "4.0")), "SPREAD": float(os.getenv("XAU_SPREAD", "0.50")), "SLIPPAGE": float(os.getenv("XAU_SLIPPAGE", "0.20")), "HISTORY_POINTS": int(os.getenv("XAU_HISTORY_POINTS", "200"))}}
_original_risk_guard = engine.evaluate_live_risk_guard
def _runtime_risk_guard(**kwargs): return _original_risk_guard(**kwargs, price_jump_atr=float(os.getenv("LIVE_PRICE_JUMP_ATR", "0")), daily_loss_r=float(os.getenv("LIVE_DAILY_LOSS_R", "0")), consecutive_losses=int(os.getenv("LIVE_CONSECUTIVE_LOSSES", "0")), trades_today=int(os.getenv("LIVE_TRADES_TODAY", "0")), slippage=float(os.getenv("LIVE_SLIPPAGE", str(engine.SLIPPAGE))))
engine.evaluate_live_risk_guard = _runtime_risk_guard
def _f(value, default=0.0):
    try:
        value=float(value); return default if not math.isfinite(value) else value
    except Exception: return default
def activate(symbol):
    symbol=(symbol or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"Unsupported symbol: {symbol}")
    cfg=BASE[symbol]
    for target in (engine, engine.base):
        target.SYMBOL=symbol; target.MINIMUM_ATR=cfg["MINIMUM_ATR"]; target.MIN_STOP_ATR=cfg["MIN_STOP_ATR"]; target.MAX_STOP_ATR=cfg["MAX_STOP_ATR"]; target.SPREAD=cfg["SPREAD"]; target.SLIPPAGE=cfg["SLIPPAGE"]; target.SIGNAL_HISTORY_POINTS=cfg["HISTORY_POINTS"]; target.MIN_RISK_REWARD=max(float(os.getenv("MIN_RISK_REWARD","2.0")),2.0); target.RISK_REWARD=max(float(os.getenv("RISK_REWARD","2.0")),2.0)
    return symbol
def _json_safe(value):
    if value is None or isinstance(value,(str,bool,int)): return value
    if isinstance(value,float): return value if math.isfinite(value) else None
    if isinstance(value,dict): return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,set)): return [_json_safe(v) for v in value]
    try: return _json_safe(value.item())
    except (AttributeError,TypeError,ValueError): pass
    try: return _json_safe(value.tolist())
    except (AttributeError,TypeError,ValueError): return str(value)
def _json_response(payload,status=200): return Response(json.dumps(_json_safe(payload),ensure_ascii=False,allow_nan=False),status=status,mimetype="application/json")
def _start_runtime_services():
    global _SERVICES_STARTED_PID
    pid=os.getpid()
    if _SERVICES_STARTED_PID==pid: return
    with SERVICE_LOCK:
        if _SERVICES_STARTED_PID==pid: return
        if os.getenv("ENABLE_SIGNAL_SCHEDULER","true").strip().lower()!="true": logger.warning("V9 Signal Scheduler disabled by ENABLE_SIGNAL_SCHEDULER"); _SERVICES_STARTED_PID=pid; return
        try:
            import live_price; live_price.start(); import scheduler; scheduler.start(); logger.info("V9 Signal Scheduler + Live Price started in Gunicorn worker pid=%s",pid)
            try:
                from startup_notify import send_startup_notification; send_startup_notification(symbol="BTC + GOLD / LSE",engine_version=engine.ENGINE_VERSION)
            except Exception as exc: logger.exception("Startup notification failed: %s",exc)
            _SERVICES_STARTED_PID=pid
        except Exception as exc:
            logger.exception("V9 Runtime services failed to start in worker pid=%s",pid)
            try:
                from telegram_notify import send_telegram_message
                now_bkk=datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S"); send_telegram_message("❌ ระบบ V9 Runtime Services ขัดข้อง\n\n" f"🕐 เวลา: {now_bkk} (กรุงเทพฯ)\n⚠️ ไม่สามารถเริ่ม Live Price / Scheduler ใน worker ได้\n\n" f"🔴 ประเภทข้อผิดพลาด: {type(exc).__name__}\n📝 รายละเอียด: {str(exc)}\n\n🛑 ไม่มีการเปิดออเดอร์อัตโนมัติ")
            except Exception: logger.exception("Runtime service error Telegram notification failed")
@engine.app.before_request
def _ensure_runtime_services(): _start_runtime_services()
@engine.app.route("/")
def health():
    try: import live_price; live=live_price.status()
    except Exception as exc: live={"running":False,"provider":"LSE","transport":"WebSocket","error":str(exc)}
    return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":"V9","exchange":"LSE","symbols":["BTC/USD","XAU/USD"],"timeframe":"M5 trigger + H1/M15 confirmation","live_price":live,"live_orders_allowed":False})
@engine.app.route("/live-price")
def live_price_status():
    try: import live_price; payload=live_price.status(); payload["status"]="ok"; return _json_response(payload)
    except Exception as exc: return _json_response({"status":"error","error":str(exc)},500)
app=engine.app
