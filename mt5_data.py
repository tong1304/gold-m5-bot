"""Render-only market-data adapter backed by London Strategic Edge (LSE).

No MetaTrader, MT5 bridge, PC, VPS, Binance, or Twelve Data connection is
required. LSE provides stored 5-minute candles directly; higher timeframes
are resampled locally so the scanner uses one cached M5 dataset per symbol.
"""
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

BASE_URL = os.getenv("LSE_BASE_URL", "https://api.londonstrategicedge.com/vault").rstrip("/")
SYMBOLS = {
    "BTC": os.getenv("LSE_BTC_SYMBOL", "BTC/USD").strip(),
    "ETH": os.getenv("LSE_ETH_SYMBOL", "ETH/USD").strip(),
    "SOL": os.getenv("LSE_SOL_SYMBOL", "SOL/USD").strip(),
    "GOLD": os.getenv("LSE_GOLD_SYMBOL", "XAU/USD").strip(),
}
LOGICAL_TO_LSE = {
    "BTC/USDT": SYMBOLS["BTC"], "BTC/USD": SYMBOLS["BTC"],
    "ETH/USDT": SYMBOLS["ETH"], "ETH/USD": SYMBOLS["ETH"],
    "SOL/USDT": SYMBOLS["SOL"], "SOL/USD": SYMBOLS["SOL"],
    "XAU/USDT": SYMBOLS["GOLD"], "XAU/USD": SYMBOLS["GOLD"],
}


def _timeframe(value):
    value = str(value).lower()
    return {"1m":"1m", "5m":"5m", "15m":"15m", "30m":"30m", "45m":"45m", "1h":"1h", "2h":"2h", "4h":"4h", "8h":"8h", "1d":"1d"}.get(value, value)


class LSEMarketData:
    """Cloud market-data provider backed exclusively by London Strategic Edge."""
    def __init__(self):
        self.api_key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("LSE_API_KEY is not configured")
        self.base_url = BASE_URL
        self.last_provider = "lse"
        self._m5_cache = {}
        self._cache_ttl_seconds = max(30, int(os.getenv("LSE_M5_CACHE_SECONDS", "60")))

    @classmethod
    def market_symbol(cls, symbol):
        key = str(symbol or "").strip().upper()
        return LOGICAL_TO_LSE.get(key, SYMBOLS.get(key, key))

    def _request(self, path, params=None):
        response = requests.get(
            f"{self.base_url}{path}",
            params=params or {},
            headers={"x-api-key": self.api_key},
            timeout=20,
        )
        if response.status_code in (401, 403):
            raise RuntimeError(f"LSE authentication failed ({response.status_code})")
        if response.status_code == 429:
            raise RuntimeError("LSE API rate/data allowance limit reached")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("detail"):
            raise RuntimeError(f"LSE API error: {data['detail']}")
        return data

    @staticmethod
    def _normalize_candles(payload):
        if not isinstance(payload, list) or not payload:
            raise RuntimeError("LSE returned no candles")
        frame = pd.DataFrame(payload)
        required = ["ts", "open", "high", "low", "close"]
        missing = [c for c in required if c not in frame.columns]
        if missing:
            raise RuntimeError(f"LSE missing candle fields: {missing}")
        frame["datetime"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
        for column in ["open", "high", "low", "close", "volume"]:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        return (frame.dropna(subset=["datetime", "open", "high", "low", "close"])
                [["datetime", "open", "high", "low", "close", "volume"]]
                .sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True))

    def _fetch_raw_m5(self, provider_symbol):
        now = time.monotonic()
        cached = self._m5_cache.get(provider_symbol)
        if cached and now - cached["time"] < self._cache_ttl_seconds:
            return cached["frame"].copy()

        payload = self._request("/candles", {
            "symbol": provider_symbol,
            "timeframe": "5m",
            "limit": 5000,
            "order": "desc",
        })
        frame = self._normalize_candles(payload)
        if len(frame) < 2:
            raise RuntimeError(f"LSE returned too few M5 candles: {len(frame)}")
        self._m5_cache[provider_symbol] = {"time": now, "frame": frame.copy()}
        print(f"LSE M5 fetched: {provider_symbol} rows={len(frame)}", flush=True)
        return frame

    @staticmethod
    def _resample(frame, minutes):
        work = frame.copy().set_index("datetime")
        result = work.resample(f"{int(minutes)}min", label="left", closed="left").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}).dropna(subset=["open", "high", "low", "close"])
        return result.reset_index()[["datetime", "open", "high", "low", "close", "volume"]]

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        provider_symbol = self.market_symbol(symbol)
        tf = str(timeframe).lower()
        if tf == "5m":
            frame = self._fetch_raw_m5(provider_symbol)
            return frame.tail(min(int(limit), len(frame))).reset_index(drop=True)

        minutes = {"15m":15, "30m":30, "45m":45, "1h":60, "2h":120, "4h":240, "8h":480}.get(tf)
        if minutes is not None:
            frame = self._fetch_raw_m5(provider_symbol)
            higher = self._resample(frame, minutes)
            if len(higher) < 2:
                raise RuntimeError(f"LSE returned too few resampled {tf} candles: {len(higher)}")
            return higher.tail(min(int(limit), len(higher))).reset_index(drop=True)

        payload = self._request("/candles", {
            "symbol": provider_symbol,
            "timeframe": _timeframe(tf),
            "limit": min(max(int(limit), 2), 5000),
            "order": "desc",
        })
        return self._normalize_candles(payload).tail(int(limit)).reset_index(drop=True)

    def fetch_price(self, symbol):
        """Return the latest available candle close from LSE.

        LSE's documented REST surface exposes candles rather than a separate
        /price endpoint, so the newest 5m close is used as the provider price.
        """
        provider_symbol = self.market_symbol(symbol)
        frame = self._fetch_raw_m5(provider_symbol)
        if frame.empty:
            raise RuntimeError(f"LSE returned no price data: {provider_symbol}")
        return float(frame.iloc[-1]["close"]), provider_symbol

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)


# Compatibility aliases for the existing application imports.
TwelveDataMarketData = LSEMarketData
XMMarketData = LSEMarketData
