import os
import json
import threading
from urllib.parse import parse_qs

import requests

# engine_v42 sends its legacy startup notification at import time.
# Suppress only that import-time HTTP call; runtime Telegram sending remains intact.
_original_requests_post = requests.post
requests.post = lambda *args, **kwargs: type("_StartupResponse", (), {"ok": False, "text": "legacy startup suppressed"})()
import engine_v5 as engine
requests.post = _original_requests_post

SUPPORTED_SYMBOLS = ("XAU/USD", "BTC/USD")
SYMBOL_LOCK = threading.RLock()

BASE = {
    "XAU/USD": {
        "MINIMUM_ATR": float(os.getenv("XAU_MINIMUM_ATR", str(engine.MINIMUM_ATR))),
        "MIN_STOP_ATR": float(os.getenv("XAU_MIN_STOP_ATR", str(engine.MIN_STOP_ATR))),
        "MAX_STOP_ATR": float(os.getenv("XAU_MAX_STOP_ATR", str(engine.MAX_STOP_ATR))),
        "SPREAD": float(os.getenv("XAU_SPREAD", str(engine.SPREAD))),
        "SLIPPAGE": float(os.getenv("XAU_SLIPPAGE", str(engine.SLIPPAGE))),
        "HISTORY_POINTS": int(os.getenv("XAU_HISTORY_POINTS", str(engine.SIGNAL_HISTORY_POINTS))),
        "BACKTEST_POINTS": int(os.getenv("XAU_BACKTEST_POINTS", "200")),
    },
    "BTC/USD": {
        "MINIMUM_ATR": float(os.getenv("BTC_MINIMUM_ATR", "20.0")),
        "MIN_STOP_ATR": float(os.getenv("BTC_MIN_STOP_ATR", "1.0")),
        "MAX_STOP_ATR": float(os.getenv("BTC_MAX_STOP_ATR", "3.0")),
        "SPREAD": float(os.getenv("BTC_SPREAD", "5.0")),
        "SLIPPAGE": float(os.getenv("BTC_SLIPPAGE", "2.0")),
        "HISTORY_POINTS": int(os.getenv("BTC_HISTORY_POINTS", "80")),
        "BACKTEST_POINTS": int(os.getenv("BTC_BACKTEST_POINTS", "80")),
    },
}

_original_risk_guard = engine.evaluate_live_risk_guard


def _runtime_risk_guard(**kwargs):
    """Feed externally maintained live-risk state into the v5 fail-closed guard."""
    return _original_risk_guard(
        **kwargs,
        price_jump_atr=float(os.getenv("LIVE_PRICE_JUMP_ATR", "0")),
        daily_loss_r=float(os.getenv("LIVE_DAILY_LOSS_R", "0")),
        consecutive_losses=int(os.getenv("LIVE_CONSECUTIVE_LOSSES", "0")),
        trades_today=int(os.getenv("LIVE_TRADES_TODAY", "0")),
        slippage=float(os.getenv("LIVE_SLIPPAGE", str(engine.SLIPPAGE))),
    )


engine.evaluate_live_risk_guard = _runtime_risk_guard


def _telegram_alerting_jsonify(*args, **kwargs):
    """Preserve the existing Telegram workflow without changing v5 route logic."""
    payload = args[0] if args and isinstance(args[0], dict) else None
    if payload and payload.get("valid") and payload.get("signal") in ("BUY", "SELL"):
        levels = payload.get("trade_levels") or {}
        message = (
            f"<b>🚨 XAU/USD SIGNAL v5</b>\n\n"
            f"<b>Direction:</b> {payload.get('signal')}\n"
            f"<b>Timeframe:</b> M5\n"
            f"<b>Score:</b> {payload.get('score')}\n"
            f"<b>Entry:</b> NEXT CANDLE OPEN (THEORETICAL)\n"
            f"<b>Projected SL:</b> {levels.get('sl')}\n"
            f"<b>Projected TP:</b> {levels.get('tp')}\n"
            f"<b>RR:</b> {levels.get('risk_reward')}\n"
            f"<b>Pattern:</b> {', '.join(payload.get('patterns') or [])}\n"
            f"<b>Safety:</b> PAPER VALIDATION ONLY"
        )
        payload["telegram"] = engine.send_telegram(message)
    return _original_jsonify(*args, **kwargs)


_original_jsonify = engine.jsonify
engine.jsonify = _telegram_alerting_jsonify


def activate(symbol):
    symbol = (symbol or os.getenv("SYMBOL", "XAU/USD")).strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"Unsupported symbol: {symbol}")
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


@engine.app.route("/symbols")
def symbols():
    return {
        "status": "ok",
        "engine_version": engine.ENGINE_VERSION,
        "symbols": list(SUPPORTED_SYMBOLS),
        "timeframe": engine.TIMEFRAME,
        "usage": "Use ?symbol=XAU/USD or ?symbol=BTC/USD",
    }


