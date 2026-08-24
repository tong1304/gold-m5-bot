from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from v11.telegram import send_telegram
from v11 import engine as v12_engine
import live_scanner_v11

logger = logging.getLogger("signal_scheduler")
ENGINE_VERSION = v12_engine.ENGINE_VERSION
TIMEFRAME_MODE = "MTF:H1→M15→M5"
TIMEFRAMES = ("H1", "M15", "M5")
BANGKOK = ZoneInfo("Asia/Bangkok")
UTC = timezone.utc
DISPLAY_SYMBOLS = ("BTC", "GOLD")
_RUNNING = False
_THREAD = None
_MONITOR_THREAD = None
_LAST_CLOSED_CANDLE = {}
_LAST_MONITOR_SLOT = None
_STARTED_AT = None
_LAST_CYCLE_AT = None
_LAST_RESULTS = []
_CYCLE_COUNT = 0

STRATEGIES = [
    "B1_RANGE_SWEEP_DISPLACEMENT",
    "B2_HTF_ZONE_M5_FVG_RETEST",
    "B3_VOLATILITY_EXPANSION_BREAKOUT_RETEST",
    "E1_TREND",
    "E2_TREND_PULLBACK",
    "E3_BREAKOUT",
    "E4_BREAKOUT_RETEST",
    "E5_MOMENTUM",
    "E6_MEAN_REVERSION",
    "E7_LIQUIDITY_REVERSAL",
    "E8_RANGE",
]


def _interval_seconds():
    try:
        return max(300, int(os.getenv("SIGNAL_SCAN_INTERVAL_SECONDS", "300")))
    except ValueError:
        return 300


def _symbols():
    return [
        s for s in dict.fromkeys(
            x.strip().upper()
            for x in os.getenv("LIVE_SIGNAL_SYMBOLS", "BTC,GOLD").split(",")
        )
        if s in DISPLAY_SYMBOLS
    ]


def _asset_market_status(symbol, now_utc=None):
    now_utc = now_utc or datetime.now(UTC)
    if symbol == "BTC":
        return True, "OPEN_24_7"
    wd = now_utc.weekday()
    t = now_utc.time()
    if symbol != "GOLD":
        return False, "UNKNOWN_MARKET_SESSION"
    if wd == 5:
        return False, "WEEKEND_CLOSED"
    if wd == 6:
        return (t.hour >= 23, "OPEN" if t.hour >= 23 else "SUNDAY_CLOSED")
    if wd == 4:
        return (t.hour < 22, "OPEN" if t.hour < 22 else "FRIDAY_CLOSED")
    if 22 <= t.hour < 23:
        return False, "DAILY_BREAK"
    return True, "OPEN"


def _is_stale_market_data_error(exc):
    """Return True only for a provider candle-feed freshness failure."""
    return "STALE_MARKET_DATA:" in str(exc)


def _notify_error(exc, context):
    try:
        send_telegram(f"⚠️ <b>V12.9 ระบบขัดข้อง</b>\n\n{context}\n{type(exc).__name__}: {exc}")
    except Exception:
        logger.exception("[V12 TELEGRAM] error notification failed")


def _trace_source(result):
    return result.get("setup") or result if isinstance(result, dict) else {}


def _log_decision(symbol, result):
    try:
        setup = _trace_source(result)
        logger.warning(
            "[V12 DECISION] %s FINAL=%s ENGINE=%s STRATEGY=%s ENTRY_TYPE=%s ENTRY=%s SL=%s TP=%s RR=%s",
            symbol,
            setup.get("signal", result.get("signal", "NO_TRADE")),
            setup.get("engine", result.get("engine", "NONE")),
            setup.get("strategy", result.get("strategy", "NONE")),
            setup.get("entry_type", result.get("entry_type")),
            (setup.get("trade_levels") or {}).get("entry", "N/A"),
            (setup.get("trade_levels") or {}).get("sl", "N/A"),
            (setup.get("trade_levels") or {}).get("tp", "N/A"),
            (setup.get("trade_levels") or {}).get("risk_reward", "N/A"),
        )
        trace = setup.get("decision_trace") or []
        if isinstance(trace, (list, tuple)):
            for item in trace:
                logger.warning("[V12 TRACE DETAIL] %s %s", symbol, item)
        else:
            logger.warning("[V12 TRACE DETAIL] %s trace=NONE", symbol)
    except Exception as exc:
        logger.exception("[V12 DECISION] %s logging failed: %s", symbol, exc)


