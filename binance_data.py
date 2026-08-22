"""Market-data adapter with Binance primary and a restricted-region fallback."""
import os
from datetime import datetime, timezone

import ccxt
import pandas as pd


class BinanceMarketData:
    # XAU/USDT is represented by PAXG because Binance Spot has no native XAU/USDT.
    SYMBOL_ALIASES = {"XAU/USDT": "PAXG/USDT"}
    # If Binance returns HTTP 451 from the hosting region, use Kraken public
    # market data so the scanner can continue receiving OHLCV/ticker data.
    # This is DATA ONLY; the application still never places live orders.
    FALLBACK_ALIASES = {
        "BTC/USDT": "BTC/USDT",
        "ETH/USDT": "ETH/USDT",
        "SOL/USDT": "SOL/USDT",
        "XAU/USDT": "PAXG/USD",
    }

    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret = os.getenv("BINANCE_API_SECRET", "").strip()
        self.exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": os.getenv("BINANCE_DEFAULT_TYPE", "spot")},
        })
        self.fallback_exchange = ccxt.kraken({"enableRateLimit": True})
        self.last_provider = "binance"

    @classmethod
    def market_symbol(cls, symbol):
        return cls.SYMBOL_ALIASES.get(symbol, symbol)

    @classmethod
    def fallback_symbol(cls, symbol):
        return cls.FALLBACK_ALIASES.get(symbol, symbol)

    @staticmethod
    def normalize_ohlcv(ohlcv):
        frame = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if frame.empty:
            raise RuntimeError("market returned no OHLCV candles")
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

    def _ensure_fallback_market(self, symbol):
        market_symbol = self.fallback_symbol(symbol)
        self.fallback_exchange.load_markets()
        if market_symbol not in self.fallback_exchange.markets:
            raise RuntimeError(f"Fallback market is unavailable: {market_symbol} (requested {symbol})")
        return market_symbol

    def _use_fallback(self, exc):
        text = str(exc)
        return "451" in text or "restricted location" in text.lower() or isinstance(exc, ccxt.ExchangeNotAvailable)

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        try:
            market_symbol = self._ensure_market(symbol)
            ohlcv = self.exchange.fetch_ohlcv(market_symbol, timeframe, limit=min(int(limit), 1000))
            self.last_provider = "binance"
            frame = self.normalize_ohlcv(ohlcv)
        except Exception as exc:
            if not self._use_fallback(exc):
                raise
            market_symbol = self._ensure_fallback_market(symbol)
            ohlcv = self.fallback_exchange.fetch_ohlcv(market_symbol, timeframe, limit=min(int(limit), 1000))
            self.last_provider = "kraken_fallback"
            frame = self.normalize_ohlcv(ohlcv)
        if len(frame) < 2:
            raise RuntimeError(f"market returned too few candles: {len(frame)}")
        return frame

    def fetch_price(self, symbol):
        try:
            market_symbol = self._ensure_market(symbol)
            ticker = self.exchange.fetch_ticker(market_symbol)
            self.last_provider = "binance"
        except Exception as exc:
            if not self._use_fallback(exc):
                raise
            market_symbol = self._ensure_fallback_market(symbol)
            ticker = self.fallback_exchange.fetch_ticker(market_symbol)
            self.last_provider = "kraken_fallback"
        price = ticker.get("last") or ticker.get("close")
        if price is None:
            raise RuntimeError(f"ticker has no last price: {market_symbol}")
        return float(price), market_symbol

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)