@engine.app.route("/validation")
def validation():
    """Run the v5 paper-validation backtest directly from a browser."""
    from flask import request

    symbol = (request.args.get("symbol") or "XAU/USD").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        return {
            "status": "error",
            "engine_version": engine.ENGINE_VERSION,
            "message": f"Unsupported symbol: {symbol}",
            "supported_symbols": list(SUPPORTED_SYMBOLS),
            "live_orders_allowed": False,
        }, 400

    try:
        bars = int(request.args.get("bars", "1000"))
    except (TypeError, ValueError):
        return {
            "status": "error",
            "engine_version": engine.ENGINE_VERSION,
            "message": "bars must be an integer between 100 and 5000",
            "live_orders_allowed": False,
        }, 400

    bars = max(100, min(bars, 5000))

    try:
        import validate_v5
        with SYMBOL_LOCK:
            activate(symbol)
            report = validate_v5.run(symbol, bars)
        report["endpoint"] = "/validation"
        report["request"] = {"symbol": symbol, "bars": bars}
        report["live_orders_allowed"] = False
        return report, 200
    except Exception as exc:
        # Safe diagnostic: expose the exception message/type, never a traceback.
        return {
            "status": "validation_error",
            "engine_version": engine.ENGINE_VERSION,
            "symbol": symbol,
            "bars": bars,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "live_orders_allowed": False,
            "next_step": "Use /validation/diagnostics?symbol=XAU/USD&bars=1000 for staged diagnostics.",
        }, 502


@engine.app.route("/validation/diagnostics")
def validation_diagnostics():
    """Run validation in stages so deployment/runtime failures are observable."""
    from flask import request

    symbol = (request.args.get("symbol") or "XAU/USD").strip().upper()
    try:
        bars = max(100, min(int(request.args.get("bars", "1000")), 5000))
    except (TypeError, ValueError):
        bars = 1000

    result = {
        "status": "ok",
        "engine_version": engine.ENGINE_VERSION,
        "symbol": symbol,
        "bars": bars,
        "live_orders_allowed": False,
        "stages": {},
    }

    if symbol not in SUPPORTED_SYMBOLS:
        result["status"] = "error"
        result["message"] = f"Unsupported symbol: {symbol}"
        return result, 400

    try:
        activate(symbol)
        result["stages"]["activate"] = {"ok": True}

        import validate_v5
        result["stages"]["import_validate_v5"] = {"ok": True}

        df = validate_v5.fetch_candles(symbol, "5min", bars)
        result["stages"]["fetch_candles"] = {"ok": True, "rows": len(df)}

        df = engine.base.remove_incomplete_last_candle(df)
        result["stages"]["closed_candles"] = {"ok": True, "rows": len(df)}

        if len(df) < 100:
            raise RuntimeError(f"Only {len(df)} closed candles returned")

        df = engine.base.calculate_indicators(df)
        result["stages"]["indicators"] = {"ok": True, "rows": len(df)}

        index = len(df) - int(engine.FORWARD_BARS) - 2
        index = max(50, min(index, len(df) - 1))
        analyzed = engine.base.analyze_candle(df, index)
        result["stages"]["analyze_candle"] = {
            "ok": True,
            "index": index,
            "valid": analyzed.get("valid") if isinstance(analyzed, dict) else None,
            "signal": analyzed.get("signal") if isinstance(analyzed, dict) else None,
            "score": analyzed.get("score") if isinstance(analyzed, dict) else None,
        }

        result["status"] = "diagnostics_ok"
        return result, 200
    except Exception as exc:
        result["status"] = "diagnostics_error"
        result["error_type"] = type(exc).__name__
        result["message"] = str(exc)
        return result, 502


class MultiSymbolMiddleware:
    """Serialize access to the legacy engine's mutable symbol globals."""

    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        requested = params.get("symbol", [os.getenv("SYMBOL", "XAU/USD")])[0]

        with SYMBOL_LOCK:
            names = (
                "SYMBOL", "MINIMUM_ATR", "MIN_STOP_ATR", "MAX_STOP_ATR",
                "SPREAD", "SLIPPAGE", "SIGNAL_HISTORY_POINTS"
            )
            previous = {name: getattr(engine, name) for name in names}
            previous_base = {name: getattr(engine.base, name) for name in names}
            try:
                activate(requested)
                return self.application(environ, start_response)
            except ValueError as exc:
                body = json.dumps({
                    "status": "error",
                    "engine_version": engine.ENGINE_VERSION,
                    "symbol": requested,
                    "message": str(exc),
                    "live_orders_allowed": False,
                }).encode()
                start_response("400 BAD REQUEST", [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ])
                return [body]
            except Exception as exc:
                # Prevent Flask/Gunicorn HTML 500 pages and expose a safe runtime diagnostic.
                body = json.dumps({
                    "status": "application_error",
                    "engine_version": getattr(engine, "ENGINE_VERSION", "unknown"),
                    "symbol": requested,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "live_orders_allowed": False,
                }).encode()
                start_response("500 INTERNAL SERVER ERROR", [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ])
                return [body]
            finally:
                for name, value in previous.items():
                    setattr(engine, name, value)
                for name, value in previous_base.items():
                    setattr(engine.base, name, value)


app = MultiSymbolMiddleware(engine.app)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", port, app)
