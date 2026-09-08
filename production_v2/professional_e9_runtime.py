from __future__ import annotations

from functools import wraps
from typing import Any

from .professional_opportunity_controller import derive_opportunity_state


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_PROFESSIONAL_E9_RUNTIME_V1", False):
        return
    original = pipeline_module.analyze_e9

    @wraps(original)
    def analyze_e9(snapshot: dict[str, Any], results: dict[str, Any]):
        result = original(snapshot, results)
        output = dict(getattr(result, "output", {}) or {})
        payload = {
            "candle": snapshot.get("candle_close_timestamp") or snapshot.get("candle"),
            "e1": dict(getattr(results.get("E1"), "output", {}) or {}),
            "e2": dict(getattr(results.get("E2"), "output", {}) or {}),
            "e3": dict(getattr(results.get("E3"), "output", {}) or {}),
            "e4": dict(getattr(results.get("E4"), "output", {}) or {}),
            "e5": dict(getattr(results.get("E5"), "output", {}) or {}),
            "e6": dict(getattr(results.get("E6"), "output", {}) or {}),
            "e7": dict(getattr(results.get("E7"), "output", {}) or {}),
            "e8": dict(getattr(results.get("E8"), "output", {}) or {}),
            "e9": output,
        }
        state = derive_opportunity_state(payload)
        output["professional_opportunity"] = state
        output["canonical_event_clock"] = state.get("canonical_event_clock", {})
        output["opportunity_stage"] = state.get("stage")
        output["opportunity_direction"] = state.get("direction")
        output["execution_authorized"] = state.get("execution_authorized", False)
        return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)

    pipeline_module.analyze_e9 = analyze_e9
    pipeline_module._PROFESSIONAL_E9_RUNTIME_V1 = True
