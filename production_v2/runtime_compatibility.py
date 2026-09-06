from __future__ import annotations

import inspect
from typing import Any

EXPECTED_MIN_POSITIONAL = 4


def install(pipeline_module: Any) -> None:
    """Prevent a stale 4-argument lifecycle helper from killing the live loop.

    Current code supports causal_anchor. Older deployed workers may still expose
    the 4-argument helper; normalize the boundary here so the caller remains
    forward-compatible while preserving causal anchors when supported.
    """
    if getattr(pipeline_module, "_RUNTIME_COMPATIBILITY_INSTALLED", False):
        return
    original = getattr(pipeline_module, "_directional_lifecycle_current", None)
    if original is None:
        return
    try:
        signature = inspect.signature(original)
        positional = [p for p in signature.parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        supports_anchor = len(positional) >= 5 or any(
            p.kind == p.VAR_POSITIONAL for p in signature.parameters.values()
        )
    except (TypeError, ValueError):
        supports_anchor = True

    def compatible(*args, **kwargs):
        if supports_anchor:
            return original(*args, **kwargs)
        # Legacy helper: results, decision, gate_passed, candle.
        return original(*args[:EXPECTED_MIN_POSITIONAL])

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
