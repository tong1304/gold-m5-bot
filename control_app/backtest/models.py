from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BacktestResult:
    run_id: str
    symbol: str
    start_time: str
    end_time: str
    engine_version: str
    statistics: dict[str, Any]
    trades: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "symbol": self.symbol,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "engine_version": self.engine_version,
            "statistics": self.statistics,
            "trades": self.trades,
            "metadata": self.metadata,
        }
