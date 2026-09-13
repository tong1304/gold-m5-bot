"""Runtime binding for opportunity repricing continuation.

This module is deliberately non-authoritative: it can move an immature
opportunity into REPRICE_WAIT, but it cannot authorize an order or weaken E8/E9.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from .opportunity_repricing_continuation import apply_opportunity_repricing


_INSTALLED = False


def _text(value: Any) -> str:
    return str(value or "").strip().upper()


def _first(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, dict):
            return value
    return {}


def install(pipeline_module: Any) -> bool:
    """Wrap ProductionPipeline.run when available."""
    global _INSTALLED
    if _INSTALLED:
        return True
    pipeline_cls = getattr(pipeline_module, "ProductionPipeline", None)
    if pipeline_cls is None or not hasattr(pipeline_cls, "run"):
        return False
    original = pipeline_cls.run
    if getattr(original, "_repricing_continuation", False):
        _INSTALLED = True
        return True

    @wraps(original)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if not isinstance(result, dict):
            return result
        risk = result.get("risk") if isinstance(result.get("risk"), dict) else {}
        lifecycle = _first(risk, "opportunity_lifecycle", "lifecycle")
        e4 = _first(result, "e4", "E4")
        e5 = _first(result, "e5", "E5")
        e8 = _first(result, "e8", "E8")
        if not lifecycle or not e8:
            return result
        updated = apply_opportunity_repricing(lifecycle, e4=e4, e5=e5, e8=e8)
        if updated == lifecycle or _text(updated.get("state")) != "REPRICE_WAIT":
            return result

        risk["opportunity_lifecycle"] = updated
        risk["opportunity_repricing"] = {
            "state": "REPRICE_WAIT",
            "opportunity_id": updated.get("opportunity_id"),
            "direction": updated.get("direction"),
            "wait_for": updated.get("wait_for"),
            "reprice_required": True,
            "trade_authorized": False,
            "source": "E8_EARLY_OPPORTUNITY_SCREEN",
        }
        result["risk"] = risk

        e9 = _first(result, "e9", "E9")
        if e9:
            e9 = dict(e9)
            e9["decision"] = "WAIT"
            e9["action"] = "REPRICE_WAIT"
            e9["trade_authorized"] = False
            reasons = list(e9.get("reasons") or e9.get("reason_codes") or [])
            if "OPPORTUNITY_REPRICE_REQUIRED" not in reasons:
                reasons.append("OPPORTUNITY_REPRICE_REQUIRED")
            e9["reasons"] = reasons
            result["e9"] = e9
            result["E9"] = e9
        result["opportunity_repricing"] = risk["opportunity_repricing"]
        return result

    wrapped._repricing_continuation = True
    pipeline_cls.run = wrapped
    _INSTALLED = True
    return True
