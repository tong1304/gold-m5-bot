from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any


@dataclass(frozen=True)
class CalibrationStats:
    sample_count: int
    win_rate: float
    expectancy_r: float
    average_mfe_r: float
    average_mae_r: float
    timeout_rate: float
    win_rate_low: float
    win_rate_high: float
    actionable: bool


def _wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    spread = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n) / d
    return max(0.0, centre - spread), min(1.0, centre + spread)


def aggregate_samples(samples: list[dict[str, Any]], min_samples: int = 30, asset: str | None = None, signature: str | None = None) -> CalibrationStats:
    selected = []
    for sample in samples:
        if asset and str(sample.get("asset", "")).upper() != str(asset).upper():
            continue
        if signature and sample.get("evidence_signature") != signature:
            continue
        selected.append(sample)
    count = len(selected)
    wins = sum(str(s.get("outcome", "")).upper() == "WIN" for s in selected)
    rs = [float(s["realized_r"]) for s in selected if s.get("realized_r") is not None and str(s.get("outcome", "")).upper() in {"WIN", "LOSS", "TIMEOUT"}]
    mfes = [float(s["mfe_r"]) for s in selected if s.get("mfe_r") is not None]
    maes = [float(s["mae_r"]) for s in selected if s.get("mae_r") is not None]
    timeouts = sum(str(s.get("outcome", "")).upper() == "TIMEOUT" for s in selected)
    low, high = _wilson(wins, count)
    return CalibrationStats(
        sample_count=count,
        win_rate=wins / count if count else 0.0,
        expectancy_r=sum(rs) / len(rs) if rs else 0.0,
        average_mfe_r=sum(mfes) / len(mfes) if mfes else 0.0,
        average_mae_r=sum(maes) / len(maes) if maes else 0.0,
        timeout_rate=timeouts / count if count else 0.0,
        win_rate_low=low,
        win_rate_high=high,
        actionable=count >= min_samples,
    )


def calibration_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("asset", "")).upper(),
        str(record.get("regime", "UNRESOLVED")).upper(),
        str(record.get("direction", "NO_TRADE")).upper(),
        str(record.get("evidence_signature", "UNRESOLVED")),
    )
