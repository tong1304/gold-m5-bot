from __future__ import annotations

import os
import threading
import time as _time
from datetime import datetime, time, timedelta, timezone
from typing import Any

from lse import LSE

DEFAULT_SYMBOLS = {"GOLD": "XAU/USD", "BTC": "BTC/USD"}
CANDLE_INTERVAL = timedelta(minutes=5)


class LiveMarketData:
    def __init__(self):
        key = os.getenv("LSE_API_KEY")
        if not key:
            raise RuntimeError("LSE_API_KEY is required")
        self.client = LSE(api_key=key)
        # Keep provider requests serialized inside this worker. LSE can reject
        # overlapping requests for the same key even when the application
        # itself is otherwise healthy.
        self._request_lock = threading.Lock()
        self._last_request_at = 0.0
        self._min_request_gap = max(0.0, float(os.getenv("LSE_MIN_REQUEST_GAP_SECONDS", "0.25")))
        self._max_retries = max(0, int(os.getenv("LSE_MAX_429_RETRIES", "4")))
        self._retry_base_seconds = max(0.05, float(os.getenv("LSE_429_BACKOFF_SECONDS", "0.75")))

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

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    def market_is_open(self, alias: str, now: datetime | None = None) -> bool:
        alias = alias.upper()
        if alias == "BTC":
            return True
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if now.weekday() >= 5:
            return False
        start = self._utc_time(os.getenv("GOLD_DAILY_BREAK_START_UTC", "21:00"), time(21, 0))
        end = self._utc_time(os.getenv("GOLD_DAILY_BREAK_END_UTC", "22:00"), time(22, 0))
        current = now.time()
        if start <= current < end:
            return False
        if now.weekday() == 4 and current >= start:
            return False
        return True

    @staticmethod
    def _is_429(exc: Exception) -> bool:
        text = str(exc).lower()
        return "429" in text or "too many concurrent" in text or "rate limit" in text or "too many requests" in text

    def _fetch_candles(self, symbol: str, limit: int) -> Any:
        with self._request_lock:
            now = _time.monotonic()
            wait = self._min_request_gap - (now - self._last_request_at)
            if wait > 0:
                _time.sleep(wait)
            for attempt in range(self._max_retries + 1):
                try:
                    self._last_request_at = _time.monotonic()
                    return self.client.candles(symbol, "5m", limit=limit, order="desc")
                except Exception as exc:
                    if not self._is_429(exc) or attempt >= self._max_retries:
                        raise
                    delay = self._retry_base_seconds * (2 ** attempt)
                    _time.sleep(delay)
            raise RuntimeError("LSE candle request exhausted retries")

    def candles(self, alias: str, limit: int = 200) -> dict[str, Any]:
        symbol = self.symbols()[alias]
        if not self.market_is_open(alias):
            return {"symbol": symbol, "timeframe": "M5", "bars": [], "candle_close_timestamp": None, "market_open": False, "market_state": "MARKET_CLOSED", "closed_candle_only": True, "lookahead_allowed": False}

        response = self._fetch_candles(symbol, limit)
        rows = response.get("data", response) if isinstance(response, dict) else response
        now = datetime.now(timezone.utc)
        bars = []
        for row in reversed(rows or []):
            source_timestamp = row.get("timestamp")
            start = self._parse_timestamp(source_timestamp)
            if start is None:
                continue
            close_time = start + CANDLE_INTERVAL
            if close_time > now:
                continue
            timestamp = start.isoformat().replace("+00:00", "Z")
            bars.append({"open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"]), "timestamp": timestamp, "candle_id": timestamp, "is_closed": True, "candle_close_timestamp": close_time.isoformat().replace("+00:00", "Z")})

        latest = bars[-1] if bars else None
        return {"symbol": symbol, "timeframe": "M5", "bars": bars,
                "candle_close_timestamp": latest.get("timestamp") if latest else None,
                "data_cutoff_timestamp": latest.get("candle_close_timestamp") if latest else None,
                "data_cutoff_candle_id": latest.get("candle_id") if latest else None,
                "market_open": True, "market_state": "MARKET_OPEN", "closed_candle_only": True, "lookahead_allowed": False}
