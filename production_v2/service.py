from __future__ import annotations

from datetime import datetime, timezone
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
        # A professional decision engine must never make a fresh decision from
        # stale market data. Ten minutes covers normal polling/network jitter
        # while still protecting the M5 runtime from an old candle.
        self.max_candle_age_seconds = int(os.getenv("MAX_CANDLE_AGE_SECONDS", "600"))
        self._started = False
        self._last_candle: dict[str, str] = {}
        self._wait_state: dict[str, dict] = {}
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

    @staticmethod
    def _candle_age_seconds(candle: str) -> float | None:
        try:
            timestamp = datetime.fromisoformat(candle.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
        except (TypeError, ValueError):
            return None

    def _trace_result(self, alias: str, result) -> None:
        state = result.risk.get("engine_state")
        blocked_by = result.risk.get("blocked_by")
        # Score is retained only as an internal diagnostic field for backwards
        # compatibility. It is deliberately excluded from the decision trace:
        # PASS/WAIT/FAIL is determined by gates and thesis validity, not points.
        print(
            f"[PRODUCTION V2] {alias} PIPELINE decision={result.decision} "
            f"state={state} blocked_by={blocked_by} "
            f"wait_bars={result.risk.get('wait_bars')} "
            f"gate={result.gate_passed} engines={len(result.engines)}",
            flush=True,
        )
        for engine in result.engines:
            print(
                f"[PRODUCTION V2] {alias} {engine.engine_id} "
                f"gate={engine.gate_passed} reasons={list(engine.reason_codes)}",
                flush=True,
            )

    def _loop(self) -> None:
        while True:
            for alias in self.data.symbols():
                try:
                    raw = self.data.candles(alias)
                    payload = normalize_market_data(raw)
                    if payload["bars"]:
                        self._last_prices[alias] = payload["bars"][-1]["close"]
                        store.update_price(alias, self._last_prices[alias])

                    candle = payload.get("candle_close_timestamp") or ""
                    if not candle:
                        self._runtime_errors[alias] = "ไม่พบ candle timestamp"
                        continue

                    age = self._candle_age_seconds(candle)
                    if age is not None and age > self.max_candle_age_seconds:
                        # Do not mark stale data as the last processed candle.
                        # Once the provider catches up, the real closed candle
                        # must still enter the decision pipeline.
                        print(
                            f"[PRODUCTION V2] {alias} STALE_CANDLE "
                            f"candle={candle} age_seconds={int(age)} "
                            f"max_age_seconds={self.max_candle_age_seconds} "
                            f"action=SKIP_EVALUATION",
                            flush=True,
                        )
                        self._runtime_errors[alias] = f"stale candle: {candle}"
                        continue

                    # LSE may return the same closed candle on multiple polling
                    # cycles. A duplicate candle is data refresh only: never
                    # rerun E1..E9, never advance WAIT, and never overwrite the
                    # current professional WAIT state.
                    if self._last_candle.get(alias) == candle:
                        print(
                            f"[PRODUCTION V2] {alias} DUPLICATE_CANDLE "
                            f"candle={candle} action=SKIP_EVALUATION",
                            flush=True,
                        )
                        continue

                    self._last_candle[alias] = candle
                    print(
                        f"[PRODUCTION V2] {alias} LSE M5 new closed candle "
                        f"bars={len(raw.get('bars') or [])} candle={candle}",
                        flush=True,
                    )

                    wait_state = self._wait_state.get(alias)
                    wait_bars = int(wait_state.get("wait_bars", 0)) if wait_state else 0
                    if wait_state:
                        print(
                            f"[PRODUCTION V2] {alias} WAIT_RESUME "
                            f"waiting_engine={wait_state.get('waiting_engine')} "
                            f"wait_bars={wait_bars} "
                            f"policy=REUSE_UPSTREAM_UNLESS_STRUCTURE_CHANGED",
                            flush=True,
                        )

                    result = self.pipeline.run(
                        payload,
                        wait_bars=wait_bars,
                        resume_state=wait_state,
                    )
                    self._runtime_errors.pop(alias, None)
                    store.record(result, self._last_prices.get(alias))
                    self._trace_result(alias, result)

                    if result.decision == "WAIT":
                        blocked_by = result.risk.get("blocked_by")
                        self._wait_state[alias] = {
                            "waiting_engine": blocked_by,
                            "engines": result.engines,
                            # Informational counter only. It NEVER expires WAIT.
                            "wait_bars": wait_bars + 1,
                        }
                    else:
                        # PASS/FAIL starts a fresh decision cycle. FAIL is never
                        # kept alive as a WAIT state.
                        self._wait_state.pop(alias, None)

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