def _seconds_to_next_boundary():
    remaining = 300 - (datetime.now(UTC).timestamp() % 300)
    return max(0.5, remaining + 1.0)


def run_scan_cycle():
    global _LAST_CYCLE_AT, _LAST_RESULTS, _CYCLE_COUNT
    now_utc = datetime.now(UTC)
    now_bkk = now_utc.astimezone(BANGKOK)
    results = []
    _CYCLE_COUNT += 1
    _LAST_CYCLE_AT = now_utc.isoformat()
    logger.warning(
        "[V12 SCHEDULER] Scan cycle #%s started at %s Bangkok symbols=%s mode=%s engine=%s",
        _CYCLE_COUNT, now_bkk.strftime('%Y-%m-%d %H:%M:%S'), _symbols(), TIMEFRAME_MODE, ENGINE_VERSION,
    )
    for symbol in _symbols():
        try:
            opened, session = _asset_market_status(symbol, now_utc)
            if not opened:
                results.append({"status": "market_closed", "symbol": symbol, "session": session, "live_orders_allowed": False})
                continue
            frame = live_scanner_v11._lse_frame(symbol, "5m", max(100, int(os.getenv("LIVE_SIGNAL_HISTORY", "200"))))
            if frame.empty:
                raise RuntimeError("NO_CLOSED_M5_CANDLES")
            closed_key = str(frame.iloc[-1].datetime)
            if _LAST_CLOSED_CANDLE.get(symbol) == closed_key:
                results.append({"status": "waiting_new_candle", "symbol": symbol, "closed_candle": closed_key, "timeframe_mode": TIMEFRAME_MODE, "engine_version": ENGINE_VERSION})
                continue
            result = live_scanner_v11.scan_once(symbol)
            result.update({"trigger": "NEW_CLOSED_M5_CANDLE", "candle_consumed": True, "market_session": session, "engine_version": ENGINE_VERSION, "timeframe_mode": TIMEFRAME_MODE, "timeframes": list(TIMEFRAMES)})
            results.append(result)
            _LAST_CLOSED_CANDLE[symbol] = closed_key
            _log_decision(symbol, result)
            logger.warning(
                "[V12 SCHEDULER] %s result status=%s strategy=%s side=%s selected_engine=%s mode=%s engine=%s",
                symbol, result.get("status"), result.get("strategy"), result.get("signal"),
                result.get("engine") or _trace_source(result).get("engine"), TIMEFRAME_MODE, ENGINE_VERSION,
            )
        except Exception as exc:
            if _is_stale_market_data_error(exc):
                message = str(exc)
                logger.warning(
                    "[V12 DATA] %s skipped: stale provider candle feed; no signal generated. %s",
                    symbol, message,
                )
                results.append({
                    "status": "market_data_stale",
                    "symbol": symbol,
                    "error_type": type(exc).__name__,
                    "message": message,
                    "timeframe_mode": TIMEFRAME_MODE,
                    "engine_version": ENGINE_VERSION,
                    "live_orders_allowed": False,
                })
                continue
            logger.exception("[V12 SCHEDULER] %s scan failed: %s", symbol, exc)
            _notify_error(exc, f"การสแกน {symbol}")
            results.append({"status": "scan_error", "symbol": symbol, "error_type": type(exc).__name__, "message": str(exc), "timeframe_mode": TIMEFRAME_MODE, "engine_version": ENGINE_VERSION, "live_orders_allowed": False})
    _LAST_RESULTS = results
    return results


def _loop():
    logger.warning(
        "[V12 SCHEDULER] Thread entered; performing initial MTF scan H1→M15→M5 on latest closed M5 candle engine=%s",
        ENGINE_VERSION,
    )
    if _RUNNING:
        try:
            run_scan_cycle()
        except Exception as exc:
            logger.exception("[V12 SCHEDULER] Initial MTF scan failed: %s", exc)
    while _RUNNING:
        wait = _seconds_to_next_boundary()
        logger.warning(
            "[V12 SCHEDULER] Waiting %.1fs for next closed M5 boundary; mode=%s engine=%s",
            wait, TIMEFRAME_MODE, ENGINE_VERSION,
        )
        time.sleep(wait)
