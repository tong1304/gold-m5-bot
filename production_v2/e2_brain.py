from __future__ import annotations

from typing import Any

from trading_system.engines.e2.professional_regime import ProfessionalE2Brain


class E2CoreBrain(ProfessionalE2Brain):
    """Single E2 professional opportunity/regime brain; legacy 2A-2F are paused."""
    pass


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    brain = E2CoreBrain("E2_CORE")
    output, confidence, reasons = brain._analyse(snapshot)
    result = dict(output)
    result["confidence"] = float(confidence)
    result["reason_codes"] = list(reasons or ())
    result["reasoning_mode"] = "SINGLE_PROFESSIONAL_CORE"
    result["sub_engines_active"] = False
    result["sub_engines_status"] = "PAUSED"
    return result
