from __future__ import annotations

import os
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

    def candles(self, alias: str, limit: int = 200) -> dict[str, Any]:
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
        return {"symbol": symbol, "timeframe": "M5", "bars": bars,
                "candle_close_timestamp": (rows[0].get("timestamp") if rows else None)}
