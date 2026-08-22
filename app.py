import os
import json
import math
import threading
import logging
from urllib.parse import parse_qs
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Response, request

import engine_v5 as engine

SUPPORTED_SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XAU/USDT")
SYMBOL_LOCK = threading.RLock()
logger = logging.getLogger(__name__)

BASE = {
    "BTC/USDT": {"MINIMUM_ATR": float(os.getenv("BTC_MINIMUM_ATR", "20.0")), "MIN_STOP_ATR": float(os.getenv("BTC_MIN_STOP_ATR", "1.0")), "MAX_STOP_ATR": float(os.getenv("BTC_MAX_STOP_ATR", "3.0")), "SPREAD": float(os.getenv("BTC_SPREAD", "5.0")), "SLIPPAGE": float(os.getenv("BTC_SLIPPAGE", "2.0")), "HISTORY_POINTS": int(os.getenv("BTC_HISTORY_POINTS", "200"))},
    "ETH/USDT": {"MINIMUM_ATR": float(os.getenv("ETH_MINIMUM_ATR", "1.0")), "MIN_STOP_ATR": float(os.getenv("ETH_MIN_STOP_ATR", "1.0")), "MAX_STOP_ATR": float(os.getenv("ETH_MAX_STOP_ATR", "3.0")), "SPREAD": float(os.getenv("ETH_SPREAD", "0.50")), "SLIPPAGE": float(os.getenv("ETH_SLIPPAGE", "0.20")), "HISTORY_POINTS": int(os.getenv("ETH_HISTORY_POINTS", "200"))},
    "SOL/USDT": {"MINIMUM_ATR": float(os.getenv("SOL_MINIMUM_ATR", "0.20")), "MIN_STOP_ATR": float(os.getenv("SOL_MIN_STOP_ATR", "1.0")), "MAX_STOP_ATR": float(os.getenv("SOL_MAX_STOP_ATR", "3.0")), "SPREAD": float(os.getenv("SOL_SPREAD", "0.10")), "SLIPPAGE": float(os.getenv("SOL_SLIPPAGE", "0.05")), "HISTORY_POINTS": int(os.getenv("SOL_HISTORY_POINTS", "200"))},
    "XAU/USDT": {"MINIMUM_ATR": float(os.getenv("XAU_MINIMUM_ATR", "1.0")), "MIN_STOP_ATR": float(os.getenv("XAU_MIN_STOP_ATR", "1.0")), "MAX_STOP_ATR": float(os.getenv("XAU_MAX_STOP_ATR", "3.0")), "SPREAD": float(os.getenv("XAU_SPREAD", "0.50")), "SLIPPAGE": float(os.getenv("XAU_SLIPPAGE", "0.20")), "HISTORY_POINTS": int(os.getenv("XAU_HISTORY_POINTS", "200"))},
}

_original_risk_guard = engine.evaluate_live_risk_guard

def _runtime_risk_guard(**kwargs):
    return _original_risk_guard(**kwargs, price_jump_atr=float(os.getenv("LIVE_PRICE_JUMP_ATR", "0")), daily_loss_r=float(os.getenv("LIVE_DAILY_LOSS_R", "0")), consecutive_losses=int(os.getenv("LIVE_CONSECUTIVE_LOSSES", "0")), trades_today=int(os.getenv("LIVE_TRADES_TODAY", "0")), slippage=float(os.getenv("LIVE_SLIPPAGE", str(engine.SLIPPAGE))))
engine.evaluate_live_risk_guard = _runtime_risk_guard

M5_MIN_DIRECTIONAL_PATTERNS = 1
M5_REQUIRE_NO_OPPOSING_PATTERN = True


def _f(value, default=0.0):
    try:
        value = float(value)
        return default if not math.isfinite(value) else value
    except Exception:
        return default


