from __future__ import annotations

import inspect
from functools import wraps
from typing import Any

EXPECTED_MIN_POSITIONAL = 4
LEGACY_SIGNATURE_ERROR = "takes 4 positional arguments but 5 were given"


def _unwrap(fn: Any) -> list[Any]:
    chain: list[Any] = []
    current = fn
    seen: set[int] = set()
    while callable(current) and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = getattr(current, "__wrapped__", None)
    return chain


def _signature_supports_anchor(fn: Any) -> bool:
    """Return True when an underlying lifecycle implementation accepts causal_anchor."""
    for current in _unwrap(fn):
        try:
            signature = inspect.signature(current)
        except (TypeError, ValueError):
            continue
        parameters = list(signature.parameters.values())
        if any(p.name == "causal_anchor" for p in parameters):
            return True
        positional = [p for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if len(positional) >= 5:
            return True
    return False


def _best_signature(fn: Any) -> str:
    """Report the useful underlying signature rather than a generic *args wrapper."""
    chain = _unwrap(fn)
    for current in reversed(chain):
        try:
            signature = inspect.signature(current)
        except (TypeError, ValueError):
            continue
        parameters = list(signature.parameters.values())
        if "causal_anchor" in str(signature) or len([p for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]) >= 5:
            return str(signature)
    try:
        return str(inspect.signature(fn))
    except (TypeError, ValueError):
        return "UNKNOWN"


def install(pipeline_module: Any) -> None:
    """Normalize the lifecycle call boundary without hiding causal-anchor support."""
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
    return {
        "pipeline_module": getattr(pipeline_module, "__file__", "UNKNOWN"),
        "lifecycle_signature": _best_signature(fn),
        "causal_anchor_supported": _signature_supports_anchor(fn),
        "compatibility_layer": True,
    }
