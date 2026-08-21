import os
import json
import threading
from urllib.parse import parse_qs

import engine_v5 as engine

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
                }).encode()
                start_response("400 BAD REQUEST", [
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
