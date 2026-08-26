from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class OutcomeRecord:
    outcome: str
    realized_r: Optional[float]
    mfe_r: Optional[float]
    mae_r: Optional[float]
    bars_to_resolution: int


@dataclass(frozen=True)
class DecisionRecord:
    sample_id: str
    asset: str
    decision_timestamp: str
    candle_timestamp: str
    entry: Optional[float]
    direction: str
    thesis_quality: float
    evidence_signature: str
    outcome: Optional[str] = None
    outcome_timestamp: Optional[str] = None
    realized_r: Optional[float] = None
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None
    bars_to_resolution: Optional[int] = None


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def evidence_signature(evidence: dict[str, Any]) -> str:
    keys = (
        "direction", "market_state", "regime", "opportunity", "structure",
        "liquidity", "location", "setup", "setup_maturity", "confirmation",
        "economics",
    )
    normalized = {k: str(evidence.get(k, "UNRESOLVED")).upper() for k in keys}
    return hashlib.sha256(_stable_json(normalized).encode()).hexdigest()[:20]


def make_decision_record(asset: str, timestamp: str, entry: Optional[float], e9_output: dict[str, Any]) -> DecisionRecord:
    asset = str(asset).upper()
    direction = str(e9_output.get("decision", "NO_TRADE")).upper()
    sample_material = {
        "asset": asset,
        "timestamp": timestamp,
        "decision": direction,
        "architecture": e9_output.get("architecture", "PRODUCTION_V2"),
    }
    sample_id = hashlib.sha256(_stable_json(sample_material).encode()).hexdigest()[:24]
    dims = e9_output.get("professional_dimensions") or {}
    evidence = dict(dims)
    evidence.update({
        "direction": e9_output.get("direction", direction),
        "regime": e9_output.get("regime", "UNRESOLVED"),
        "setup": e9_output.get("setup", "UNRESOLVED"),
        "confirmation": e9_output.get("confirmation", "UNRESOLVED"),
        "economics": e9_output.get("economics", "UNRESOLVED"),
    })
    return DecisionRecord(
        sample_id=sample_id,
        asset=asset,
        decision_timestamp=timestamp,
        candle_timestamp=timestamp,
        entry=float(entry) if entry is not None else None,
        direction=direction,
        thesis_quality=float(e9_output.get("thesis_quality", 0.0)),
        evidence_signature=evidence_signature(evidence),
    )


def evaluate_outcome(direction: str, entry: float, stop: float, target: float, candles: list[dict[str, Any]], horizon: int) -> OutcomeRecord:
    direction = str(direction).upper()
    risk = abs(float(entry) - float(stop))
    if risk <= 0 or not candles or horizon <= 0:
        return OutcomeRecord("UNRESOLVED", None, None, None, 0)
    best = 0.0
    worst = 0.0
    for i, candle in enumerate(candles[:horizon], 1):
        high = float(candle["high"])
        low = float(candle["low"])
        if direction == "BUY":
            mfe = (high - entry) / risk
            mae = (low - entry) / risk
            hit_target = high >= target
            hit_stop = low <= stop
        elif direction == "SELL":
            mfe = (entry - low) / risk
            mae = (entry - high) / risk
            hit_target = low <= target
            hit_stop = high >= stop
        else:
            continue
        best = max(best, mfe)
        worst = min(worst, mae)
        if hit_target and hit_stop:
            return OutcomeRecord("AMBIGUOUS", None, round(best, 6), round(worst, 6), i)
        if hit_target:
            reward = abs(float(target) - float(entry)) / risk
            return OutcomeRecord("WIN", round(reward, 6), round(best, 6), round(worst, 6), i)
        if hit_stop:
            return OutcomeRecord("LOSS", -1.0, round(best, 6), round(worst, 6), i)
    return OutcomeRecord("TIMEOUT", 0.0, round(best, 6), round(worst, 6), min(len(candles), horizon))


def append_decision(path: str | Path, record: DecisionRecord) -> bool:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                try:
                    if json.loads(line).get("sample_id") == record.sample_id:
                        return False
                except json.JSONDecodeError:
                    continue
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    return True


def load_records(path: str | Path) -> list[DecisionRecord]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        records.append(DecisionRecord(**json.loads(line)))
    return records


def build_advisory(direction: str, stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "ADVISORY",
        "direction": str(direction).upper(),
        "sample_count": int(stats.get("sample_count", 0)),
        "win_rate": float(stats.get("win_rate", 0.0)),
        "expectancy_r": float(stats.get("expectancy_r", 0.0)),
        "actionable": bool(stats.get("actionable", False)),
        "decision_override": False,
    }
