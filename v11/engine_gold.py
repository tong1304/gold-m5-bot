from __future__ import annotations

import os
import hashlib
import pandas as pd

from .data_quality import validate_frame
from .regime import classify_regime, _direction
from .risk import calculate as calculate_risk, min_rr_for_strategy
from .setup_state import SetupState, can_emit_entry
from .new_gold_engines import evaluate_new_gold_engines
from .decision_priority import signal_reason

ENGINE_VERSION = "12.5-NEW-GOLD-G1-G3-M5"
GOLD_ENGINES = ("G1", "G2", "G3")


def _stable_id(prefix, *parts):
    raw = "|".join("" if p is None else str(p).strip() for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _asof_context(frame, target_time, timeframe_minutes, max_bars=100):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out = frame.copy()
    if "timestamp" not in out.columns:
        return out.tail(max_bars)
    ts = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    target = pd.to_datetime(target_time, errors="coerce", utc=True)
    if pd.isna(target):
        return out.tail(max_bars)
    out = out.loc[ts <= target].copy()
    return out.tail(max_bars)
