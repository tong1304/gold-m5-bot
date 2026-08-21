import os
import threading
from datetime import datetime, timezone

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData

_SCAN_LOCK = threading.RLock()
_LAST_ALERT_KEY = None
BINANCE = BinanceMarketData()


def _config(symbol):
    return {"symbol": symbol, "timeframe": "5m", "history": int(os.getenv("LIVE_SIGNAL_HISTORY", str(engine.SIGNAL_HISTORY_POINTS)))}


def scan_once(symbol="BTC/USDT"):
    global _LAST_ALERT_KEY
    symbol = (symbol or "BTC/USDT").strip().upper()
    if symbol != "BTC/USDT":
        raise ValueError(f"Unsupported Binance symbol: {symbol}")
    with _SCAN_LOCK:
        engine.SYMBOL = symbol
        base.SYMBOL = symbol
        cfg = _config(symbol)
        df = BINANCE.fetch_candles(symbol, cfg["timeframe"], cfg["history"])
        df = BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=5)
        if len(df) < 100:
            raise RuntimeError(f"Only {len(df)} closed Binance candles available")
        df = base.calculate_indicators(df)
        index = len(df) - 1
        candle = df.iloc[index]
        candle_time = str(candle.get("datetime", candle.name))
        result = base.analyze_candle(df, index)
        if not isinstance(result, dict):
            raise RuntimeError("analyze_candle returned an invalid result")
        signal = result.get("signal")
        valid = bool(result.get("valid"))
        key = f"{symbol}|{candle_time}|{signal}"
        alerted = False
        telegram_result = None
        if valid and signal in ("BUY", "SELL") and key != _LAST_ALERT_KEY:
            levels = result.get("trade_levels") or {}
            message = (
                f"<b>🚨 {symbol} SIGNAL v5</b>\n\n"
                f"<b>Direction:</b> {signal}\n"
                f"<b>Timeframe:</b> M5\n"
                f"<b>Score:</b> {result.get('score')}\n"
                f"<b>Entry:</b> NEXT CANDLE OPEN (MANUAL)\n"
                f"<b>SL:</b> {levels.get('sl')}\n"
                f"<b>TP:</b> {levels.get('tp')}\n"
                f"<b>RR:</b> {levels.get('risk_reward')}\n"
                f"<b>Pattern:</b> {', '.join(result.get('patterns') or [])}\n"
                f"<b>Exchange:</b> Binance\n"
                f"<b>Status:</b> MANUAL ENTRY — NO LIVE ORDER"
            )
            telegram_result = engine.send_telegram(message)
            if isinstance(telegram_result, dict) and telegram_result.get("success"):
                _LAST_ALERT_KEY = key
                alerted = True
        return {
            "status": "ok", "engine_version": engine.ENGINE_VERSION, "exchange": "Binance",
            "market_type": "spot", "symbol": symbol, "timeframe": "M5",
            "closed_candle": candle_time, "signal": signal, "valid": valid,
            "score": result.get("score"), "trade_levels": result.get("trade_levels"),
            "patterns": result.get("patterns") or [], "telegram_alert_sent": alerted,
            "telegram_result": telegram_result, "live_orders_allowed": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
