from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineResult:
    engine_id: str
    name: str
    gate_passed: bool | None
    score: float
    output: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionResult:
    """Stable public result with compatibility for the production-v2 pipeline call shape.

    Canonical shape is the explicit symbol/timeframe/gate/risk contract. The
    legacy pipeline constructor also supplies ``state``/``blocked_by``/``wait_bars``
    and an engine mapping; these are normalized here so the API never exposes a
    dict where callers expect EngineResult objects.
    """
    symbol: str = "UNKNOWN"
    timeframe: str = "M5"
    decision: str = "NO_TRADE"
    gate_passed: bool = False
    score: float = 0.0
    engines: tuple[EngineResult, ...] | dict[str, EngineResult] = ()
    risk: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    state: str = "ANALYSIS_COMPLETE_NO_TRADE"
    blocked_by: Any = None
    wait_bars: int = 0

    def __post_init__(self) -> None:
        engines = self.engines
        if isinstance(engines, dict):
            normalized = tuple(value for value in engines.values() if isinstance(value, EngineResult))
            object.__setattr__(self, "engines", normalized)
            engines_by_id = {value.engine_id: value for value in normalized}
        else:
            normalized = tuple(engines or ())
            object.__setattr__(self, "engines", normalized)
            engines_by_id = {value.engine_id: value for value in normalized}

        e9 = engines_by_id.get("E9")
        e9_output = e9.output if e9 else {}
        e8 = engines_by_id.get("E8")
        e8_output = e8.output if e8 else {}

        if self.symbol == "UNKNOWN":
            symbol = e9_output.get("symbol") or e8_output.get("symbol")
            if symbol:
                object.__setattr__(self, "symbol", str(symbol))
        if self.timeframe == "M5":
            timeframe = e9_output.get("timeframe") or e8_output.get("timeframe")
            if timeframe:
                object.__setattr__(self, "timeframe", str(timeframe))
        if self.score == 0.0 and e9 is not None:
            object.__setattr__(self, "score", float(e9.score))
        if not self.gate_passed and e9 is not None:
            object.__setattr__(self, "gate_passed", bool(e9.gate_passed))
        if not self.risk and isinstance(e8_output, dict):
            object.__setattr__(self, "risk", dict(e8_output))
        if self.reason_codes == () and e9 is not None:
            object.__setattr__(self, "reason_codes", tuple(e9.reason_codes))
        if self.state == "ANALYSIS_COMPLETE_NO_TRADE" and self.decision in {"BUY", "SELL", "TRADE"} and self.gate_passed:
            object.__setattr__(self, "state", "SIGNAL_READY")

    @property
    def legacy_runtime(self) -> bool:
        return False

    @property
    def trade_plan(self) -> dict[str, Any]:
        return dict(self.risk.get("trade_plan") or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": "9-ENGINE",
            "version": "production-v2",
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "decision": self.decision,
            "state": self.state,
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
                    "reason_codes": list(e.reason_codes),
                }
                for e in self.engines
            ],
            "risk": self.risk,
            "trade_plan": self.trade_plan,
            "reason_codes": list(self.reason_codes),
            "blocked_by": self.blocked_by,
            "wait_bars": self.wait_bars,
        }
