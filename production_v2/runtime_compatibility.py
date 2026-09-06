from __future__ import annotations

import inspect
from typing import Any

EXPECTED_MIN_POSITIONAL = 4
LEGACY_SIGNATURE_ERROR = "takes 4 positional arguments but 5 were given"


def install(pipeline_module: Any) -> None:
    """Normalize the lifecycle call boundary across mixed runtime wrappers.

    A previous compatibility wrapper (or another decorator) may expose *args,
    making signature inspection report false support for causal_anchor even when
    the wrapped legacy helper still accepts only four positional arguments.
    Therefore the boundary first attempts the modern five-argument call and, for
    the exact legacy arity error, retries with the original four-argument API.
    """
    if getattr(pipeline_module, "_RUNTIME_COMPATIBILITY_INSTALLED", False):
        return
    original = getattr(pipeline_module, "_directional_lifecycle_current", None)
    if not callable(original):
        return

    try:
        signature = inspect.signature(original)
        positional = [
            p for p in signature.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        supports_anchor = len(positional) >= 5
    except (TypeError, ValueError):
        supports_anchor = False

    def compatible(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except TypeError as exc:
            if len(args) >= 5 and LEGACY_SIGNATURE_ERROR in str(exc):
                return original(*args[:EXPECTED_MIN_POSITIONAL])
            raise

    compatible.__name__ = getattr(original, "__name__", "_directional_lifecycle_current")
    compatible.__module__ = getattr(original, "__module__", __name__)
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