def activate(symbol):
    symbol = (symbol or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"Unsupported Binance symbol: {symbol}")
    cfg = BASE[symbol]
    # Keep v5 and the underlying v4 execution engine on the same RR policy.
    # Otherwise base.calculate_trade_levels() can silently return 1.5R while
    # live_scanner expects the mandatory 2.0R minimum.
    for target in (engine, engine.base):
        target.SYMBOL = symbol
        target.MINIMUM_ATR = cfg["MINIMUM_ATR"]
        target.MIN_STOP_ATR = cfg["MIN_STOP_ATR"]
        target.MAX_STOP_ATR = cfg["MAX_STOP_ATR"]
        target.SPREAD = cfg["SPREAD"]
        target.SLIPPAGE = cfg["SLIPPAGE"]
        target.SIGNAL_HISTORY_POINTS = cfg["HISTORY_POINTS"]
        target.MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
        target.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "2.0")), 2.0)
    return symbol


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)): return value
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, dict): return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)): return [_json_safe(v) for v in value]
    try: return _json_safe(value.item())
    except (AttributeError, TypeError, ValueError): pass
    try: return _json_safe(value.tolist())
    except (AttributeError, TypeError, ValueError): return str(value)


def _json_response(payload, status=200):
    return Response(json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False), status=status, mimetype="application/json")


@engine.app.route("/")
def health():
    return _json_response({"status":"ok","service":"gold-m5-bot","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbols":list(SUPPORTED_SYMBOLS),"timeframe":"M5","live_orders_allowed":False})


@engine.app.route("/symbols")
def symbols():
    return _json_response({"status":"ok","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbols":list(SUPPORTED_SYMBOLS),"timeframe":"M5 trigger + H1/M15 confirmation","market_data":"CCXT public OHLCV","live_orders_allowed":False})


