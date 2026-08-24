from __future__ import annotations

from typing import Any

from ..state_store import StateStore
from .models import BacktestResult


class BacktestRepository:
    def __init__(self, store: StateStore):
        self.store = store

    def save_backtest(self, result: BacktestResult, completed_at: str) -> str:
        self.store.finish_run(result.run_id, result.to_dict(), completed_at)
        return result.run_id

    def get_backtest(self, run_id: str) -> dict[str, Any] | None:
        return self.store.get_run(run_id)

    def list_backtests(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_runs(limit)
