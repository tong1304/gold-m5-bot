from __future__ import annotations

import traceback


def install(pipeline_module) -> None:
    """Diagnostic-only runtime membrane: expose the exact pipeline exception site.

    This wrapper never changes decisions or catches/replaces exceptions. It only
    prints the traceback and re-raises, so the live service can identify the
    actual NameError source instead of logging only ``str(exc)``.
    """
    if getattr(pipeline_module, "_RUNTIME_TRACE_BOUNDARY_INSTALLED", False):
        return
    original = pipeline_module.ProductionPipeline.run

    def traced(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        try:
            return original(
                self,
                market_data,
                wait_bars=wait_bars,
                resume_state=resume_state,
                historical_calibration=historical_calibration,
            )
        except Exception:
            symbol = str(market_data.get("symbol") or "UNKNOWN").upper() if isinstance(market_data, dict) else "UNKNOWN"
            candle = str(market_data.get("candle_close_timestamp") or "") if isinstance(market_data, dict) else ""
            print(
                f"[PRODUCTION V2] PIPELINE_EXCEPTION_TRACE symbol={symbol} candle={candle}",
                flush=True,
            )
            traceback.print_exc()
            raise

    pipeline_module.ProductionPipeline.run = traced
    pipeline_module._RUNTIME_TRACE_BOUNDARY_INSTALLED = True
