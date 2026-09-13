from __future__ import annotations

import inspect
from functools import wraps
from typing import Any

EXPECTED_MIN_POSITIONAL = 4
LEGACY_SIGNATURE_ERROR = "takes 4 positional arguments but 5 were given"


def _signature_supports_anchor(fn: Any) -> bool:
    """Inspect through compatibility/decorator layers when possible."""
    current = fn
    seen: set[int] = set()
    while callable(current) and id(current) not in seen:
        seen.add(id(current))
        try:
            signature = inspect.signature(current)
            positional = [
                p for p in signature.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            if len(positional) >= 5:
                return True
        except (TypeError, ValueError):
            pass
        current = getattr(current, "__wrapped__", None)
    return False


def install(pipeline_module: Any) -> None:
    """Normalize the lifecycle call boundary without hiding the real signature."""
    if getattr(pipeline_module, "_RUNTIME_COMPATIBILITY_INSTALLED", False):
        return
    original = getattr(pipeline_module, "_directional_lifecycle_current", None)
    if not callable(original):
        return

    supports_anchor = _signature_supports_anchor(original)

    @wraps(original)
    def compatible(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except TypeError as exc:
            if len(args) >= 5 and LEGACY_SIGNATURE_ERROR in str(exc):
                return original(*args[:EXPECTED_MIN_POSITIONAL])
            raise

    try:
        compatible.__signature__ = inspect.signature(original)
    except (TypeError, ValueError):
        pass
    pipeline_module._directional_lifecycle_current = compatible
    pipeline_module._RUNTIME_LIFECYCLE_SUPPORTS_CAUSAL_ANCHOR = supports_anchor
    pipeline_module._RUNTIME_COMPATIBILITY_INSTALLED = True


def fingerprint(pipeline_module: Any) -> dict[str, Any]:
    fn = getattr(pipeline_module, "_directional_lifecycle_current", None)
    try:
        signature = str(inspect.signature(fn))
    except (TypeError, ValueError):
        signature = "UNKNOWN"
    return {
        "pipeline_module": getattr(pipeline_module, "__file__", "UNKNOWN"),
        "lifecycle_signature": signature,
        "causal_anchor_supported": bool(getattr(pipeline_module, "_RUNTIME_LIFECYCLE_SUPPORTS_CAUSAL_ANCHOR", False)),
        "compatibility_layer": True,
    }
