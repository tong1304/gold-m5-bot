from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        clean.append({k: float(bar[k]) for k in ("open", "high", "low", "close")})
    if not clean:
        raise ValueError("bars are required")
    return {
        "symbol": str(payload.get("symbol") or "UNKNOWN"),
        "timeframe": str(payload.get("timeframe") or "M5"),
        "bars": clean,
        "candle_close_timestamp": payload.get("candle_close_timestamp") or datetime.now(timezone.utc).isoformat(),
    }
