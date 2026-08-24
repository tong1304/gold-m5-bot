from __future__ import annotations
from typing import Iterable
import math
import pandas as pd

REQUIRED = ("datetime", "open", "high", "low", "close")

def validate_frame(frame: pd.DataFrame, *, minimum: int = 60, timeframe_minutes: int | None = None) -> list[str]:
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
    if dt.isna().any(): reasons.append("INVALID_DATETIME")
    if dt.duplicated().any(): reasons.append("DUPLICATE_DATETIME")
    if not dt.is_monotonic_increasing: reasons.append("DATETIME_NOT_SORTED")
    for col in REQUIRED[1:]:
        values = pd.to_numeric(frame[col], errors="coerce")
        if values.isna().any(): reasons.append(f"INVALID_{col.upper()}")
        elif not values.map(math.isfinite).all(): reasons.append(f"NONFINITE_{col.upper()}")
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
        if (delta <= 0).any(): reasons.append("NONPOSITIVE_INTERVAL")
        if (delta > timeframe_minutes * 3).any(): reasons.append("LARGE_DATA_GAP")
    return reasons

def require_closed(frame: pd.DataFrame, *, timeframe_minutes: int, now=None) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty: return frame
    dt = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if current.tzinfo is None: current = current.tz_localize("UTC")
    cutoff = current.floor(f"{timeframe_minutes}min")
    out = frame.loc[dt < cutoff].copy()
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True, errors="coerce")
    return out.sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
