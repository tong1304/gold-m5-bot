from __future__ import annotations

from typing import Any


def _module_name(value: Any) -> str:
    return f"{getattr(value, '__module__', '?')}.{getattr(value, '__name__', type(value).__name__)}"


def _is_timing_membrane(value: Any) -> bool:
    return callable(value) and str(getattr(value, "_timing_membrane_version", "")).startswith("OPPORTUNITY_TIMING_MEMBRANE_")


def install(pipeline_module, e6_module, e8_module, e9_module) -> None:
    """Install one final runtime binder; E6 timing membrane is authoritative."""
    if getattr(pipeline_module, "_FINAL_RUNTIME_BINDING_INSTALLED", False):
        return

    original_run = pipeline_module.ProductionPipeline.run
    pipeline_module._E6_FINAL_AUTHORITY = getattr(
        pipeline_module,
        "_E6_RUNTIME_OVERRIDE",
        getattr(pipeline_module, "analyze_e6", e6_module.analyze_e6),
    )

    def _ensure_e6_membrane():
        # A later compatibility installer must never be able to silently replace
        # the timing membrane with the legacy patched_analyze_e6 callable.
        try:
            from .opportunity_timing_runtime_hotfix import install as install_timing
            install_timing(pipeline_module)
        except Exception as exc:
            print(f"[PRODUCTION V2] TIMING_MEMBRANE_REPAIR_ERROR error={exc!r}", flush=True)

        membrane = getattr(pipeline_module, "_E6_TIMING_MEMBRANE", None)
        if _is_timing_membrane(membrane):
            pipeline_module._E6_RUNTIME_OVERRIDE = membrane
            pipeline_module.analyze_e6 = membrane
            return membrane

        current = getattr(pipeline_module, "_E6_RUNTIME_OVERRIDE", None)
        if _is_timing_membrane(current):
            pipeline_module._E6_TIMING_MEMBRANE = current
            pipeline_module.analyze_e6 = current
            return current

        return current or getattr(pipeline_module, "_E6_FINAL_AUTHORITY", e6_module.analyze_e6)

    def run_with_final_bindings(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        e6_binding = _ensure_e6_membrane()
        pipeline_module.analyze_e6 = e6_binding
        pipeline_module.analyze_e8 = e8_module.analyze_e8
        pipeline_module.analyze_e9 = e9_module.analyze_e9
        timing_active = _is_timing_membrane(e6_binding)
        print(
            "[PRODUCTION V2] FINAL_BINDING "
            f"E6={_module_name(e6_binding)} "
            f"E8={_module_name(pipeline_module.analyze_e8)} "
            f"E9={_module_name(pipeline_module.analyze_e9)} "
            f"TIMING_MEMBRANE={'ACTIVE' if timing_active else 'INACTIVE'}",
            flush=True,
        )
        if not timing_active:
            print("[PRODUCTION V2] FINAL_BINDING_FATAL E6_TIMING_MEMBRANE_NOT_AUTHORITATIVE", flush=True)
        return original_run(
            self,
            market_data,
            wait_bars=wait_bars,
            resume_state=resume_state,
            historical_calibration=historical_calibration,
        )

    pipeline_module.ProductionPipeline.run = run_with_final_bindings
    pipeline_module._FINAL_RUNTIME_BINDING_INSTALLED = True
