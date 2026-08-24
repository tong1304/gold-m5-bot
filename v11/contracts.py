from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    direction: str
    status: str
    reasons: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    quality: float = 0.0
    freshness_bars: int = 0
    setup_timestamp: Any = None

    @classmethod
    def pass_(cls, strategy, direction, evidence=None, quality=0.0, freshness_bars=0, setup_timestamp=None):
        return cls(strategy, direction, "PASS", (), evidence or {}, float(quality or 0.0), int(freshness_bars or 0), setup_timestamp)

    @classmethod
    def fail(cls, strategy, direction, reasons, evidence=None):
        return cls(strategy, direction, "FAIL", tuple(reasons), evidence or {})

    @classmethod
    def not_applicable(cls, strategy, direction, reason, evidence=None):
        return cls(strategy, direction, "NOT_APPLICABLE", (reason,), evidence or {})

    def as_dict(self):
        return {"strategy": self.strategy, "direction": self.direction, "status": self.status,
                "reason": list(self.reasons), "evidence": self.evidence,
                "quality": self.quality, "freshness_bars": self.freshness_bars,
                "setup_timestamp": str(self.setup_timestamp) if self.setup_timestamp is not None else None}
