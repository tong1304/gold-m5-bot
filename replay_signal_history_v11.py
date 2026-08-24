"""CLI for the native V11 replay pipeline. No legacy engine imports."""
from __future__ import annotations

import argparse
import json
import os
from datetime import timedelta

import pandas as pd
from lse import LSE
from v11 import replay
from live_scanner_v11 import _normalize


HISTORICAL_WARMUP = timedelta(days=2)
HISTORICAL_CHUNK_BY_TIMEFRAME = {
    "5m": timedelta(days=2),
    "15m": timedelta(days=4),
}


def _progress(event, **payload):
    """Emit machine-readable progress without corrupting the final JSON result."""
    print(json.dumps({"_replay_progress": event, **payload}, ensure_ascii=False, default=str), flush=True)


def _timestamp(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC").to_pydatetime()
    return ts.tz_convert("UTC").to_pydatetime()


def historical_window(start: str, end: str):
    start_ts = _timestamp(start)
    end_ts = _timestamp(end)
    if end_ts < start_ts:
        raise ValueError("วันสิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น")
    return start_ts - HISTORICAL_WARMUP, end_ts


def _historical_frame(symbol: str, timeframe: str, start: str, end: str):
    market = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}[symbol]
    chunk_size = HISTORICAL_CHUNK_BY_TIMEFRAME[timeframe]
    fetch_start, fetch_end = historical_window(start, end)
    if len(end.strip()) == 10:
        fetch_end = fetch_end + timedelta(days=1)
    api_key = os.getenv("LSE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("LSE_API_KEY_MISSING: Replay requires the same LSE_API_KEY used by Live V11")
    client = LSE(api_key=api_key)
    frames = []
    cursor = fetch_start
    total_chunks = max(1, (fetch_end - fetch_start + chunk_size - timedelta(microseconds=1)) // chunk_size)
    chunk_no = 0
    while cursor < fetch_end:
        chunk_no += 1
        chunk_end = min(cursor + chunk_size, fetch_end)
        _progress("fetching", symbol=symbol, timeframe=timeframe, chunk=chunk_no, total_chunks=int(total_chunks), start=cursor.isoformat(), end=chunk_end.isoformat())
        raw = client.candles(market, timeframe, start=cursor.date().isoformat(), end=chunk_end.date().isoformat())
        frame = _normalize(raw, symbol, timeframe)
        if not frame.empty:
            frames.append(frame)
        _progress("fetched", symbol=symbol, timeframe=timeframe, chunk=chunk_no, rows=int(len(frame)))
        cursor = chunk_end
    if not frames:
        raise RuntimeError(f"NO_HISTORICAL_CANDLES:{symbol}:{timeframe}")
    result = pd.concat(frames, ignore_index=True).sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
    _progress("history_ready", symbol=symbol, timeframe=timeframe, rows=int(len(result)))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--symbol", choices=["BTC", "GOLD", "ALL"], default="ALL")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    symbols = [args.symbol] if args.symbol != "ALL" else ["BTC", "GOLD"]
    reports = []
    start = _timestamp(args.start)
    end = _timestamp(args.end)
    if end < start:
        raise ValueError("วันสิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น")
    replay_end = end + timedelta(days=1) if len(args.end.strip()) == 10 else end
    _progress("started", symbols=symbols, start=args.start, end=args.end)

    for symbol in symbols:
        try:
            _progress("symbol_started", symbol=symbol)
            m5 = _historical_frame(symbol, "5m", args.start, args.end)
            m15 = _historical_frame(symbol, "15m", args.start, args.end)
            _progress("engine_started", symbol=symbol, m5_rows=int(len(m5)), m15_rows=int(len(m15)))
            report = replay.replay_frames(
                m5, m15, symbol, start_time=start, end_time=replay_end, limit=None,
                progress_callback=_progress,
            )
            reports.append({**report, "start": args.start, "end": args.end, "dry_run": bool(args.dry_run)})
            performance = report.get("performance") or {}
            _progress("symbol_completed", symbol=symbol, candles=int(len(m5)), trades=int(performance.get("trades", 0)), wins=int(performance.get("wins", 0)), losses=int(performance.get("losses", 0)), open=int(performance.get("open", 0)), net_r=performance.get("net_r", 0))
        except Exception as exc:
            reports.append({"status":"failed","symbol":symbol,"engine_version":"11.1-HARDENED","error":f"{type(exc).__name__}: {exc}","start":args.start,"end":args.end,"dry_run":bool(args.dry_run)})
            _progress("symbol_failed", symbol=symbol, error=f"{type(exc).__name__}: {exc}")

    failed = [r for r in reports if r.get("status") == "failed"]
    status = "failed" if failed and len(failed) == len(reports) else ("partial" if failed else ("dry-run" if args.dry_run else "completed"))
    result = {"status":status,"engine_version":"11.1-HARDENED","source":"LSE_HISTORICAL_OHLCV","symbols":symbols,"reports":reports,"live_orders_allowed":False}
    _progress("completed", status=status)
    return result


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, default=str, allow_nan=False), flush=True)
