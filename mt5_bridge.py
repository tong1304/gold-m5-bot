"""XM MT5 bridge.

Run this process on the Windows machine/VPS where the XM MetaTrader 5
terminal is installed and connected to the XM trade server. The cloud bot
calls this bridge for OHLCV and tick data; no trading/order endpoint exists.
"""
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

try:
    import MetaTrader5 as mt5
except ImportError as exc:
    mt5 = None
    _MT5_IMPORT_ERROR = exc

app = Flask(__name__)
TOKEN = os.getenv("MT5_BRIDGE_TOKEN", "").strip()
PORT = int(os.getenv("MT5_BRIDGE_PORT", "8787"))

TIMEFRAMES = {
    "M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1",
}


def _authorize():
    if not TOKEN:
        return True
    return request.headers.get("X-MT5-BRIDGE-TOKEN", "") == TOKEN


def _ensure_mt5():
    if mt5 is None:
        raise RuntimeError(f"MetaTrader5 package is unavailable: {_MT5_IMPORT_ERROR}")
    if mt5.terminal_info() is None:
        path = os.getenv("MT5_PATH", "").strip()
        login = os.getenv("MT5_LOGIN", "").strip()
        password = os.getenv("MT5_PASSWORD", "").strip()
        server = os.getenv("MT5_SERVER", "").strip()
        kwargs = {}
        if login and password and server:
            kwargs.update(login=int(login), password=password, server=server)
        ok = mt5.initialize(path=path, **kwargs) if path else mt5.initialize(**kwargs)
        if not ok:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    return mt5


def _symbol(name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("symbol is required")
    terminal = _ensure_mt5()
    info = terminal.symbol_info(name)
    if info is None:
        raise RuntimeError(f"XM MT5 symbol not found: {name}")
    if not info.visible and not terminal.symbol_select(name, True):
        raise RuntimeError(f"XM MT5 symbol could not be selected: {name}")
    return name


def _timeframe(name):
    key = str(name or "M5").upper()
    attr = TIMEFRAMES.get(key)
    if not attr:
        raise ValueError(f"unsupported timeframe: {key}")
    return getattr(_ensure_mt5(), attr)


@app.before_request
def auth():
    if not _authorize():
        return jsonify({"status": "error", "message": "unauthorized"}), 401


@app.get("/health")
def health():
    terminal = _ensure_mt5()
    info = terminal.terminal_info()
    account = terminal.account_info()
    return jsonify({
        "status": "ok",
        "provider": "XM MT5",
        "terminal_connected": info is not None,
        "trade_server": getattr(info, "name", None),
        "account_login": getattr(account, "login", None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orders_enabled": False,
    })


@app.get("/symbols")
def symbols():
    terminal = _ensure_mt5()
    requested = [os.getenv("MT5_BTC_SYMBOL", "BTCUSD"), os.getenv("MT5_GOLD_SYMBOL", "XAUUSD")]
    result = []
    for name in requested:
        info = terminal.symbol_info(name)
        result.append({
            "symbol": name,
            "available": info is not None,
            "visible": bool(info.visible) if info is not None else False,
        })
    return jsonify({"status": "ok", "provider": "XM MT5", "symbols": result})


@app.get("/price")
def price():
    name = _symbol(request.args.get("symbol"))
    tick = _ensure_mt5().symbol_info_tick(name)
    if tick is None:
        raise RuntimeError(f"XM MT5 tick unavailable: {name}")
    return jsonify({
        "status": "ok",
        "provider": "XM MT5",
        "symbol": name,
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "last": float(tick.last) if tick.last else None,
        "time": int(tick.time),
    })


@app.get("/candles")
def candles():
    name = _symbol(request.args.get("symbol"))
    timeframe_name = request.args.get("timeframe", "M5").upper()
    timeframe = _timeframe(timeframe_name)
    limit = min(max(int(request.args.get("limit", "1000")), 2), 5000)
    rates = _ensure_mt5().copy_rates_from_pos(name, timeframe, 0, limit)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"XM MT5 returned no OHLCV for {name}: {_ensure_mt5().last_error()}")
    rows = []
    for row in rates:
        rows.append({
            "time": int(row["time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "tick_volume": int(row["tick_volume"]),
            "spread": int(row["spread"]),
            "real_volume": int(row["real_volume"]),
        })
    return jsonify({
        "status": "ok",
        "provider": "XM MT5",
        "symbol": name,
        "timeframe": timeframe_name,
        "candles": rows,
    })


@app.errorhandler(Exception)
def handle_error(exc):
    return jsonify({
        "status": "error",
        "provider": "XM MT5",
        "error_type": type(exc).__name__,
        "message": str(exc),
    }), 502


if __name__ == "__main__":
    _ensure_mt5()
    app.run(host=os.getenv("MT5_BRIDGE_HOST", "0.0.0.0"), port=PORT)
