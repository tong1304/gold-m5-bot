from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from v11 import engine as v12_engine
import live_scanner_v11

logger = logging.getLogger("signal_scheduler")
ENGINE_VERSION = v12_engine.ENGINE_VERSION
TIMEFRAME_MODE = "MTF:H1→M15→M5"
TIMEFRAMES = ("H1", "M15", "M5")
BANGKOK = ZoneInfo("Asia/Bangkok")
NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
DISPLAY_SYMBOLS = ("BTC", "GOLD")
_RUNNING = False
_THREAD = None
_LAST_CLOSED_CANDLE = {}
_STARTED_AT = None
_LAST_CYCLE_AT = None
_LAST_RESULTS = []
_CYCLE_COUNT = 0

STRATEGIES = [
    "B1_RANGE_SWEEP_DISPLACEMENT",
    "B2_HTF_ZONE_M5_FVG_RETEST",
    "B3_VOLATILITY_EXPANSION_BREAKOUT_RETEST",
    "G1_LIQUIDITY_SWEEP_CHOCH",
    "G2_HTF_ZONE_M5_FVG_RETEST",
    "G3_VOLATILITY_EXPANSION_BREAKOUT_RETEST",
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
    if symbol != "GOLD":
        return False, "UNKNOWN_MARKET_SESSION"
    ny = now_utc.astimezone(NEW_YORK)
    wd = ny.weekday()
    minutes = ny.hour * 60 + ny.minute
    if wd == 5:
        return False, "WEEKEND_CLOSED"
    if wd == 6:
        opened = minutes >= 18 * 60
        return opened, "OPEN" if opened else "SUNDAY_CLOSED"
    if wd == 4:
        opened = minutes < 17 * 60
        return opened, "OPEN" if opened else "FRIDAY_CLOSED"
    if 17 * 60 <= minutes < 18 * 60:
        return False, "DAILY_BREAK"
    return True, "OPEN"


def _is_stale_market_data_error(exc):
    return "STALE_MARKET_DATA:" in str(exc)


def _log_decision(symbol, result):
    try:
        setup = result.get("setup") if isinstance(result.get("setup"), dict) else result
        selected = result.get("selected_setup") or setup.get("selected_setup") or setup
        if not isinstance(selected, dict):
            selected = {}
        engine = result.get("engine") or setup.get("engine") or selected.get("engine") or "NONE"
        strategy = result.get("strategy") or setup.get("strategy") or selected.get("strategy") or "NONE"
        signal = result.get("signal") or setup.get("signal") or "NO_TRADE"
        logger.warning(
            "[SCHEDULER] %s FINAL=%s ENGINE=%s STRATEGY=%s",
            symbol, signal, engine, strategy,
        )
    except Exception as exc:
        logger.exception("[SCHEDULER] %s decision logging failed: %s", symbol, exc)


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
        "[SCHEDULER] Scan cycle #%s started at %s Bangkok symbols=%s mode=%s engine=%s",
        _CYCLE_COUNT, now_bkk.strftime("%Y-%m-%d %H:%M:%S"), _symbols(), TIMEFRAME_MODE, ENGINE_VERSION,
    )

    for symbol in _symbols():
        try:
            opened, session = _asset_market_status(symbol, now_utc)
            if not opened:
                logger.warning("[SESSION] %s skipped: %s", symbol, session)
                results.append({"status": "market_closed", "symbol": symbol, "session": session, "live_orders_allowed": False, "engine_version": ENGINE_VERSION})
                continue

            frame = live_scanner_v11._lse_frame(
                symbol, "5m", max(100, int(os.getenv("LIVE_SIGNAL_HISTORY", "200")))
            )
            if frame.empty:
                raise RuntimeError("NO_CLOSED_M5_CANDLES")

            closed_key = str(frame.iloc[-1].datetime)
            if _LAST_CLOSED_CANDLE.get(symbol) == closed_key:
                results.append({
                    "status": "waiting_new_candle",
                    "symbol": symbol,
                    "closed_candle": closed_key,
                    "timeframe_mode": TIMEFRAME_MODE,
                    "engine_version": ENGINE_VERSION,
                })
                continue

            result = live_scanner_v11.scan_once(symbol)
            result.update({
                "trigger": "NEW_CLOSED_M5_CANDLE",
                "candle_consumed": True,
                "market_session": session,
                "engine_version": ENGINE_VERSION,
                "timeframe_mode": TIMEFRAME_MODE,
                "timeframes": list(TIMEFRAMES),
            })
            results.append(result)
            _LAST_CLOSED_CANDLE[symbol] = closed_key
            _log_decision(symbol, result)

        except Exception as exc:
            if _is_stale_market_data_error(exc):
                logger.warning("[DATA] %s skipped: stale provider candle feed: %s", symbol, exc)
                results.append({
                    "status": "market_data_stale",
                    "symbol": symbol,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "timeframe_mode": TIMEFRAME_MODE,
                    "engine_version": ENGINE_VERSION,
                    "live_orders_allowed": False,
                })
                continue
            logger.exception("[SCHEDULER] %s scan failed: %s", symbol, exc)
            results.append({
                "status": "scan_error",
                "symbol": symbol,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "timeframe_mode": TIMEFRAME_MODE,
                "engine_version": ENGINE_VERSION,
                "live_orders_allowed": False,
            })

    _LAST_RESULTS = results
    return results


def _loop():
    logger.warning(
        "[SCHEDULER] Thread entered; scanning latest closed M5 candle engine=%s",
        ENGINE_VERSION,
    )
    if _RUNNING:
        try:
            run_scan_cycle()
        except Exception:
            logger.exception("[SCHEDULER] Initial scan failed")

    while _RUNNING:
        time.sleep(_seconds_to_next_boundary())
        if _RUNNING:
            try:
                run_scan_cycle()
            except Exception:
                logger.exception("[SCHEDULER] Scheduled scan failed")


def start():
    global _RUNNING, _THREAD, _STARTED_AT
    if _RUNNING and _THREAD and _THREAD.is_alive():
        return False
    _RUNNING = True
    _STARTED_AT = datetime.now(UTC).isoformat()
    _THREAD = threading.Thread(target=_loop, name="production-v2-scheduler", daemon=True)
    _THREAD.start()
    logger.warning(
        "[SCHEDULER] STARTED engine=%s interval=%ss symbols=%s mode=%s timeframes=%s telegram_monitor=DISABLED",
        ENGINE_VERSION, _interval_seconds(), _symbols(), TIMEFRAME_MODE, "/".join(TIMEFRAMES),
    )
    return True


def stop():
    global _RUNNING
    _RUNNING = False


def status():
    try:
        import live_price
        live = live_price.status()
    except Exception as exc:
        live = {"running": False, "error": str(exc)}
    return {
        "running": bool(_RUNNING and _THREAD and _THREAD.is_alive()),
        "interval_seconds": _interval_seconds(),
        "symbols": _symbols(),
        "timezone": "Asia/Bangkok",
        "provider": "LSE",
        "engine_version": ENGINE_VERSION,
        "scanner": "live_scanner_v11",
        "multi_strategy": True,
        "strategies": STRATEGIES,
        "timeframes": list(TIMEFRAMES),
        "timeframe_mode": TIMEFRAME_MODE,
        "started_at": _STARTED_AT,
        "last_cycle_at": _LAST_CYCLE_AT,
        "cycle_count": _CYCLE_COUNT,
        "last_results": _LAST_RESULTS,
        "live_price": live,
        "telegram_monitor_running": False,
        "telegram_monitor": "DISABLED - owned by production_v2_monitor.py",
        "live_orders_allowed": False,
    }
