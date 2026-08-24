from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "control_app.db"


def database_path() -> Path:
    return Path(os.getenv("CONTROL_APP_DB", str(DEFAULT_DB)))


def max_backtest_days() -> int:
    try:
        return max(1, min(int(os.getenv("CONTROL_APP_MAX_DAYS", "90")), 365))
    except ValueError:
        return 90
