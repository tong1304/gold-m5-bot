"""CLI for the native V11 replay pipeline. No legacy engine imports."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
from lse import LSE
from v11 import replay
from live_scanner_v11 import _normalize


HISTORICAL_WARMUP = timedelta(days=2)


def _timestamp(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC").to_pydatetime()
    return ts.tz_convert("UTC").to_pydatetime()


def historical_window(start: str, end: str):
    """Return the LSE fetch window: warm-up before start and exclusive end."""
    start_ts = _timestamp(start)
    end_ts = _timestamp(end)
    if end_ts < start_ts:
        raise ValueError("วันสิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น")
    return start_ts - HISTORICAL_WARMUP, end_ts


def _historical_frame(symbol: str, timeframe: str, start: str, end: str):
    market = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}[symbol]
    fetch_start, fetch_end = historical_window(start, end)
    client = LSE()
    raw = client.candles(
        market,
        timeframe,
        start=fetch_start.date().isoformat(),
        end=fetch_end.date().isoformat(),
    )
    frame = _normalize(raw, symbol, timeframe)
    if frame.empty:
        raise RuntimeError(f"NO_HISTORICAL_CANDLES:{symbol}:{timeframe}")
    return frame


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

    # A date-only end value represents the whole calendar day in the web UI.
    replay_end = end + timedelta(days=1) if len(args.end.strip()) == 10 else end

    for symbol in symbols:
        try:
            # Fetch the actual requested historical window plus warm-up instead of
            # using the live scanner's recent-candle/staleness window. The old
            # 5,000-point approach covered only ~17 days of M5 data and could not
            # replay a full month such as 2026-08-01 through 2026-08-24.
            m5 = _historical_frame(symbol, "5m", args.start, args.end)
            m15 = _historical_frame(symbol, "15m", args.start, args.end)
            report = replay.replay_frames(
                m5,
                m15,
                symbol,
                start_time=start,
                end_time=replay_end,
                limit=None,
            )
            reports.append({
                **report,
                "start": args.start,
                "end": args.end,
                "dry_run": bool(args.dry_run),
            })
        except Exception as exc:
            reports.append({
                "status": "failed",
                "symbol": symbol,
                "engine_version": "11.1-HARDENED",
                "error": f"{type(exc).__name__}: {exc}",
                "start": args.start,
                "end": args.end,
                "dry_run": bool(args.dry_run),
            })

    failed = [r for r in reports if r.get("status") == "failed"]
    status = "failed" if failed and len(failed) == len(reports) else ("partial" if failed else ("dry-run" if args.dry_run else "completed"))
    return {
        "status": status,
        "engine_version": "11.1-HARDENED",
        "source": "LSE_HISTORICAL_OHLCV",
        "symbols": symbols,
        "reports": reports,
        "live_orders_allowed": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, default=str, allow_nan=False))
