from __future__ import annotations

import os
from datetime import datetime, time, timezone
from typing import Any

from lse import LSE

DEFAULT_SYMBOLS = {"GOLD": "XAU/USD", "BTC": "BTC/USD"}


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
            }

        response = self.client.candles(symbol, "5m", limit=limit, order="desc")
        rows = response.get("data", response) if isinstance(response, dict) else response
        bars = []
        for row in reversed(rows or []):
            bars.append({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
        return {
            "symbol": symbol,
            "timeframe": "M5",
            "bars": bars,
            "candle_close_timestamp": (rows[0].get("timestamp") if rows else None),
            "market_open": True,
            "market_state": "MARKET_OPEN",
        }
