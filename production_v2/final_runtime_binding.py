from __future__ import annotations

from typing import Any

_INSTALLED = False


def _module_name(value: Any) -> str:
    return f"{getattr(value, '__module__', '?')}.{getattr(value, '__name__', type(value).__name__)}"


def install(pipeline_module, e6_module, e8_module, e9_module) -> None:
    """Make final authority bindings deterministic at every live pipeline run.

    Package startup installs several wrappers in sequence.  This final membrane
    deliberately rebinds E6/E8/E9 immediately before execution so a startup
    wrapper cannot leave the pipeline holding an earlier function reference.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original_run = pipeline_module.ProductionPipeline.run

    def run_with_final_bindings(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        pipeline_module.analyze_e6 = e6_module.analyze_e6
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
    _INSTALLED = True
