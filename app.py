import os
import json
import math
import threading
from urllib.parse import parse_qs

import requests
from flask import Response, request

import engine_v5 as engine

SUPPORTED_SYMBOLS = ("BTC/USDT",)
SYMBOL_LOCK = threading.RLock()

BASE = {
    "BTC/USDT": {
        "MINIMUM_ATR": float(os.getenv("BTC_MINIMUM_ATR", "20.0")),
        "MIN_STOP_ATR": float(os.getenv("BTC_MIN_STOP_ATR", "1.0")),
        "MAX_STOP_ATR": float(os.getenv("BTC_MAX_STOP_ATR", "3.0")),
        "SPREAD": float(os.getenv("BTC_SPREAD", "5.0")),
        "SLIPPAGE": float(os.getenv("BTC_SLIPPAGE", "2.0")),
        "HISTORY_POINTS": int(os.getenv("BTC_HISTORY_POINTS", "200")),
        "BACKTEST_POINTS": int(os.getenv("BTC_BACKTEST_POINTS", "200")),
    },
}

_original_risk_guard = engine.evaluate_live_risk_guard

def _runtime_risk_guard(**kwargs):
    return _original_risk_guard(
        **kwargs,
        price_jump_atr=float(os.getenv("LIVE_PRICE_JUMP_ATR", "0")),
        daily_loss_r=float(os.getenv("LIVE_DAILY_LOSS_R", "0")),
        consecutive_losses=int(os.getenv("LIVE_CONSECUTIVE_LOSSES", "0")),
        trades_today=int(os.getenv("LIVE_TRADES_TODAY", "0")),
        slippage=float(os.getenv("LIVE_SLIPPAGE", str(engine.SLIPPAGE))),
    )
engine.evaluate_live_risk_guard = _runtime_risk_guard


def activate(symbol):
    symbol = (symbol or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"Unsupported Binance symbol: {symbol}")
    cfg = BASE[symbol]
    for target in (engine, engine.base):
        target.SYMBOL = symbol
        target.MINIMUM_ATR = cfg["MINIMUM_ATR"]
        target.MIN_STOP_ATR = cfg["MIN_STOP_ATR"]
        target.MAX_STOP_ATR = cfg["MAX_STOP_ATR"]
        target.SPREAD = cfg["SPREAD"]
        target.SLIPPAGE = cfg["SLIPPAGE"]
        target.SIGNAL_HISTORY_POINTS = cfg["HISTORY_POINTS"]
    return symbol


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    try:
        return _json_safe(value.item())
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        return _json_safe(value.tolist())
    except (AttributeError, TypeError, ValueError):
        return str(value)


def _json_response(payload, status=200):
    body = json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False)
    return Response(body, status=status, mimetype="application/json")


@engine.app.route("/symbols")
def symbols():
    return _json_response({"status":"ok","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbols":list(SUPPORTED_SYMBOLS),"timeframe":"M5","market_data":"CCXT public OHLCV","live_orders_allowed":False})


