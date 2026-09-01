from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import Any

from lse import LSE

DEFAULT_SYMBOLS = {"GOLD": "XAU/USD", "BTC": "BTC/USD"}
CANDLE_INTERVAL = timedelta(minutes=5)


class LiveMarketData:
    def __init__(self):
        key = os.getenv("LSE_API_KEY")
        if not key:
            raise RuntimeError("LSE_API_KEY is required")
        self.client = LSE(api_key=key)

    @staticmethod
    def symbols() -> dict[str, str]:
        configured = os.getenv("TRADING_SYMBOLS", "GOLD,BTC").split(",")
        return {name.strip(): DEFAULT_SYMBOLS[name.strip()] for name in configured if name.strip() in DEFAULT_SYMBOLS}

    @staticmethod
    def _utc_time(value: str, default: time) -> time:
        try:
            hour, minute = value.strip().split(":", 1)
            return time(int(hour), int(minute))
        except (AttributeError, ValueError):
            return default

    @staticmethod
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

    def market_is_open(self, alias: str, now: datetime | None = None) -> bool:
        alias = alias.upper()
        if alias == "BTC":
            return True

        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if now.weekday() >= 5:
            return False

        start = self._utc_time(os.getenv("GOLD_DAILY_BREAK_START_UTC", "21:00"), time(21, 0))
        end = self._utc_time(os.getenv("GOLD_DAILY_BREAK_END_UTC", "22:00"), time(22, 0))
        current = now.time()

        if start <= current < end:
            return False
        if now.weekday() == 4 and current >= start:
            return False
        return True

    def candles(self, alias: str, limit: int = 200) -> dict[str, Any]:
        symbol = self.symbols()[alias]
        if not self.market_is_open(alias):
            return {
                "symbol": symbol,
                "timeframe": "M5",
                "bars": [],
                "candle_close_timestamp": None,
                "market_open": False,
                "market_state": "MARKET_CLOSED",
                "closed_candle_only": True,
                "lookahead_allowed": False,
            }

        response = self.client.candles(symbol, "5m", limit=limit, order="desc")
        rows = response.get("data", response) if isinstance(response, dict) else response
        now = datetime.now(timezone.utc)
        bars = []

        # LSE timestamps identify the M5 candle start. A candle is admissible
        # only after start + 5 minutes <= now. Never pass the live/open candle
        # across the market-data boundary.
        for row in reversed(rows or []):
            source_timestamp = row.get("timestamp")
            start = self._parse_timestamp(source_timestamp)
            if start is None:
                continue
            close_time = start + CANDLE_INTERVAL
            if close_time > now:
                continue
            timestamp = start.isoformat().replace("+00:00", "Z")
            bars.append({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "timestamp": timestamp,
                "candle_id": timestamp,
                "is_closed": True,
                "candle_close_timestamp": close_time.isoformat().replace("+00:00", "Z"),
            })

        latest = bars[-1] if bars else None
        return {
            "symbol": symbol,
            "timeframe": "M5",
            "bars": bars,
            # Scheduler identity remains the latest candle start timestamp.
            "candle_close_timestamp": latest.get("timestamp") if latest else None,
            "data_cutoff_timestamp": latest.get("candle_close_timestamp") if latest else None,
            "data_cutoff_candle_id": latest.get("candle_id") if latest else None,
            "market_open": True,
            "market_state": "MARKET_OPEN",
            "closed_candle_only": True,
            "lookahead_allowed": False,
        }
