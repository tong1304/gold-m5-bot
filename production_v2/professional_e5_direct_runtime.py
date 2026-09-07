from __future__ import annotations

from functools import wraps
from typing import Any


def install(module: Any) -> None:
    if getattr(module, "_PROFESSIONAL_E5_DIRECT_V1", False):
        return
    original = module.analyze_e5

    @wraps(original)
    def analyze_e5(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        output = dict(getattr(result, "output", {}) or {})
        extension = str(output.get("extension_state") or "").upper()
        location = str(output.get("location_state") or "").upper()
        if extension in {"EXTENDED", "EXCESSIVE"} and location == "ACCEPTED_AUCTION_NO_REVERSAL_EDGE":
            output["location_state"] = "WAIT_REPRICING"
            output["location_contract_state"] = location
            reasons = list(output.get("reason_codes") or [])
            reasons.append("EXTENDED_ALIGNED_MARKET_WAIT_REPRICING")
            output["reason_codes"] = list(dict.fromkeys(reasons))
            trace = list(output.get("reasoning_trace") or [])
            trace.append("EXTENDED_MARKET -> WAIT_REPRICING")
            output["reasoning_trace"] = trace
        return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)

    module.analyze_e5 = analyze_e5
    module._PROFESSIONAL_E5_DIRECT_V1 = True
