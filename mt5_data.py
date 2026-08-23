"""Render-only market-data adapter backed by London Strategic Edge (LSE).

REST supplies historical/closed candles. The official LSE WebSocket supplies
live ticks. The scanner uses the live tick stream to build the currently
forming M5 candle, while H1/M15 confirmation remains based on closed candles.
No MetaTrader, MT5 bridge, PC, VPS, Binance, or Twelve Data connection is used.
"""
import os
import time
import threading
from datetime import datetime, timezone

import pandas as pd
import requests

try:
    from lse import LSE
except ImportError:
    LSE = None

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


class _LiveTickCache:
    """One persistent LSE WebSocket connection for the two active symbols."""
    def __init__(self, api_key):
        self.api_key = api_key
        self._ticks = {}
        self._lock = threading.RLock()
        self._started = False
        self._thread = None
        self._client = None

    def start(self, symbols):
        if self._started or LSE is None or not self.api_key:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, args=(list(symbols),), name="lse-live-websocket", daemon=True)
        self._thread.start()

    def _run(self, symbols):
        while True:
            try:
                client = LSE(api_key=self.api_key)
                self._client = client

                def on_tick(tick):
                    symbol = str(getattr(tick, "symbol", "")).upper()
                    price = getattr(tick, "price", None)
                    if not symbol or price is None:
                        return
                    try:
                        price = float(price)
                        if not price == price or price <= 0:
                            return
                    except (TypeError, ValueError):
                        return
                    ts = getattr(tick, "datetime", None)
                    if ts is None:
                        ts = getattr(tick, "timestamp", None)
                    with self._lock:
                        self._ticks[symbol] = {
                            "price": price,
                            "bid": getattr(tick, "bid", None),
                            "ask": getattr(tick, "ask", None),
                            "volume": getattr(tick, "volume", 0.0),
                            "timestamp": ts,
                        }

                client.on("tick", on_tick)
                client.connect(symbols=symbols)
            except Exception as exc:
                print(f"LSE WebSocket reconnect: {type(exc).__name__}: {exc}", flush=True)
                time.sleep(5)

    def latest(self, symbol):
        with self._lock:
            value = self._ticks.get(str(symbol).upper())
            return dict(value) if value else None


class LSEMarketData:
    """Cloud market-data provider backed exclusively by London Strategic Edge."""
    def __init__(self):
        self.api_key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("LSE_API_KEY is not configured")
        self.base_url = BASE_URL
        self.last_provider = "lse"
        self._m5_cache = {}
        self._cache_ttl_seconds = max(5, int(os.getenv("LSE_M5_CACHE_SECONDS", "15")))
        self._live = _LiveTickCache(self.api_key)
        self._live.start(SYMBOLS.values())

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

    @staticmethod
    def _tick_datetime(value):
        try:
            if isinstance(value, datetime):
                dt = value
            elif isinstance(value, (int, float)):
                dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            else:
                text = str(value).replace("Z", "+00:00")
                dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return datetime.now(timezone.utc)

    def _append_live_m5(self, frame, provider_symbol):
        """Build/update the currently forming M5 bar from the live WebSocket tick."""
        tick = self._live.latest(provider_symbol)
        if not tick:
            return frame
        now = self._tick_datetime(tick.get("timestamp"))
        start = pd.Timestamp(now).floor("5min")
        price = float(tick["price"])
        current = frame[frame["datetime"] == start]
        if not current.empty:
            row = current.iloc[-1].copy()
            row["high"] = max(float(row["high"]), price)
            row["low"] = min(float(row["low"]), price)
            row["close"] = price
            row["volume"] = max(float(row.get("volume", 0.0)), float(tick.get("volume") or 0.0))
            frame = frame[frame["datetime"] != start].copy()
            return pd.concat([frame, pd.DataFrame([row])], ignore_index=True).sort_values("datetime").reset_index(drop=True)

        if frame.empty:
            return frame
        last_close = float(frame.iloc[-1]["close"])
        live_row = {
            "datetime": start,
            "open": last_close,
            "high": price,
            "low": price,
            "close": price,
            "volume": float(tick.get("volume") or 0.0),
        }
        return pd.concat([frame, pd.DataFrame([live_row])], ignore_index=True).sort_values("datetime").reset_index(drop=True)

    def _fetch_raw_m5(self, provider_symbol):
        now = time.monotonic()
        cached = self._m5_cache.get(provider_symbol)
        if cached and now - cached["time"] < self._cache_ttl_seconds:
            frame = cached["frame"].copy()
        else:
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
            print(f"LSE M5 REST fetched: {provider_symbol} rows={len(frame)}", flush=True)
        live = self._append_live_m5(frame, provider_symbol)
        if len(live) != len(frame) or (not live.empty and not frame.empty and float(live.iloc[-1]["close"]) != float(frame.iloc[-1]["close"])):
            print(f"LSE LIVE M5 updated: {provider_symbol} close={float(live.iloc[-1]['close'])}", flush=True)
        return live

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
            "timeframe": {"1m":"1m", "5m":"5m", "15m":"15m", "30m":"30m", "45m":"45m", "1h":"1h", "2h":"2h", "4h":"4h", "8h":"8h", "1d":"1d"}.get(tf, tf),
            "limit": min(max(int(limit), 2), 5000),
            "order": "desc",
        })
        return self._normalize_candles(payload).tail(int(limit)).reset_index(drop=True)

    def fetch_price(self, symbol):
        provider_symbol = self.market_symbol(symbol)
        tick = self._live.latest(provider_symbol)
        if tick:
            return float(tick["price"]), provider_symbol
        frame = self._fetch_raw_m5(provider_symbol)
        if frame.empty:
            raise RuntimeError(f"LSE returned no price data: {provider_symbol}")
        return float(frame.iloc[-1]["close"]), provider_symbol

    @staticmethod
    def remove_incomplete_last_candle(frame, now=None, timeframe_minutes=5):
        if frame.empty:
            return frame
        # M5 is intentionally allowed to retain the live forming bar. H1/M15
        # continue to use closed candles for confirmation.
        if int(timeframe_minutes) == 5 and os.getenv("LSE_USE_LIVE_M5", "true").strip().lower() == "true":
            return frame.reset_index(drop=True)
        now = now or datetime.now(timezone.utc)
        cutoff = pd.Timestamp(now).floor(f"{int(timeframe_minutes)}min")
        return frame[frame["datetime"] < cutoff].reset_index(drop=True)


TwelveDataMarketData = LSEMarketData
XMMarketData = LSEMarketData
