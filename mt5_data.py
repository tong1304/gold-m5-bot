"""Twelve Data cloud market-data adapter.

Render-only market data: no MetaTrader, MT5 bridge, PC, or VPS is required.
The legacy XMMarketData name is retained for compatibility with the existing scanner.
"""
import os
from datetime import datetime, timezone

import pandas as pd
import requests

BASE_URL = os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")
SYMBOLS = {
    "BTC": os.getenv("TWELVE_DATA_BTC_SYMBOL", "BTC/USD").strip(),
    "ETH": os.getenv("TWELVE_DATA_ETH_SYMBOL", "ETH/USD").strip(),
    "SOL": os.getenv("TWELVE_DATA_SOL_SYMBOL", "SOL/USD").strip(),
    "GOLD": os.getenv("TWELVE_DATA_GOLD_SYMBOL", "XAU/USD").strip(),
}
LOGICAL_TO_TWELVE = {
    "BTC/USDT": SYMBOLS["BTC"], "BTC/USD": SYMBOLS["BTC"],
    "ETH/USDT": SYMBOLS["ETH"], "ETH/USD": SYMBOLS["ETH"],
    "SOL/USDT": SYMBOLS["SOL"], "SOL/USD": SYMBOLS["SOL"],
    "XAU/USDT": SYMBOLS["GOLD"], "XAU/USD": SYMBOLS["GOLD"],
}


def _timeframe(value):
    value = str(value).lower()
    return {"1m":"1min", "5m":"5min", "15m":"15min", "30m":"30min",
            "45m":"45min", "1h":"1h", "2h":"2h", "4h":"4h", "8h":"8h",
            "1d":"1day"}.get(value, value)


class TwelveDataMarketData:
    """Cloud market-data provider backed exclusively by Twelve Data."""
    def __init__(self):
        self.api_key = (os.getenv("TWELVE_DATA_API_KEY", "").strip()
                        or os.getenv("TWELVEDATA_API_KEY", "").strip())
        if not self.api_key:
            raise RuntimeError("TWELVE_DATA_API_KEY is not configured")
        self.base_url = BASE_URL
        self.last_provider = "twelve_data"

    @classmethod
    def market_symbol(cls, symbol):
        key = str(symbol or "").strip().upper()
        return LOGICAL_TO_TWELVE.get(key, SYMBOLS.get(key, key))

    def _request(self, path, params):
        params = dict(params)
        params["apikey"] = self.api_key
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(data.get("message", "Twelve Data API error"))
        return data

    @staticmethod
    def _normalize_candles(payload):
        rows = payload.get("values") if isinstance(payload, dict) else None
        if not rows:
            raise RuntimeError("Twelve Data returned no candles")
        frame = pd.DataFrame(rows)
        required = ["datetime", "open", "high", "low", "close"]
        missing = [c for c in required if c not in frame.columns]
        if missing:
            raise RuntimeError(f"Twelve Data missing candle fields: {missing}")
        frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
        for column in ["open", "high", "low", "close", "volume"]:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        return (frame.dropna(subset=["datetime", "open", "high", "low", "close"])
                [["datetime", "open", "high", "low", "close", "volume"]]
                .sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True))

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        provider_symbol = self.market_symbol(symbol)
        payload = self._request("/time_series", {
            "symbol": provider_symbol,
            "interval": _timeframe(timeframe),
            "outputsize": min(max(int(limit), 2), 5000),
            "order": "asc",
            "timezone": "UTC",
        })
        frame = self._normalize_candles(payload)
        if len(frame) < 2:
            raise RuntimeError(f"Twelve Data returned too few candles: {len(frame)}")
        return frame

    def fetch_price(self, symbol):
        provider_symbol = self.market_symbol(symbol)
        payload = self._request("/price", {"symbol": provider_symbol})
        price = payload.get("price") if isinstance(payload, dict) else None
        if price is None:
            quote = self._request("/quote", {"symbol": provider_symbol})
            price = quote.get("close") or quote.get("price")
        if price is None:
            raise RuntimeError(f"Twelve Data returned no usable price: {provider_symbol}")
        return float(price), provider_symbol

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)


# Compatibility name retained for existing imports.
XMMarketData = TwelveDataMarketData