@engine.app.route("/signal")
def live_signal():
    symbol = (request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: return _json_response({"status":"error","message":f"Unsupported Binance symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try:
        import live_scanner
        with SYMBOL_LOCK: activate(symbol); return _json_response(live_scanner.scan_once(symbol),200)
    except Exception as exc: return _json_response({"status":"signal_error","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False},502)


@engine.app.route("/validation")
def validation():
    symbol = (request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: return _json_response({"status":"error","message":f"Unsupported Binance symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False},400)
    try: bars=max(100,min(int(request.args.get("bars","1000")),1000))
    except (TypeError,ValueError): return _json_response({"status":"error","message":"bars must be an integer between 100 and 1000","live_orders_allowed":False},400)
    try:
        import validate_v5
        with SYMBOL_LOCK: activate(symbol); report=validate_v5.run(symbol,bars)
        report["endpoint"]="/validation"; report["request"]={"symbol":symbol,"bars":bars}; report["live_orders_allowed"]=False; return _json_response(report)
    except Exception as exc: return _json_response({"status":"validation_error","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)


@engine.app.route("/validation/diagnostics")
def validation_diagnostics():
    symbol=(request.args.get("symbol") or "BTC/USDT").strip().upper()
    try: bars=max(100,min(int(request.args.get("bars","1000")),1000))
    except (TypeError,ValueError): bars=1000
    result={"status":"ok","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":symbol,"bars":bars,"live_orders_allowed":False,"stages":{}}
    if symbol not in SUPPORTED_SYMBOLS: result.update({"status":"error","message":f"Unsupported Binance symbol: {symbol}"}); return _json_response(result,400)
    try:
        activate(symbol); result["stages"]["activate"]={"ok":True}; import validate_v5; result["stages"]["import_validate_v5"]={"ok":True}
        df=validate_v5.fetch_candles(symbol,"5min",bars); result["stages"]["fetch_binance_ohlcv"]={"ok":True,"rows":len(df)}
        from binance_data import BinanceMarketData
        df=BinanceMarketData.remove_incomplete_last_candle(df,timeframe_minutes=5); result["stages"]["closed_candles"]={"ok":True,"rows":len(df)}
        if len(df)<100: raise RuntimeError(f"Only {len(df)} closed Binance candles returned")
        df=engine.base.calculate_indicators(df); index=max(50,min(len(df)-int(engine.FORWARD_BARS)-2,len(df)-1)); analyzed=engine.base.analyze_candle(df,index)
        result["stages"]["indicators"]={"ok":True,"rows":len(df)}; result["stages"]["analyze_candle"]={"ok":True,"index":index,"valid":analyzed.get("valid") if isinstance(analyzed,dict) else None,"signal":analyzed.get("signal") if isinstance(analyzed,dict) else None,"score":analyzed.get("score") if isinstance(analyzed,dict) else None}; result["status"]="diagnostics_ok"; return _json_response(result)
    except Exception as exc: result.update({"status":"diagnostics_error","error_type":type(exc).__name__,"message":str(exc)}); return _json_response(result,502)


@engine.app.route("/scheduler/status")
def scheduler_status():
    try:
        import scheduler; return _json_response({"status":"ok",**scheduler.status()})
    except Exception as exc: return _json_response({"status":"scheduler_error","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False},502)


class MultiSymbolMiddleware:
    def __init__(self, application): self.application=application
    def __call__(self,environ,start_response):
        params=parse_qs(environ.get("QUERY_STRING", ""),keep_blank_values=True); requested=params.get("symbol",["BTC/USDT"])[0]
        with SYMBOL_LOCK:
            names=("SYMBOL","MINIMUM_ATR","MIN_STOP_ATR","MAX_STOP_ATR","SPREAD","SLIPPAGE","SIGNAL_HISTORY_POINTS","MIN_RISK_REWARD","RISK_REWARD"); previous={n:getattr(engine,n) for n in names}; previous_base={n:getattr(engine.base,n) for n in names}
            try: activate(requested); return self.application(environ,start_response)
            except ValueError as exc:
                body=json.dumps(_json_safe({"status":"error","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":requested,"message":str(exc),"live_orders_allowed":False})).encode(); start_response("400 BAD REQUEST",[("Content-Type","application/json"),("Content-Length",str(len(body)))]); return [body]
            except Exception as exc:
                logger.exception("Application request failed: %s", exc)
                body=json.dumps(_json_safe({"status":"application_error","engine_version":getattr(engine,"ENGINE_VERSION","unknown"),"exchange":"Binance","symbol":requested,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})).encode(); start_response("500 INTERNAL SERVER ERROR",[("Content-Type","application/json"),("Content-Length",str(len(body)))]); return [body]
            finally:
                for n,v in previous.items(): setattr(engine,n,v)
                for n,v in previous_base.items(): setattr(engine.base,n,v)

app=MultiSymbolMiddleware(engine.app)

if os.getenv("ENABLE_SIGNAL_SCHEDULER", "true").strip().lower() == "true":
    try:
        import scheduler
        scheduler.start()
        logger.info("Signal Scheduler started successfully")
    except Exception as exc:
        logger.exception("Signal Scheduler failed to start")
        try:
            from telegram_notify import send_telegram_message
            now_bkk = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")
            send_telegram_message(
                "❌ ระบบแจ้งเตือน Scheduler ขัดข้อง\n\n"
                f"🕐 เวลา: {now_bkk} (กรุงเทพฯ)\n"
                "⚠️ ไม่สามารถเริ่มระบบสแกนสัญญาณอัตโนมัติได้\n\n"
                f"🔴 ประเภทข้อผิดพลาด: {type(exc).__name__}\n"
                f"📝 รายละเอียด: {str(exc)}\n\n"
                "🛑 ระบบจะไม่ถือว่า Scheduler ทำงานอยู่\n"
                "🖐️ ไม่มีการเปิดออเดอร์อัตโนมัติ"
            )
        except Exception as telegram_exc:
            logger.exception("Scheduler error Telegram notification failed: %s", telegram_exc)
else:
    logger.warning("Signal Scheduler disabled by ENABLE_SIGNAL_SCHEDULER")

try:
    from startup_notify import send_startup_notification
    send_startup_notification(symbol="MULTI-ASSET", engine_version="5.0")
except Exception as exc:
    logger.exception("Startup notification failed: %s", exc)

if __name__ == "__main__":
    port=int(os.getenv("PORT","10000"))
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0",port,app)