@engine.app.route("/validation")
def validation():
    symbol = (request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        return _json_response({"status":"error","message":f"Unsupported Binance symbol: {symbol}","supported_symbols":list(SUPPORTED_SYMBOLS),"live_orders_allowed":False}, 400)
    try:
        bars = max(100, min(int(request.args.get("bars", "1000")), 1000))
    except (TypeError, ValueError):
        return _json_response({"status":"error","message":"bars must be an integer between 100 and 1000","live_orders_allowed":False}, 400)
    try:
        import validate_v5
        with SYMBOL_LOCK:
            activate(symbol)
            report = validate_v5.run(symbol, bars)
        report["endpoint"] = "/validation"
        report["request"] = {"symbol":symbol,"bars":bars}
        report["live_orders_allowed"] = False
        return _json_response(report, 200)
    except Exception as exc:
        return _json_response({"status":"validation_error","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":symbol,"bars":bars,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False}, 502)


@engine.app.route("/validation/diagnostics")
def validation_diagnostics():
    symbol = (request.args.get("symbol") or "BTC/USDT").strip().upper()
    try:
        bars = max(100, min(int(request.args.get("bars", "1000")), 1000))
    except (TypeError, ValueError):
        bars = 1000
    result = {"status":"ok","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":symbol,"bars":bars,"live_orders_allowed":False,"stages":{}}
    if symbol not in SUPPORTED_SYMBOLS:
        result.update({"status":"error","message":f"Unsupported Binance symbol: {symbol}"})
        return _json_response(result, 400)
    try:
        activate(symbol)
        result["stages"]["activate"] = {"ok":True}
        import validate_v5
        result["stages"]["import_validate_v5"] = {"ok":True}
        df = validate_v5.fetch_candles(symbol, "5min", bars)
        result["stages"]["fetch_binance_ohlcv"] = {"ok":True,"rows":len(df)}
        from binance_data import BinanceMarketData
        df = BinanceMarketData.remove_incomplete_last_candle(df, timeframe_minutes=5)
        result["stages"]["closed_candles"] = {"ok":True,"rows":len(df)}
        if len(df) < 100:
            raise RuntimeError(f"Only {len(df)} closed Binance candles returned")
        df = engine.base.calculate_indicators(df)
        result["stages"]["indicators"] = {"ok":True,"rows":len(df)}
        index = len(df) - int(engine.FORWARD_BARS) - 2
        index = max(50, min(index, len(df)-1))
        analyzed = engine.base.analyze_candle(df, index)
        result["stages"]["analyze_candle"] = {"ok":True,"index":index,"valid":analyzed.get("valid") if isinstance(analyzed,dict) else None,"signal":analyzed.get("signal") if isinstance(analyzed,dict) else None,"score":analyzed.get("score") if isinstance(analyzed,dict) else None}
        result["status"] = "diagnostics_ok"
        return _json_response(result, 200)
    except Exception as exc:
        result.update({"status":"diagnostics_error","error_type":type(exc).__name__,"message":str(exc)})
        return _json_response(result, 502)


@engine.app.route("/signal")
def live_signal():
    symbol = (request.args.get("symbol") or "BTC/USDT").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        return _json_response({"status":"error","message":f"Unsupported Binance symbol: {symbol}","live_orders_allowed":False}, 400)
    try:
        import live_scanner
        with SYMBOL_LOCK:
            activate(symbol)
            result = live_scanner.scan_once(symbol)
        return _json_response(result, 200)
    except Exception as exc:
        return _json_response({"status":"signal_error","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":symbol,"error_type":type(exc).__name__,"message":str(exc),"telegram_alert_sent":False,"live_orders_allowed":False}, 502)


@engine.app.route("/scheduler/status")
def scheduler_status():
    try:
        import scheduler
        return _json_response({"status":"ok",**scheduler.status()}, 200)
    except Exception as exc:
        return _json_response({"status":"scheduler_error","error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False}, 502)


def _startup_once():
    if os.getenv("DISABLE_STARTUP_TELEGRAM", "false").strip().lower() == "true":
        return
    try:
        from startup_notify import send_startup_notification
        send_startup_notification("BTC/USDT", str(engine.ENGINE_VERSION))
    except Exception:
        pass

# Gunicorn imports this module once per worker. The notification helper has its
# own process-local once guard; it is deliberately best-effort and never blocks startup.
_startup_once()


class MultiSymbolMiddleware:
    def __init__(self, application):
        self.application = application
    def __call__(self, environ, start_response):
        params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        requested = params.get("symbol", ["BTC/USDT"])[0]
        with SYMBOL_LOCK:
            names = ("SYMBOL","MINIMUM_ATR","MIN_STOP_ATR","MAX_STOP_ATR","SPREAD","SLIPPAGE","SIGNAL_HISTORY_POINTS")
            previous = {name:getattr(engine,name) for name in names}
            previous_base = {name:getattr(engine.base,name) for name in names}
            try:
                activate(requested)
                return self.application(environ, start_response)
            except ValueError as exc:
                body = json.dumps(_json_safe({"status":"error","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","symbol":requested,"message":str(exc),"live_orders_allowed":False})).encode()
                start_response("400 BAD REQUEST",[("Content-Type","application/json"),("Content-Length",str(len(body)))])
                return [body]
            except Exception as exc:
                body = json.dumps(_json_safe({"status":"application_error","engine_version":getattr(engine,"ENGINE_VERSION","unknown"),"exchange":"Binance","symbol":requested,"error_type":type(exc).__name__,"message":str(exc),"live_orders_allowed":False})).encode()
                start_response("500 INTERNAL SERVER ERROR",[("Content-Type","application/json"),("Content-Length",str(len(body)))])
                return [body]
            finally:
                for name,value in previous.items(): setattr(engine,name,value)
                for name,value in previous_base.items(): setattr(engine.base,name,value)

app = MultiSymbolMiddleware(engine.app)

if os.getenv("ENABLE_SIGNAL_SCHEDULER", "false").strip().lower() == "true":
    try:
        import scheduler
        scheduler.start()
    except Exception:
        pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", port, app)
