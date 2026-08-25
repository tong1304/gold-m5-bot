from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineResult:
    engine_id: str
    name: str
    gate_passed: bool
    score: float
    output: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionResult:
    symbol: str
    timeframe: str
    decision: str
    gate_passed: bool
    score: float
    engines: tuple[EngineResult, ...]
    risk: dict[str, Any]
    reason_codes: tuple[str, ...] = ()

    @property
    def legacy_runtime(self) -> bool:
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": "9-ENGINE",
            "version": "production-v2",
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "decision": self.decision,
            "gate_passed": self.gate_passed,
            "score": self.score,
            "decision_authority": "E9",
            "legacy_runtime": False,
            "engines": [
                {
                    "id": e.engine_id,
                    "name": e.name,
                    "gate_passed": e.gate_passed,
                    "score": e.score,
                    "output": e.output,
                    "reason_codes": e.reason_codes,
                }
                for e in self.engines
            ],
            "risk": self.risk,
            "reason_codes": list(self.reason_codes),
        }
