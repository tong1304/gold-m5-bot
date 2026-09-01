from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_CLOSURE_KEYS = ("is_closed", "closed", "complete", "is_complete", "closed_candle", "candle_closed")


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def normalize_market_data(payload: dict[str, Any]) -> dict[str, Any]:
    bars = payload.get("bars") or []
    if not isinstance(bars, list):
        raise ValueError("bars must be a list")
    clean = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        if not all(k in bar for k in ("open", "high", "low", "close")):
            continue
        closure_flags = [bool(bar[k]) for k in _CLOSURE_KEYS if k in bar]
        if not closure_flags:
            raise ValueError("CLOSED_CANDLE_STATUS_REQUIRED")
        if not all(closure_flags):
            continue
        item = {k: float(bar[k]) for k in ("open", "high", "low", "close")}
        for key in ("id", "candle_id", "timestamp", "time", "candle_close_timestamp"):
            if bar.get(key) is not None:
                item[key] = str(bar[key])
        item["is_closed"] = True
        clean.append(item)
    if not clean:
        raise ValueError("bars are required")

    candle_identity = clean[-1].get("candle_id") or clean[-1].get("id") or clean[-1].get("timestamp") or clean[-1].get("time")
    cutoff_timestamp = payload.get("data_cutoff_timestamp")
    if cutoff_timestamp is None:
        cutoff_timestamp = clean[-1].get("candle_close_timestamp")
    if cutoff_timestamp is None:
        source = payload.get("candle_close_timestamp")
        parsed = _parse_timestamp(source)
        cutoff_timestamp = parsed.isoformat().replace("+00:00", "Z") if parsed is not None else source

    return {
        "symbol": str(payload.get("symbol") or "UNKNOWN"),
        "timeframe": str(payload.get("timeframe") or "M5"),
        "bars": clean,
        "candle_close_timestamp": payload.get("candle_close_timestamp") or clean[-1].get("timestamp") or clean[-1].get("time"),
        "data_cutoff_candle_id": payload.get("data_cutoff_candle_id") or candle_identity,
        "data_cutoff_timestamp": cutoff_timestamp,
        "closed_candle_only": True,
        "lookahead_allowed": False,
    }
