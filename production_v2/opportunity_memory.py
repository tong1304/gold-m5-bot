from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


_LOCK = Lock()
_DEFAULT_PATH = "/tmp/production_v2_opportunity_lifecycle.json"


def _path() -> Path:
    return Path(os.getenv("OPPORTUNITY_MEMORY_PATH", _DEFAULT_PATH)).expanduser()


def load_all() -> dict[str, dict[str, Any]]:
    path = _path()
    try:
        with _LOCK:
            if not path.exists():
                return {}
            payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            str(symbol): dict(state)
            for symbol, state in payload.items()
            if isinstance(state, dict)
        }
    except Exception:
        return {}


def load(symbol: str) -> dict[str, Any]:
    return dict(load_all().get(str(symbol or "UNKNOWN").upper()) or {})


def save(symbol: str, state: dict[str, Any]) -> None:
    path = _path()
    symbol = str(symbol or "UNKNOWN").upper()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        payload = load_all()
        payload[symbol] = dict(state)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)


def remove(symbol: str) -> None:
    path = _path()
    symbol = str(symbol or "UNKNOWN").upper()
    with _LOCK:
        payload = load_all()
        if symbol not in payload:
            return
        del payload[symbol]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
