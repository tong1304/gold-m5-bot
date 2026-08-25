from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any

from lse import LSE


DEFAULT_SYMBOLS = {"GOLD": "XAU/USD", "BTC": "BTC/USD"}


@dataclass(frozen=True)
class MarketSession:
    """Provider-safe session policy used BEFORE any market-data fetch.

    GOLD is treated as a 24/5 instrument with a configurable daily maintenance
    break. BTC is 24/7. All times are UTC so the policy is deterministic on
    Render and does not depend on the host's local timezone.
    """

    always_open: bool = False
    weekdays_only: bool = True
    open_time: time = time(0, 0)
    close_time: time = time(23, 59, 59)
    break_start: time | None = None
    break_end: time | None = None

    def is_open(self, now: datetime) -> bool:
        if self.always_open:
            return True
        now = now.astimezone(timezone.utc)
        if self.weekdays_only and now.weekday() >= 5:
            return False

        current = now.time()
        if self.break_start is not None and self.break_end is not None:
            if self.break_start <= current < self.break_end:
                return False

        # Normal same-day session. The defaults are intentionally explicit;
        # provider-specific hours can be overridden with environment variables.
        return self.open_time <= current <= self.close_time


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

    def session(self, alias: str) -> MarketSession:
        alias = alias.upper()
        if alias == "BTC":
            return MarketSession(always_open=True, weekdays_only=False)

        # XAU/USD is normally available 24/5 but has a daily provider/market
        # maintenance window. Keep it configurable because exact session hours
        # are provider-dependent rather than a property of the strategy.
        return MarketSession(
            always_open=False,
            weekdays_only=True,
            open_time=self._utc_time(os.getenv("GOLD_SESSION_OPEN_UTC", "00:00"), time(0, 0)),
            close_time=self._utc_time(os.getenv("GOLD_SESSION_CLOSE_UTC", "23:59"), time(23, 59)),
            break_start=self._utc_time(os.getenv("GOLD_DAILY_BREAK_START_UTC", "21:00"), time(21, 0)),
            break_end=self._utc_time(os.getenv("GOLD_DAILY_BREAK_END_UTC", "22:00"), time(22, 0)),
        )

    def market_is_open(self, alias: str, now: datetime | None = None) -> bool:
        return self.session(alias).is_open(now or datetime.now(timezone.utc))

    def candles(self, alias: str, limit: int = 200) -> dict[str, Any]:
        """Fetch M5 candles only after the market-session gate passes."""
        if not self.market_is_open(alias):
            return {
                "symbol": self.symbols()[alias],
                "timeframe": "M5",
                "bars": [],
                "candle_close_timestamp": None,
                "market_open": False,
                "market_state": "MARKET_CLOSED",
            }

        symbol = self.symbols()[alias]
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
