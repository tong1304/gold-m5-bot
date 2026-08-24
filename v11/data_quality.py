from __future__ import annotations

import math
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd

REQUIRED = ("datetime", "open", "high", "low", "close")
_NEW_YORK = ZoneInfo("America/New_York")
_GOLD_CLOSE = time(17, 0)
_GOLD_OPEN = time(18, 0)


def _gold_market_closed(timestamp: pd.Timestamp) -> bool:
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    local = timestamp.tz_convert(_NEW_YORK)
    wd = local.weekday()
    current = local.time()
    if wd == 5:
        return True
    if wd == 6:
        return current < _GOLD_OPEN
    if wd == 4:
        return current >= _GOLD_CLOSE
    return _GOLD_CLOSE <= current < _GOLD_OPEN


def _gap_is_expected_session_gap(start: pd.Timestamp, end: pd.Timestamp, timeframe_minutes: int) -> bool:
    """Check missing candle slots, including the Friday->Sunday GOLD closure.

    Candle timestamps are treated as candle-open timestamps.  A gap is expected
    only when every missing slot is inside a known GOLD closure window.
    """
    if timeframe_minutes <= 0 or end <= start:
        return False
    missing = pd.date_range(
        start=start + pd.Timedelta(minutes=timeframe_minutes),
        end=end - pd.Timedelta(minutes=timeframe_minutes),
        freq=f"{timeframe_minutes}min",
        tz="UTC",
    )
    if len(missing) == 0:
        return False
    return all(_gold_market_closed(ts) for ts in missing)


def validate_frame(frame: pd.DataFrame, *, minimum: int = 60, timeframe_minutes: int | None = None, market: str | None = None) -> list[str]:
    reasons: list[str] = []
    if not isinstance(frame, pd.DataFrame):
        return ["FRAME_NOT_DATAFRAME"]
    if len(frame) < minimum:
        reasons.append("INSUFFICIENT_CONTEXT")
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        reasons.append("MISSING_COLUMNS:" + ",".join(missing))
        return reasons
    dt = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    if dt.isna().any():
        reasons.append("INVALID_DATETIME")
    if dt.duplicated().any():
        reasons.append("DUPLICATE_DATETIME")
    if not dt.is_monotonic_increasing:
        reasons.append("DATETIME_NOT_SORTED")
    for col in REQUIRED[1:]:
        values = pd.to_numeric(frame[col], errors="coerce")
        if values.isna().any():
            reasons.append(f"INVALID_{col.upper()}")
        elif not values.map(math.isfinite).all():
            reasons.append(f"NONFINITE_{col.upper()}")
    try:
        high = pd.to_numeric(frame.high, errors="coerce")
        low = pd.to_numeric(frame.low, errors="coerce")
        op = pd.to_numeric(frame.open, errors="coerce")
        cl = pd.to_numeric(frame.close, errors="coerce")
        if ((high < low) | (op > high) | (op < low) | (cl > high) | (cl < low)).any():
            reasons.append("OHLC_INCONSISTENT")
    except Exception:
        reasons.append("OHLC_VALIDATION_ERROR")
    if timeframe_minutes and len(dt) > 1:
        delta = dt.diff().dropna().dt.total_seconds() / 60.0
        if (delta <= 0).any():
            reasons.append("NONPOSITIVE_INTERVAL")
        for index, gap in delta.items():
            if gap <= timeframe_minutes * 3:
                continue
            start = dt.iloc[index - 1]
            end = dt.iloc[index]
            if str(market or "").upper() == "GOLD" and _gap_is_expected_session_gap(start, end, timeframe_minutes):
                continue
            reasons.append("LARGE_DATA_GAP")
            break
    return reasons


def require_closed(frame: pd.DataFrame, *, timeframe_minutes: int, now=None) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    dt = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    cutoff = current.floor(f"{timeframe_minutes}min")
    out = frame.loc[dt < cutoff].copy()
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True, errors="coerce")
    return out.sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
