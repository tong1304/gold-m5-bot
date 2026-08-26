from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import json
from typing import Any

from .e9_calibration import CalibrationStats, aggregate_samples, calibration_key
from .e9_learning import DecisionRecord, OutcomeRecord, load_records


def attach_outcome(record: DecisionRecord, outcome: OutcomeRecord, outcome_timestamp: str) -> DecisionRecord:
    """Return an immutable decision record enriched only after the future outcome exists."""
    return replace(
        record,
        outcome=outcome.outcome,
        outcome_timestamp=outcome_timestamp,
        realized_r=outcome.realized_r,
        mfe_r=outcome.mfe_r,
        mae_r=outcome.mae_r,
        bars_to_resolution=outcome.bars_to_resolution,
    )


def update_record(path: str | Path, sample_id: str, outcome: OutcomeRecord, outcome_timestamp: str) -> bool:
    """Resolve exactly one journal record; never overwrite a different sample."""
    records = load_records(path)
    changed = False
    updated: list[DecisionRecord] = []
    for record in records:
        if record.sample_id == sample_id:
            if record.outcome is not None:
                updated.append(record)
            else:
                updated.append(attach_outcome(record, outcome, outcome_timestamp))
                changed = True
        else:
            updated.append(record)
    if not changed:
        return False
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in updated:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
    tmp.replace(target)
    return True


def calibration_table(path: str | Path, *, min_samples: int = 30) -> dict[tuple[str, str, str, str], CalibrationStats]:
    """Build isolated asset/regime/direction/evidence-signature statistics."""
    records = [asdict(r) for r in load_records(path) if r.outcome in {"WIN", "LOSS", "TIMEOUT"}]
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(calibration_key(record), []).append(record)
    return {key: aggregate_samples(group, min_samples=min_samples) for key, group in groups.items()}


def select_advisory(stats: dict[tuple[str, str, str, str], CalibrationStats], asset: str, regime: str, direction: str, signature: str) -> CalibrationStats | None:
    """Exact-match lookup only; no cross-asset or cross-regime borrowing."""
    return stats.get((str(asset).upper(), str(regime).upper(), str(direction).upper(), signature))
