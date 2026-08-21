import os
import threading
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
        raise ValueError(f"Unsupported symbol: {symbol}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    cfg = BASE[symbol]
    engine.SYMBOL = symbol
    engine.MINIMUM_ATR = cfg["MINIMUM_ATR"]
    engine.MIN_STOP_ATR = cfg["MIN_STOP_ATR"]
    engine.MAX_STOP_ATR = cfg["MAX_STOP_ATR"]
    engine.SPREAD = cfg["SPREAD"]
    engine.SLIPPAGE = cfg["SLIPPAGE"]
    return symbol


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
                import json
                body = json.dumps({"status": "error", "message": str(exc)}).encode()
                start_response("400 BAD REQUEST", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
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


app = MultiSymbolMiddleware(engine.app)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", port, app)
