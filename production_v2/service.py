from __future__ import annotations

import os
import threading
import time

from .live_data import LiveMarketData
from .market_data import normalize_market_data
from .notifications.telegram import format_startup, send, send_decision
from .pipeline import ProductionPipeline


class LiveService:
    def __init__(self):
        self.pipeline = ProductionPipeline()
        self.data = LiveMarketData()
        self.interval = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60"))
        self._started = False
        self._last_candle: dict[str, str] = {}

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        send(format_startup(list(self.data.symbols().keys())))
        threading.Thread(target=self._loop, name="production-v2-scheduler", daemon=True).start()

    def _loop(self) -> None:
        while True:
            for alias in self.data.symbols():
                try:
                    payload = normalize_market_data(self.data.candles(alias))
                    candle = payload.get("candle_close_timestamp") or ""
                    if candle and self._last_candle.get(alias) == candle:
                        continue
                    self._last_candle[alias] = candle
                    result = self.pipeline.run(payload)
                    if result.decision != "NO_TRADE":
                        send_decision(result)
                except Exception as exc:
                    print(f"[PRODUCTION-V2] {alias}: {exc}")
            time.sleep(self.interval)


_service = None


def start_live_service() -> None:
    global _service
    if _service is None:
        _service = LiveService()
    _service.start()
