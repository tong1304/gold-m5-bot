from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    direction: str
    status: str
    reasons: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def pass_(cls, strategy, direction, evidence=None):
        return cls(strategy, direction, "PASS", (), evidence or {})

    @classmethod
    def fail(cls, strategy, direction, reasons, evidence=None):
        return cls(strategy, direction, "FAIL", tuple(reasons), evidence or {})

    @classmethod
    def not_applicable(cls, strategy, direction, reason, evidence=None):
        return cls(strategy, direction, "NOT_APPLICABLE", (reason,), evidence or {})

    def as_dict(self):
        return {"strategy": self.strategy, "direction": self.direction, "status": self.status, "reason": list(self.reasons), "evidence": self.evidence}
