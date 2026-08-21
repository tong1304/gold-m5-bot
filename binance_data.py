"""Binance public market-data adapter for the signal engine.

This module deliberately uses CCXT's public OHLCV endpoint only. API keys are
not required for candles and are not used for order placement.
"""
import os
from datetime import datetime, timezone

import ccxt
import pandas as pd


class BinanceMarketData:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret = os.getenv("BINANCE_API_SECRET", "").strip()
        self.exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": os.getenv("BINANCE_DEFAULT_TYPE", "spot")},
        })

    @staticmethod
    def normalize_ohlcv(ohlcv):
        frame = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        if frame.empty:
            raise RuntimeError("Binance returned no OHLCV candles")
        frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(
            subset=["datetime", "open", "high", "low", "close"]
        )
        frame = frame[["datetime", "open", "high", "low", "close", "volume"]]
        return frame.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        self.exchange.load_markets()
        if symbol not in self.exchange.markets:
            raise RuntimeError(f"Binance market is unavailable: {symbol}")
        ohlcv = self.exchange.fetch_ohlcv(
            symbol,
            timeframe,
            limit=min(int(limit), 1000),
        )
        frame = self.normalize_ohlcv(ohlcv)
        if len(frame) < 2:
            raise RuntimeError(f"Binance returned too few candles: {len(frame)}")
        return frame

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)
