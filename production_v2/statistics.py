from __future__ import annotations

from threading import Lock
from typing import Any


ENGINE_IDS = tuple(f"E{i}" for i in range(1, 10))


class StatisticsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._decisions = 0
        self._trades = 0
        self._last_decision = "NONE"
        self._last_prices: dict[str, float] = {}
        self._engine_counts = {engine_id: 0 for engine_id in ENGINE_IDS}

    def record(self, result: Any, price: float | None = None) -> None:
        with self._lock:
            self._decisions += 1
            self._last_decision = result.decision
            if result.decision in {"BUY", "SELL"} and result.gate_passed:
                self._trades += 1
            if price is not None:
                self._last_prices[result.symbol] = price
            for engine in result.engines:
                if engine.gate_passed:
                    self._engine_counts[engine.engine_id] = self._engine_counts.get(engine.engine_id, 0) + 1

    def update_price(self, symbol: str, price: float) -> None:
        with self._lock:
            self._last_prices[symbol] = price

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "system": "9-ENGINE",
                "version": "production-v2",
                "decision_authority": "E9",
                "legacy_runtime": False,
                "engines": list(ENGINE_IDS),
                "decisions": self._decisions,
                "actionable_trades": self._trades,
                "last_decision": self._last_decision,
                "prices": dict(self._last_prices),
                "engine_gate_passes": dict(self._engine_counts),
            }


store = StatisticsStore()


def build_statistics() -> dict[str, Any]:
    return store.snapshot()
