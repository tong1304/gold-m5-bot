from __future__ import annotations
from threading import Lock
from typing import Any

ENGINE_IDS = tuple(f"E{i}" for i in range(1, 10))


class StatisticsStore:
    def __init__(self) -> None:
        self._lock = Lock(); self._decisions = 0; self._authorizations = 0; self._executions = 0; self._last_decision = "NONE"; self._last_execution_state = "NOT_REQUESTED"; self._last_prices: dict[str,float] = {}; self._engine_counts = {engine_id:0 for engine_id in ENGINE_IDS}

    def record(self, result: Any, price: float | None = None) -> None:
        with self._lock:
            self._decisions += 1; self._last_decision = str(result.decision)
            if str(result.decision).upper() in {"BUY","SELL"} and bool(result.gate_passed): self._authorizations += 1
            execution = dict(getattr(result,"execution_state",{}) or {}); state = str(execution.get("state") or "NOT_REQUESTED").upper(); self._last_execution_state = state
            if state == "POSITION_OPEN": self._executions += 1
            if price is not None: self._last_prices[result.symbol] = price
            for engine in result.engines:
                if engine.gate_passed: self._engine_counts[engine.engine_id] = self._engine_counts.get(engine.engine_id,0)+1

    def record_execution(self, symbol: str, execution_state: str) -> None:
        with self._lock:
            self._last_execution_state = str(execution_state).upper()
            if self._last_execution_state == "POSITION_OPEN": self._executions += 1

    def update_price(self, symbol: str, price: float) -> None:
        with self._lock: self._last_prices[symbol] = price

    def snapshot(self) -> dict[str,Any]:
        with self._lock:
            return {"system":"9-ENGINE","version":"production-v2","decision_authority":"E9","legacy_runtime":False,"engines":list(ENGINE_IDS),"decisions":self._decisions,"e9_authorizations":self._authorizations,"executed_positions":self._executions,"actionable_trades":self._executions,"last_decision":self._last_decision,"last_execution_state":self._last_execution_state,"prices":dict(self._last_prices),"engine_gate_passes":dict(self._engine_counts)}

store=StatisticsStore()

def build_statistics()->dict[str,Any]: return store.snapshot()
