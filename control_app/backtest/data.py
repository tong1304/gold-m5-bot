from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")


def gold_market_open(ts: pd.Timestamp) -> tuple[bool, str]:
    ny = ts.to_pydatetime().astimezone(NEW_YORK)
    wd = ny.weekday()
    minutes = ny.hour * 60 + ny.minute
    if wd == 5:
        return False, "WEEKEND_CLOSED"
    if wd == 6:
        return (minutes >= 18 * 60, "OPEN" if minutes >= 18 * 60 else "SUNDAY_CLOSED")
    if wd == 4:
        return (minutes < 17 * 60, "OPEN" if minutes < 17 * 60 else "FRIDAY_CLOSED")
    if 17 * 60 <= minutes < 18 * 60:
        return False, "DAILY_BREAK"
    return True, "OPEN"


def _normalize(raw: object, symbol: str, timeframe: str) -> pd.DataFrame:
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = rows.get("data") or rows.get("rows")
    if not isinstance(rows, (list, tuple)):
        raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}")
    candles = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if {"open", "high", "low", "close"}.issubset(row) and any(k in row for k in ("datetime", "timestamp", "time", "date")):
            candles.append(row)
    if not candles:
        raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:no_candles")
    frame = pd.DataFrame(candles)
    if "datetime" not in frame:
        for candidate in ("timestamp", "time", "date"):
            if candidate in frame:
                frame = frame.rename(columns={candidate: "datetime"})
                break
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["datetime", "open", "high", "low", "close"])
    frame = frame.sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
    minutes = {"5m": 5, "15m": 15, "1h": 60}[timeframe]
    now = pd.Timestamp.now(tz="UTC")
    frame = frame[frame["datetime"] + pd.Timedelta(minutes=minutes) <= now]
    return frame.reset_index(drop=True)


def load_historical_frames(symbol: str, start: datetime, end: datetime, api_key: str | None = None) -> dict[str, pd.DataFrame]:
    """Load closed H1/M15/M5 candles without using the live scanner's freshness gate."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if end <= start:
        raise ValueError("end must be after start")
    from lse import LSE

    market = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}[symbol]
    client = LSE(api_key=api_key)
    fetch_start = start - timedelta(days=8)
    result: dict[str, pd.DataFrame] = {}
    for timeframe, minutes in (("5m", 5), ("15m", 15), ("1h", 60)):
        chunk_days = 3 if timeframe == "5m" else 14
        pieces: list[pd.DataFrame] = []
        cursor = fetch_start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=chunk_days), end)
            raw = client.candles(
                market,
                timeframe,
                start=cursor.astimezone(UTC).date().isoformat(),
                end=(chunk_end + timedelta(days=1)).astimezone(UTC).date().isoformat(),
                limit=1000,
                order="desc",
            )
            piece = _normalize(raw, symbol, timeframe)
            if not piece.empty:
                pieces.append(piece)
            cursor = chunk_end
        frame = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=["datetime", "open", "high", "low", "close"])
        frame = frame.sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
        frame = frame[(frame.datetime >= pd.Timestamp(fetch_start)) & (frame.datetime <= pd.Timestamp(end))]
        if symbol == "GOLD" and not frame.empty:
            frame = frame[frame.datetime.map(lambda x: gold_market_open(x)[0])].reset_index(drop=True)
        if len(frame) < 100:
            raise RuntimeError(f"INSUFFICIENT_HISTORICAL_DATA:{symbol}:{timeframe}:bars={len(frame)}")
        result[timeframe] = frame
    return result
