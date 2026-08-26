from __future__ import annotations

from datetime import datetime, timezone
import os
import threading
import time
from zoneinfo import ZoneInfo

from .live_data import LiveMarketData
from .market_data import normalize_market_data
from .notifications.no_trade import send_no_trade
from .notifications.telegram import format_critical, format_startup, format_status, send, send_decision
from .pipeline import ProductionPipeline
from .statistics import store

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class LiveService:
    def __init__(self):
        self.pipeline = ProductionPipeline()
        self.data = LiveMarketData()
        self.interval = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60"))
        self.status_interval_seconds = int(os.getenv("STATUS_INTERVAL_SECONDS", "900"))
        self.max_candle_age_seconds = int(os.getenv("MAX_CANDLE_AGE_SECONDS", "600"))
        self._started = False
        self._last_candle: dict[str, str] = {}
        self._last_status_slot: str | None = None
        self._runtime_errors: dict[str, str] = {}
        self._last_prices: dict[str, float] = {}
        self._latest_results: dict[str, object] = {}
        self._last_no_trade_slot: str | None = None

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        send(format_startup(list(self.data.symbols().keys())))
        threading.Thread(target=self._loop, name="production-v2-scheduler", daemon=True).start()

    def _send_status(self, now: datetime) -> None:
        send(format_status({"prices": dict(self._last_prices), "timeframe": "M5", "timestamp": now, "architecture": "E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9"}))
        self._last_status_slot = now.strftime("%Y%m%d%H%M")

    def _send_aligned_status(self) -> None:
        now = datetime.now(BANGKOK_TZ)
        if now.minute % 15 != 0: return
        slot = now.strftime("%Y%m%d%H%M")
        if slot == self._last_status_slot: return
        try: self._send_status(now)
        except Exception as exc: print(f"[PRODUCTION V2] Telegram status error: {exc}", flush=True)

    def _send_aligned_no_trade(self) -> None:
        now = datetime.now(BANGKOK_TZ)
        if now.minute % 10 != 0: return
        slot = now.strftime("%Y%m%d%H%M")
        if slot == self._last_no_trade_slot: return
        symbols = self.data.symbols()
        if set(self._latest_results) != set(symbols): return
        if any(getattr(r, "decision", None) in {"BUY", "SELL"} and bool(getattr(r, "gate_passed", False)) for r in self._latest_results.values()):
            self._last_no_trade_slot = slot
            return
        try:
            send_no_trade(dict(self._latest_results), now)
            self._last_no_trade_slot = slot
        except Exception as exc: print(f"[PRODUCTION V2] Telegram no-trade error: {exc}", flush=True)

    @staticmethod
    def _candle_age_seconds(candle: str) -> float | None:
        try:
            timestamp = datetime.fromisoformat(candle.replace("Z", "+00:00"))
            if timestamp.tzinfo is None: timestamp = timestamp.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
        except (TypeError, ValueError): return None

    def _trace_result(self, alias: str, result) -> None:
        state = result.risk.get("engine_state"); blocked_by = result.risk.get("blocked_by")
        print(f"[PRODUCTION V2] {alias} PIPELINE decision={result.decision} state={state} blocked_by={blocked_by} wait_bars=0 gate={result.gate_passed} engines={len(result.engines)}", flush=True)
        for engine in result.engines:
            handoff = (engine.output.get("professional_reasoning") or {}).get("handoff")
            print(f"[PRODUCTION V2] {alias} {engine.engine_id} gate={engine.gate_passed} score={engine.score:.1f} handoff={handoff} reasons={list(engine.reason_codes)}", flush=True)

    def _loop(self) -> None:
        while True:
            for alias in self.data.symbols():
                try:
                    raw = self.data.candles(alias); payload = normalize_market_data(raw)
                    if payload["bars"]:
                        self._last_prices[alias] = payload["bars"][-1]["close"]; store.update_price(alias, self._last_prices[alias])
                    candle = payload.get("candle_close_timestamp") or ""
                    if not candle:
                        self._runtime_errors[alias] = "ไม่พบ candle timestamp"; continue
                    age = self._candle_age_seconds(candle)
                    if age is not None and age > self.max_candle_age_seconds:
                        print(f"[PRODUCTION V2] {alias} STALE_CANDLE candle={candle} age_seconds={int(age)} action=SKIP_EVALUATION", flush=True); self._runtime_errors[alias] = f"stale candle: {candle}"; continue
                    if self._last_candle.get(alias) == candle:
                        print(f"[PRODUCTION V2] {alias} DUPLICATE_CANDLE candle={candle} action=SKIP_EVALUATION", flush=True); continue
                    self._last_candle[alias] = candle
                    print(f"[PRODUCTION V2] {alias} LSE M5 new closed candle bars={len(raw.get('bars') or [])} candle={candle}", flush=True)
                    result = self.pipeline.run(payload)
                    self._runtime_errors.pop(alias, None); self._latest_results[alias] = result; store.record(result, self._last_prices.get(alias)); self._trace_result(alias, result)
                    if result.decision in {"BUY", "SELL"} and result.gate_passed: send_decision(result)
                except Exception as exc:
                    self._runtime_errors[alias] = str(exc); print(f"[PRODUCTION V2] {alias} ERROR {exc}", flush=True)
            self._send_aligned_no_trade(); self._send_aligned_status(); time.sleep(self.interval)


_service = None

def start_live_service() -> None:
    global _service
    if _service is None: _service = LiveService()
    _service.start()
