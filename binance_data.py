"""Binance public market-data adapter for the signal engine."""
import os
from datetime import datetime, timezone

import ccxt
import pandas as pd


class BinanceMarketData:
    # Binance Spot does not provide a native XAU/USDT market. PAXG/USDT is
    # used as the Binance-listed gold proxy while the application keeps the
    # user-facing symbol XAU/USDT.
    SYMBOL_ALIASES = {"XAU/USDT": "PAXG/USDT"}

    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret = os.getenv("BINANCE_API_SECRET", "").strip()
        self.exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": os.getenv("BINANCE_DEFAULT_TYPE", "spot")},
        })

    @classmethod
    def market_symbol(cls, symbol):
        return cls.SYMBOL_ALIASES.get(symbol, symbol)

    @staticmethod
    def normalize_ohlcv(ohlcv):
        frame = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if frame.empty:
            raise RuntimeError("Binance returned no OHLCV candles")
        frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["datetime", "open", "high", "low", "close"])
        return frame[["datetime", "open", "high", "low", "close", "volume"]].sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

    def _ensure_market(self, symbol):
        market_symbol = self.market_symbol(symbol)
        self.exchange.load_markets()
        if market_symbol not in self.exchange.markets:
            raise RuntimeError(f"Binance market is unavailable: {market_symbol} (requested {symbol})")
        return market_symbol

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        market_symbol = self._ensure_market(symbol)
        ohlcv = self.exchange.fetch_ohlcv(market_symbol, timeframe, limit=min(int(limit), 1000))
        frame = self.normalize_ohlcv(ohlcv)
        if len(frame) < 2:
            raise RuntimeError(f"Binance returned too few candles: {len(frame)}")
        return frame

    def fetch_price(self, symbol):
        market_symbol = self._ensure_market(symbol)
        ticker = self.exchange.fetch_ticker(market_symbol)
        price = ticker.get("last") or ticker.get("close")
        if price is None:
            raise RuntimeError(f"Binance ticker has no last price: {market_symbol}")
        return float(price), market_symbol

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)
