from __future__ import annotations

from functools import wraps
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_PROFESSIONAL_LIFECYCLE_GUARD_V1", False):
        return
    original_directional = pipeline_module._directional_lifecycle_current
    original_advance = pipeline_module.advance_opportunity_directions
    original_e5 = pipeline_module.analyze_e5

    @wraps(original_e5)
    def analyze_e5(*args: Any, **kwargs: Any):
        result = original_e5(*args, **kwargs)
        output = dict(getattr(result, "output", {}) or {})
        extension = _text(output.get("extension_state"))
        location = _text(output.get("location_state"))
        # Extended/excessive aligned price is a location warning, not a reversal
        # signal. Preserve the richer finding but expose the professional contract
        # expected by downstream lifecycle logic.
        if extension in {"EXTENDED", "EXCESSIVE"} and location == "ACCEPTED_AUCTION_NO_REVERSAL_EDGE":
            output["location_state"] = "WAIT_REPRICING"
            output["location_contract_state"] = location
            reasons = list(output.get("reason_codes") or [])
            reasons.append("EXTENDED_ALIGNED_MARKET_WAIT_REPRICING")
            output["reason_codes"] = list(dict.fromkeys(reasons))
        return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)

    @wraps(original_directional)
    def directional(*args: Any, **kwargs: Any):
        result = original_directional(*args, **kwargs)
        results = args[0] if args and isinstance(args[0], dict) else {}
        e6 = dict(getattr(results.get("E6"), "output", {}) or {})
        tradeability = _text(e6.get("tradeability")) or "UNKNOWN"
        setup_exists = bool(e6.get("setup_exists"))
        setup = _text(e6.get("setup") or e6.get("setup_family"))
        source = "E6_SETUP" if setup_exists and setup else "E6_THESIS" if setup_exists else ""
        if isinstance(result, tuple) and result and isinstance(result[0], dict):
            book = result[0]
            for direction, item in book.items():
                if not isinstance(item, dict):
                    continue
                item["tradeability"] = tradeability
                item["structural_space_is_economic_gate"] = True
                if source and _text(item.get("direction")) == _text(direction):
                    item["lifecycle_source"] = source
                    item.setdefault("setup", setup)
            return result
        return result

    @wraps(original_advance)
    def advance(previous: Any, current_by_direction: Any, **kwargs: Any):
        result = original_advance(previous, current_by_direction, **kwargs)
        opportunities = result.get("opportunities") if isinstance(result, dict) else None
        if isinstance(opportunities, dict):
            for item in opportunities.values():
                if not isinstance(item, dict):
                    continue
                if _text(item.get("state")) == "ARMED" and _text(item.get("tradeability")) == "CONSTRAINED":
                    item["state"] = "THESIS_FORMED"
                    item["lifecycle_state"] = "THESIS_FORMED"
                    item["opportunity_phase"] = "THESIS_FORMED"
                    item["trade_authorized"] = False
                    item["continuity"] = "THESIS_WAITING_FOR_E8_PRE_ECONOMICS"
                    item["wait_for"] = "E8_PRE_ECONOMICS"
            leader = result.get("leader")
            if leader in opportunities:
                lead = opportunities[leader]
                result["state"] = lead.get("state", result.get("state"))
                result["lifecycle_state"] = lead.get("lifecycle_state", result.get("lifecycle_state"))
                result["opportunity_phase"] = lead.get("opportunity_phase", result.get("opportunity_phase"))
                result["wait_for"] = lead.get("wait_for", result.get("wait_for"))
        return result

    pipeline_module.analyze_e5 = analyze_e5
    pipeline_module._directional_lifecycle_current = directional
    pipeline_module.advance_opportunity_directions = advance
    pipeline_module._PROFESSIONAL_LIFECYCLE_GUARD_V1 = True
