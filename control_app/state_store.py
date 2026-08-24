from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS backtest_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            symbol TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            error TEXT,
            result_json TEXT
        );
        """
    )
    return conn


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('telegram_enabled','1')"
            )

    def get_telegram_enabled(self) -> bool:
        with _connect(self.path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='telegram_enabled'").fetchone()
        return bool(row and row["value"] == "1")

    def set_telegram_enabled(self, enabled: bool) -> bool:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES('telegram_enabled',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("1" if enabled else "0",),
            )
        return bool(enabled)

    def create_run(self, run_id: str, symbol: str, start_time: str, end_time: str, created_at: str) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO backtest_runs(run_id,status,symbol,start_time,end_time,created_at) VALUES(?,?,?,?,?,?)",
                (run_id, "running", symbol, start_time, end_time, created_at),
            )

    def finish_run(self, run_id: str, result: dict[str, Any], completed_at: str) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "UPDATE backtest_runs SET status='completed',completed_at=?,result_json=?,error=NULL WHERE run_id=?",
                (completed_at, json.dumps(result, ensure_ascii=False), run_id),
            )

    def fail_run(self, run_id: str, error: str, completed_at: str) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "UPDATE backtest_runs SET status='failed',completed_at=?,error=? WHERE run_id=?",
                (completed_at, error, run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with _connect(self.path) as conn:
            row = conn.execute("SELECT * FROM backtest_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        if out.get("result_json"):
            out["result"] = json.loads(out.pop("result_json"))
        else:
            out.pop("result_json", None)
        return out

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT run_id,status,symbol,start_time,end_time,created_at,completed_at,error,result_json "
                "FROM backtest_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item.get("result_json"):
                payload = json.loads(item.pop("result_json"))
                item["summary"] = payload.get("statistics", payload.get("performance", {}))
            else:
                item.pop("result_json", None)
            result.append(item)
        return result
