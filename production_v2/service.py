from __future__ import annotations

import os
import threading
import time

from .live_data import LiveMarketData
from .market_data import normalize_market_data
from .notifications.telegram import format_critical, format_startup, format_status, send, send_decision
from .pipeline import ProductionPipeline, WAIT_MAX_BARS
from .statistics import store


class LiveService:
    def __init__(self):
        self.pipeline = ProductionPipeline()
        self.data = LiveMarketData()
        self.interval = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60"))
        self.status_interval_seconds = int(os.getenv("STATUS_INTERVAL_SECONDS", "900"))
        self._started = False
        self._last_candle: dict[str, str] = {}
        self._wait_bars: dict[str, int] = {}
        self._last_status_at = 0.0
        self._runtime_errors: dict[str, str] = {}
        self._last_prices: dict[str, float] = {}

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        send(format_startup(list(self.data.symbols().keys())))
        self._last_status_at = time.monotonic()
        threading.Thread(target=self._loop, name="production-v2-scheduler", daemon=True).start()

    def _send_status(self) -> None:
        symbols = self.data.symbols()
        status = {
            "symbols": {
                name: ("เชื่อมต่อแล้ว" if name not in self._runtime_errors else "มีปัญหา")
                for name in symbols
            },
            "prices": dict(self._last_prices),
            "timeframe": "M5",
            "runtime_errors": dict(self._runtime_errors),
            "architecture": "E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9",
        }
        send(format_status(status))
        self._last_status_at = time.monotonic()

    def _trace_result(self, alias: str, result) -> None:
        print(
            f"[PRODUCTION V2] {alias} PIPELINE decision={result.decision} "
            f"state={result.risk.get('engine_state')} wait_bars={result.risk.get('wait_bars')} "
            f"gate={result.gate_passed} score={result.score:.2f} "
            f"engines={len(result.engines)}",
            flush=True,
        )
        for engine in result.engines:
            print(
                f"[PRODUCTION V2] {alias} {engine.engine_id} "
                f"gate={engine.gate_passed} score={engine.score:.2f} "
                f"reasons={list(engine.reason_codes)}",
                flush=True,
            )

    def _loop(self) -> None:
        while True:
            for alias in self.data.symbols():
                try:
                    raw = self.data.candles(alias)
                    print(
                        f"[PRODUCTION V2] {alias} LSE M5 received "
                        f"bars={len(raw.get('bars') or [])} "
                        f"candle={raw.get('candle_close_timestamp')}",
                        flush=True,
                    )
                    payload = normalize_market_data(raw)
                    if payload["bars"]:
                        self._last_prices[alias] = payload["bars"][-1]["close"]
                        store.update_price(alias, self._last_prices[alias])
                    candle = payload.get("candle_close_timestamp") or ""
                    if not candle:
                        self._runtime_errors[alias] = "ไม่พบ candle timestamp"
                        continue
                    if self._last_candle.get(alias) == candle:
                        continue
                    self._last_candle[alias] = candle

                    wait_bars = self._wait_bars.get(alias, 0)
                    result = self.pipeline.run(payload, wait_bars=wait_bars)
                    self._runtime_errors.pop(alias, None)
                    store.record(result, self._last_prices.get(alias))
                    self._trace_result(alias, result)

                    if result.decision == "WAIT":
                        self._wait_bars[alias] = min(wait_bars + 1, WAIT_MAX_BARS)
                    else:
                        # PASS/FAIL starts a fresh decision cycle on the next candle.
                        self._wait_bars.pop(alias, None)

                    # Telegram is intentionally silent for WAIT and NO_TRADE.
                    # Only executable BUY/SELL decisions are sent.
                    if result.decision in {"BUY", "SELL"} and result.gate_passed:
                        send_decision(result)
                except Exception as exc:
                    self._runtime_errors[alias] = str(exc)
                    print(f"[PRODUCTION V2] {alias} ERROR {exc}", flush=True)

            if time.monotonic() - self._last_status_at >= self.status_interval_seconds:
                try:
                    _ = format_critical
                    self._send_status()
                except Exception as exc:
                    print(f"[PRODUCTION V2] Telegram status error: {exc}", flush=True)
            time.sleep(self.interval)


_service = None


def start_live_service() -> None:
    global _service
    if _service is None:
        _service = LiveService()
    _service.start()
