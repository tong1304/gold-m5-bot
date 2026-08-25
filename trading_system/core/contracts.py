from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionEvent:
    decision: str
    symbol: str
    timeframe: str
    reason_codes: tuple[str, ...]
    trace: dict[str, Any]
