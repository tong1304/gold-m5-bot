from __future__ import annotations

from typing import Any


def _module_name(value: Any) -> str:
    return f"{getattr(value, '__module__', '?')}.{getattr(value, '__name__', type(value).__name__)}"


def install(pipeline_module, e6_module, e8_module, e9_module) -> None:
    """Make final authority bindings deterministic without clobbering later E6 surgery.

    E6 is authoritative, but production startup may install a policy-preserving
    E6 membrane after package initialization. The final runtime binder must use
    that explicitly registered pipeline binding instead of blindly restoring the
    raw e6_brain callable on every candle.
    """
    if getattr(pipeline_module, "_FINAL_RUNTIME_BINDING_INSTALLED", False):
        return

    original_run = pipeline_module.ProductionPipeline.run
    pipeline_module._E6_FINAL_AUTHORITY = getattr(pipeline_module, "analyze_e6", e6_module.analyze_e6)

    def run_with_final_bindings(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        e6_binding = getattr(
            pipeline_module,
            "_E6_RUNTIME_OVERRIDE",
            getattr(pipeline_module, "_E6_FINAL_AUTHORITY", e6_module.analyze_e6),
        )
        pipeline_module.analyze_e6 = e6_binding
        pipeline_module.analyze_e8 = e8_module.analyze_e8
        pipeline_module.analyze_e9 = e9_module.analyze_e9
        print(
            "[PRODUCTION V2] FINAL_BINDING "
            f"E6={_module_name(pipeline_module.analyze_e6)} "
            f"E8={_module_name(pipeline_module.analyze_e8)} "
            f"E9={_module_name(pipeline_module.analyze_e9)}",
            flush=True,
        )
        return original_run(
            self,
            market_data,
            wait_bars=wait_bars,
            resume_state=resume_state,
            historical_calibration=historical_calibration,
        )

    pipeline_module.ProductionPipeline.run = run_with_final_bindings
    pipeline_module._FINAL_RUNTIME_BINDING_INSTALLED = True