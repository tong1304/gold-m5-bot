"""Render-only market-data adapter backed by Twelve Data.

No MetaTrader, MT5 bridge, PC, or VPS is required. Higher timeframes are
resampled locally from the same cached M5 dataset to keep Twelve Data usage
low enough for the free daily allowance.
"""
import os
import time
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
    return {"1m":"1min", "5m":"5min", "15m":"15min", "30m":"30min", "45m":"45min", "1h":"1h", "2h":"2h", "4h":"4h", "8h":"8h", "1d":"1day"}.get(value, value)


class TwelveDataMarketData:
    """Cloud market-data provider backed exclusively by Twelve Data."""
    def __init__(self):
        self.api_key = os.getenv("TWELVE_DATA_API_KEY", "").strip() or os.getenv("TWELVEDATA_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("TWELVE_DATA_API_KEY is not configured")
        self.base_url = BASE_URL
        self.last_provider = "twelve_data"
        self._m5_cache = {}
        self._cache_ttl_seconds = max(30, int(os.getenv("TWELVE_DATA_M5_CACHE_SECONDS", "60")))

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

    def _fetch_raw_m5(self, provider_symbol, limit):
        now = time.monotonic()
        cached = self._m5_cache.get(provider_symbol)
        if cached and now - cached["time"] < self._cache_ttl_seconds:
            return cached["frame"].copy()

        # Always fill the cache with a full strategy history. The scheduler's
        # 5-minute system test and scan then share this single API request.
        fetch_limit = 5000
        payload = self._request("/time_series", {
            "symbol": provider_symbol,
            "interval": "5min",
            "outputsize": fetch_limit,
            "order": "asc",
            "timezone": "UTC",
        })
        frame = self._normalize_candles(payload)
        if len(frame) < 2:
            raise RuntimeError(f"Twelve Data returned too few M5 candles: {len(frame)}")
        self._m5_cache[provider_symbol] = {"time": now, "frame": frame.copy()}
        print(f"Twelve Data M5 fetched: {provider_symbol} rows={len(frame)}", flush=True)
        return frame

    @staticmethod
    def _resample(frame, minutes):
        work = frame.copy().set_index("datetime")
        result = work.resample(f"{int(minutes)}min", label="left", closed="left").agg({"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}).dropna(subset=["open", "high", "low", "close"])
        result = result.reset_index()
        return result[["datetime", "open", "high", "low", "close", "volume"]]

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        provider_symbol = self.market_symbol(symbol)
        tf = str(timeframe).lower()
        if tf == "5m":
            frame = self._fetch_raw_m5(provider_symbol, limit)
            return frame.tail(min(int(limit), len(frame))).reset_index(drop=True)

        minutes = {"15m":15, "30m":30, "45m":45, "1h":60, "2h":120, "4h":240, "8h":480}.get(tf)
        if minutes is not None:
            frame = self._fetch_raw_m5(provider_symbol, 5000)
            higher = self._resample(frame, minutes)
            if len(higher) < 2:
                raise RuntimeError(f"Twelve Data returned too few resampled {tf} candles: {len(higher)}")
            return higher.tail(min(int(limit), len(higher))).reset_index(drop=True)

        payload = self._request("/time_series", {"symbol":provider_symbol, "interval":_timeframe(tf), "outputsize":min(max(int(limit),2),5000), "order":"asc", "timezone":"UTC"})
        return self._normalize_candles(payload).tail(int(limit)).reset_index(drop=True)

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


XMMarketData = TwelveDataMarketData
