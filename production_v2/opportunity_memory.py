from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


_LOCK = RLock()
_DEFAULT_PATH = "/tmp/production_v2_opportunity_lifecycle.json"
_TABLE = "production_v2_opportunity_lifecycle"


def _database_url() -> str:
    return str(os.getenv("OPPORTUNITY_MEMORY_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _path() -> Path:
    return Path(os.getenv("OPPORTUNITY_MEMORY_PATH", _DEFAULT_PATH)).expanduser()


def _postgres_enabled() -> bool:
    url = _database_url().lower()
    return url.startswith(("postgres://", "postgresql://"))


def _pg_connect():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL opportunity memory requires psycopg") from exc
    return psycopg.connect(_database_url(), autocommit=True)


def _ensure_postgres() -> None:
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                "symbol TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )


def _load_postgres() -> dict[str, dict[str, Any]]:
    _ensure_postgres()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT symbol, state_json FROM {_TABLE}")
            rows = cur.fetchall()
    result: dict[str, dict[str, Any]] = {}
    for symbol, state_json in rows:
        try:
            state = json.loads(state_json)
        except Exception:
            continue
        if isinstance(state, dict):
            result[str(symbol).upper()] = dict(state)
    return result


def load_all() -> dict[str, dict[str, Any]]:
    try:
        with _LOCK:
            if _postgres_enabled():
                return _load_postgres()
            path = _path()
            if not path.exists():
                return {}
            payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            str(symbol).upper(): dict(state)
            for symbol, state in payload.items()
            if isinstance(state, dict)
        }
    except Exception:
        return {}


def load(symbol: str) -> dict[str, Any]:
    return dict(load_all().get(str(symbol or "UNKNOWN").upper()) or {})


def save(symbol: str, state: dict[str, Any]) -> None:
    symbol = str(symbol or "UNKNOWN").upper()
    with _LOCK:
        if _postgres_enabled():
            _ensure_postgres()
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {_TABLE} (symbol, state_json, updated_at) VALUES (%s, %s, NOW()) "
                        "ON CONFLICT (symbol) DO UPDATE SET state_json=EXCLUDED.state_json, updated_at=NOW()",
                        (symbol, json.dumps(dict(state), ensure_ascii=False, sort_keys=True)),
                    )
            return
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = load_all()
        payload[symbol] = dict(state)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)


def remove(symbol: str) -> None:
    symbol = str(symbol or "UNKNOWN").upper()
    with _LOCK:
        if _postgres_enabled():
            _ensure_postgres()
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {_TABLE} WHERE symbol=%s", (symbol,))
            return
        path = _path()
        payload = load_all()
        if symbol not in payload:
            return
        del payload[symbol]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
