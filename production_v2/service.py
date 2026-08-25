from __future__ import annotations

import os
import threading
import time

from .live_data import LiveMarketData
from .market_data import normalize_market_data
from .notifications.telegram import format_critical, format_startup, format_status, send, send_decision
from .pipeline import ProductionPipeline
from .statistics import store


class LiveService:
    def __init__(self):
        self.pipeline = ProductionPipeline()
        self.data = LiveMarketData()
        self.interval = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60"))
        self.status_interval_seconds = int(os.getenv("STATUS_INTERVAL_SECONDS", "900"))
        self.critical_interval_seconds = int(os.getenv("CRITICAL_INTERVAL_SECONDS", "900"))
        self._started = False
        self._last_candle: dict[str, str] = {}
        self._last_status_at = 0.0
        self._last_critical_at = 0.0

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        send(format_startup(list(self.data.symbols().keys())))
        self._last_status_at = time.monotonic()
        threading.Thread(target=self._loop, name="production-v2-scheduler", daemon=True).start()

    def _send_status(self, prices: dict[str, float]) -> None:
        status = {
            "symbols": {name: "เชื่อมต่อแล้ว" for name in self.data.symbols()},
            "prices": prices,
            "timeframe": "M5",
        }
        send(format_status(status))
        self._last_status_at = time.monotonic()

    def _send_critical(self, message: str, component: str) -> None:
        now = time.monotonic()
        if now - self._last_critical_at < self.critical_interval_seconds:
            return
        send(format_critical(message, component))
        self._last_critical_at = now

    def _loop(self) -> None:
        prices: dict[str, float] = {}
        while True:
            for alias in self.data.symbols():
                try:
                    payload = normalize_market_data(self.data.candles(alias))
                    if payload["bars"]:
                        prices[alias] = payload["bars"][-1]["close"]
                        store.update_price(alias, prices[alias])
                    candle = payload.get("candle_close_timestamp") or ""
                    if candle and self._last_candle.get(alias) == candle:
                        continue
                    self._last_candle[alias] = candle
                    result = self.pipeline.run(payload)
                    store.record(result, prices.get(alias))
                    if result.decision in {"BUY", "SELL"} and result.gate_passed:
                        send_decision(result)
                except Exception as exc:
                    self._send_critical(str(exc), alias)
            if time.monotonic() - self._last_status_at >= self.status_interval_seconds:
                try:
                    self._send_status(prices)
                except Exception as exc:
                    self._send_critical(str(exc), "Telegram")
            time.sleep(self.interval)


_service = None


def start_live_service() -> None:
    global _service
    if _service is None:
        _service = LiveService()
    _service.start()
