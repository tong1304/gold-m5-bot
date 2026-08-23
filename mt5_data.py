"""XM MetaTrader 5 market-data adapter used by the cloud signal engine.

The cloud service talks only to a small MT5 bridge running beside the XM MT5
terminal. No Binance/Kraken fallback is used.
"""
import os
from datetime import datetime, timezone

import pandas as pd
import requests


MT5_SYMBOLS = {
    "BTC": os.getenv("MT5_BTC_SYMBOL", "BTCUSD").strip(),
    "GOLD": os.getenv("MT5_GOLD_SYMBOL", "XAUUSD").strip(),
}
LOGICAL_TO_MT5 = {
    "BTC/USDT": MT5_SYMBOLS["BTC"],
    "XAU/USDT": MT5_SYMBOLS["GOLD"],
}


def _timeframe(value):
    value = str(value).lower()
    mapping = {"1m":"M1", "5m":"M5", "15m":"M15", "30m":"M30",
               "1h":"H1", "4h":"H4", "1d":"D1"}
    return mapping.get(value, value.upper())


def normalize_bridge_candles(payload):
    rows = payload.get("candles") if isinstance(payload, dict) else None
    if not rows:
        raise RuntimeError("XM MT5 bridge returned no candles")
    frame = pd.DataFrame(rows)
    required = ["time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise RuntimeError(f"XM MT5 bridge missing candle fields: {missing}")
    frame["datetime"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    for column in ["open", "high", "low", "close", "tick_volume", "real_volume"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "tick_volume" in frame.columns:
        frame["volume"] = frame["tick_volume"]
    elif "real_volume" in frame.columns:
        frame["volume"] = frame["real_volume"]
    else:
        frame["volume"] = 0
    frame = frame.dropna(subset=["datetime", "open", "high", "low", "close"])
    return frame[["datetime", "open", "high", "low", "close", "volume"]].sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)


class XMMarketData:
    def __init__(self):
        self.base_url = os.getenv("MT5_BRIDGE_URL", "").strip().rstrip("/")
        self.token = os.getenv("MT5_BRIDGE_TOKEN", "").strip()
        if not self.base_url:
            raise RuntimeError("MT5_BRIDGE_URL is not configured; XM MT5 bridge is required")
        self.last_provider = "xm_mt5"

    @classmethod
    def market_symbol(cls, symbol):
        key = str(symbol or "").strip().upper()
        return LOGICAL_TO_MT5.get(key, MT5_SYMBOLS.get(key, key))

    def _request(self, path, params):
        headers = {"X-MT5-BRIDGE-TOKEN": self.token} if self.token else {}
        response = requests.get(f"{self.base_url}{path}", params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(data.get("message", "XM MT5 bridge error"))
        return data

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        mt5_symbol = self.market_symbol(symbol)
        payload = self._request("/candles", {
            "symbol": mt5_symbol,
            "timeframe": _timeframe(timeframe),
            "limit": min(max(int(limit), 2), 5000),
        })
        frame = normalize_bridge_candles(payload)
        if len(frame) < 2:
            raise RuntimeError(f"XM MT5 returned too few candles: {len(frame)}")
        return frame

    def fetch_price(self, symbol):
        mt5_symbol = self.market_symbol(symbol)
        payload = self._request("/price", {"symbol": mt5_symbol})
        price = payload.get("last") or payload.get("bid") or payload.get("ask")
        if price is None:
            raise RuntimeError(f"XM MT5 tick has no usable price: {mt5_symbol}")
        return float(price), mt5_symbol

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)
