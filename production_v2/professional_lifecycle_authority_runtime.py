from __future__ import annotations

from functools import wraps
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_PROFESSIONAL_LIFECYCLE_AUTHORITY_V1", False):
        return
    original = pipeline_module._directional_lifecycle_current

    @wraps(original)
    def directional(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        if not (isinstance(result, tuple) and result and isinstance(result[0], dict)):
            return result
        results = args[0] if args and isinstance(args[0], dict) else {}
        e6 = dict(getattr(results.get("E6"), "output", {}) or {})
        setup = str(e6.get("setup") or e6.get("setup_family") or "").strip()
        direction = _text(e6.get("direction"))
        if not e6.get("setup_exists") or not setup or direction not in {"BUY", "SELL"}:
            return result
        book = result[0]
        item = book.get(direction)
        if not isinstance(item, dict):
            return result
        item["candidate"] = True
        item["lifecycle_source"] = "E6_SETUP"
        item["direction"] = direction
        item["setup"] = setup
        item["thesis_status"] = e6.get("setup_state") or e6.get("thesis_status") or "VALIDATING"
        item["ready"] = False
        item["trade_authorized"] = False
        missing = e6.get("missing_proof") or ["E7_CONFIRMATION"]
        item["wait_for"] = missing if isinstance(missing, list) else [str(missing)]
        leader = result[1]
        if leader not in {"BUY", "SELL"}:
            leader = direction
        return book, leader, result[2]

    pipeline_module._directional_lifecycle_current = directional
    pipeline_module._PROFESSIONAL_LIFECYCLE_AUTHORITY_V1 = True
