import os
import threading
from datetime import datetime, timezone

import engine_v5 as engine

_SCAN_LOCK = threading.RLock()
_LAST_ALERT_KEY = None


def _config(symbol):
    return {
        "symbol": symbol,
        "timeframe": "5min",
        "history": int(os.getenv("LIVE_SIGNAL_HISTORY", str(engine.SIGNAL_HISTORY_POINTS))),
    }


def scan_once(symbol="XAU/USD"):
    global _LAST_ALERT_KEY
    symbol = (symbol or "XAU/USD").strip().upper()
    if symbol not in ("XAU/USD", "BTC/USD"):
        raise ValueError(f"Unsupported symbol: {symbol}")

    with _SCAN_LOCK:
        engine.SYMBOL = symbol
        cfg = _config(symbol)
        df = engine.base.fetch_candles(symbol, cfg["timeframe"], cfg["history"])
        df = engine.base.remove_incomplete_last_candle(df)
        if len(df) < 100:
            raise RuntimeError(f"Only {len(df)} closed candles available")
        df = engine.base.calculate_indicators(df)
        index = len(df) - 1
        candle = df.iloc[index]
        candle_time = str(candle.get("datetime", candle.name))
        result = engine.base.analyze_candle(df, index)
        if not isinstance(result, dict):
            raise RuntimeError("analyze_candle returned an invalid result")

        signal = result.get("signal")
        valid = bool(result.get("valid"))
        key = f"{symbol}|{candle_time}|{signal}"
        alerted = False

        if valid and signal in ("BUY", "SELL") and key != _LAST_ALERT_KEY:
            levels = result.get("trade_levels") or {}
            message = (
                f"<b>🚨 {symbol} SIGNAL v5</b>\n\n"
                f"<b>Direction:</b> {signal}\n"
                f"<b>Timeframe:</b> M5\n"
                f"<b>Score:</b> {result.get('score')}\n"
                f"<b>Entry:</b> NEXT CANDLE OPEN (THEORETICAL)\n"
                f"<b>SL:</b> {levels.get('sl')}\n"
                f"<b>TP:</b> {levels.get('tp')}\n"
                f"<b>RR:</b> {levels.get('risk_reward')}\n"
                f"<b>Pattern:</b> {', '.join(result.get('patterns') or [])}\n"
                f"<b>Status:</b> PAPER SIGNAL — NO LIVE ORDER"
            )
            telegram_result = engine.send_telegram(message)
            _LAST_ALERT_KEY = key
            alerted = bool(telegram_result)

        return {
            "status": "ok",
            "engine_version": engine.ENGINE_VERSION,
            "symbol": symbol,
            "timeframe": "M5",
            "closed_candle": candle_time,
            "signal": signal,
            "valid": valid,
            "score": result.get("score"),
            "trade_levels": result.get("trade_levels"),
            "patterns": result.get("patterns") or [],
            "telegram_alert_sent": alerted,
            "live_orders_allowed": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
