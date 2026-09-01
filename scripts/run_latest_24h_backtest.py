from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from lse import LSE

from v11.replay_m5 import REPLAY_H1_CONTEXT_BARS, REPLAY_M15_CONTEXT_BARS, REPLAY_M5_CONTEXT_BARS, replay_frames

SYMBOL = "GOLD"
MARKET = "XAU/USD"
TIMEFRAME = "5m"
OUT = Path("latest_24h_gold_backtest.json")
# 100 H1 bars are required before the replay can evaluate M5 candles. Fetch
# enough M5 history to construct both H1 and M15 context without lookahead.
WARMUP_HOURS = max(REPLAY_H1_CONTEXT_BARS, REPLAY_M15_CONTEXT_BARS / 4) + 2


def build_latest_24h_window(now: datetime) -> tuple[datetime, datetime]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    end = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(hours=24)
    return start, end


def _fetch_day(client: LSE, day: pd.Timestamp) -> pd.DataFrame:
    raw = client.candles(
        MARKET,
        TIMEFRAME,
        start=day.date().isoformat(),
        end=(day + pd.Timedelta(days=1)).date().isoformat(),
        limit=1000,
        order="asc",
    )
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("rows")
    if not isinstance(rows, (list, tuple)):
        raise RuntimeError(f"LSE_INVALID_RESPONSE:{MARKET}:{day.date().isoformat()}")
    frame = pd.DataFrame(rows)
    for candidate in ("timestamp", "time", "date"):
        if "datetime" not in frame.columns and candidate in frame.columns:
            frame = frame.rename(columns={candidate: "datetime"})
    required = ("datetime", "open", "high", "low", "close")
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise RuntimeError(f"LSE_INVALID_RESPONSE:missing={missing}:day={day.date().isoformat()}")
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    for col in required[1:]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return (
        frame.dropna(subset=list(required))
        .sort_values("datetime")
        .drop_duplicates("datetime", keep="last")
        .reset_index(drop=True)
    )


def _aggregate(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    x = frame.set_index("datetime")["open high low close".split()].resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    return x.dropna().reset_index()


def fetch_history(client: LSE, start: datetime, end: datetime) -> tuple[pd.DataFrame, dict]:
    fetch_start = pd.Timestamp(start - timedelta(hours=WARMUP_HOURS)).floor("D")
    fetch_end = pd.Timestamp(end).ceil("D")
    days = []
    day = fetch_start
    while day < fetch_end:
        days.append(_fetch_day(client, day))
        day += pd.Timedelta(days=1)
    frame = pd.concat(days, ignore_index=True).sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
    target = frame[(frame.datetime >= pd.Timestamp(start)) & (frame.datetime < pd.Timestamp(end))]
    if len(frame) < REPLAY_M5_CONTEXT_BARS + 1 or target.empty:
        raise RuntimeError(f"INSUFFICIENT_LATEST_24H_GOLD_M5:history={len(frame)}:target={len(target)}")
    gaps = target.datetime.diff().dropna() / pd.Timedelta(minutes=5)
    quality = {
        "source": "LSE_HISTORICAL_M5_OHLCV",
        "market": MARKET,
        "historical_m5_rows": len(frame),
        "target_m5_rows": len(target),
        "first_target_candle": str(target.iloc[0].datetime),
        "last_target_candle": str(target.iloc[-1].datetime),
        "five_minute_gap_count": int((gaps > 1).sum()),
        "calendar_days_fetched": len(days),
        "warmup_hours": WARMUP_HOURS,
        "lookahead_safe": True,
    }
    return frame, quality


def main() -> None:
    now = datetime.now(timezone.utc)
    start, end = build_latest_24h_window(now)
    client = LSE(api_key=os.environ["LSE_API_KEY"])
    m5, quality = fetch_history(client, start, end)
    m15 = _aggregate(m5, "15min")
    h1 = _aggregate(m5, "1h")
    report = replay_frames(m5, m15, h1, SYMBOL, start_time=start, end_time=end)
    payload = {
        "status": "completed",
        "symbol": SYMBOL,
        "market": MARKET,
        "engine_version": report.get("engine_version"),
        "engine_name": "CURRENT_PRODUCTION_V2",
        "timeframe_mode": report.get("timeframe_mode"),
        "lookahead_safe": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration_hours": 24,
        "data_quality": quality,
        "summary": {
            "candles_evaluated": report.get("candles_evaluated"),
            "signals": report.get("signals"),
            "wins": report.get("wins"),
            "losses": report.get("losses"),
            "ambiguous": report.get("ambiguous"),
            "open": report.get("open"),
            "net_r": report.get("net_r"),
            "performance": report.get("performance"),
        },
        "trade_history": report.get("trade_history", []),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "start": payload["start"], "end": payload["end"], "summary": payload["summary"]}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
