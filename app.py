import os
import threading
import json
import traceback
from urllib.parse import parse_qs

import engine_v42 as engine

SUPPORTED_SYMBOLS = ("XAU/USD", "BTC/USD")
SYMBOL_LOCK = threading.RLock()

BASE = {
    "XAU/USD": {
        "MINIMUM_ATR": engine.MINIMUM_ATR,
        "MIN_STOP_ATR": engine.MIN_STOP_ATR,
        "MAX_STOP_ATR": engine.MAX_STOP_ATR,
        "SPREAD": engine.SPREAD,
        "SLIPPAGE": engine.SLIPPAGE,
    },
    "BTC/USD": {
        "MINIMUM_ATR": float(os.getenv("BTC_MINIMUM_ATR", "20.0")),
        "MIN_STOP_ATR": float(os.getenv("BTC_MIN_STOP_ATR", "1.0")),
        "MAX_STOP_ATR": float(os.getenv("BTC_MAX_STOP_ATR", "3.0")),
        "SPREAD": float(os.getenv("BTC_SPREAD", "5.0")),
        "SLIPPAGE": float(os.getenv("BTC_SLIPPAGE", "2.0")),
    },
}

engine.ENGINE_VERSION = "4.3"


def activate(symbol):
    symbol = (symbol or os.getenv("SYMBOL", "XAU/USD")).strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(
            f"Unsupported symbol: {symbol}. Supported: {', '.join(SUPPORTED_SYMBOLS)}"
        )
    cfg = BASE[symbol]
    engine.SYMBOL = symbol
    engine.MINIMUM_ATR = cfg["MINIMUM_ATR"]
    engine.MIN_STOP_ATR = cfg["MIN_STOP_ATR"]
    engine.MAX_STOP_ATR = cfg["MAX_STOP_ATR"]
    engine.SPREAD = cfg["SPREAD"]
    engine.SLIPPAGE = cfg["SLIPPAGE"]
    return symbol


@engine.app.errorhandler(Exception)
def json_exception_handler(exc):
    from flask import request
    return {
        "status": "error",
        "engine_version": "4.3",
        "symbol": getattr(engine, "SYMBOL", None),
        "path": request.path,
        "message": str(exc),
        "exception_type": type(exc).__name__,
        "trace": traceback.format_exc(),
    }, 500


class MultiSymbolMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        requested = params.get("symbol", [os.getenv("SYMBOL", "XAU/USD")])[0]

        with SYMBOL_LOCK:
            previous = {
                "SYMBOL": engine.SYMBOL,
                "MINIMUM_ATR": engine.MINIMUM_ATR,
                "MIN_STOP_ATR": engine.MIN_STOP_ATR,
                "MAX_STOP_ATR": engine.MAX_STOP_ATR,
                "SPREAD": engine.SPREAD,
                "SLIPPAGE": engine.SLIPPAGE,
            }
            try:
                activate(requested)
                return self.app(environ, start_response)
            except ValueError as exc:
                body = json.dumps({
                    "status": "error",
                    "engine_version": "4.3",
                    "symbol": requested,
                    "message": str(exc),
                }).encode()
                start_response("400 BAD REQUEST", [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ])
                return [body]
            except Exception as exc:
                body = json.dumps({
                    "status": "error",
                    "engine_version": "4.3",
                    "symbol": requested,
                    "message": str(exc),
                    "exception_type": type(exc).__name__,
                    "trace": traceback.format_exc(),
                }).encode()
                try:
                    start_response("500 INTERNAL SERVER ERROR", [
                        ("Content-Type", "application/json"),
                        ("Content-Length", str(len(body))),
                    ])
                except Exception:
                    pass
                return [body]
            finally:
                for key, value in previous.items():
                    setattr(engine, key, value)


@engine.app.route("/symbols")
def symbols():
    return {
        "status": "ok",
        "engine_version": "4.3",
        "symbols": list(SUPPORTED_SYMBOLS),
        "timeframe": engine.TIMEFRAME,
        "usage": "Use ?symbol=XAU/USD or ?symbol=BTC/USD on /signal, /backtest, /test-data and /health",
    }


@engine.app.route("/diagnostics")
def diagnostics():
    from flask import request

    requested = request.args.get("symbol", os.getenv("SYMBOL", "XAU/USD"))
    result = {
        "status": "ok",
        "engine_version": "4.3",
        "symbol": requested,
        "stages": {},
    }

    try:
        activate(requested)
        result["stages"]["activate"] = {
            "ok": True,
            "minimum_atr": engine.MINIMUM_ATR,
            "min_stop_atr": engine.MIN_STOP_ATR,
            "max_stop_atr": engine.MAX_STOP_ATR,
            "spread": engine.SPREAD,
            "slippage": engine.SLIPPAGE,
        }

        df = engine.get_market_data(1000)
        result["stages"]["market_data"] = {
            "ok": True,
            "rows": len(df),
            "latest": str(df.iloc[-1]["datetime"]) if not df.empty else None,
        }

        df = engine.remove_incomplete_last_candle(df)
        result["stages"]["closed_candles"] = {
            "ok": True,
            "rows": len(df),
            "latest": str(df.iloc[-1]["datetime"]) if not df.empty else None,
        }

        if len(df) < 100:
            raise RuntimeError(f"Not enough closed candles: {len(df)}")

        df = engine.calculate_indicators(df)
        result["stages"]["indicators"] = {
            "ok": True,
            "columns": len(df.columns),
            "rows": len(df),
        }

        index = len(df) - 1
        analyzed = engine.analyze_candle(df, index)
        result["stages"]["analyze_candle"] = {
            "ok": True,
            "valid": analyzed.get("valid"),
            "signal": analyzed.get("signal"),
            "score": analyzed.get("score"),
        }

        return result

    except Exception as exc:
        result["status"] = "error"
        result["failed_stage"] = "current"
        result["message"] = str(exc)
        result["exception_type"] = type(exc).__name__
        result["trace"] = traceback.format_exc()
        return result, 500


app = MultiSymbolMiddleware(engine.app)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", port, app)
