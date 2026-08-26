from __future__ import annotations

from typing import Any

from trading_system.engines.e2.professional_regime import ProfessionalE2Brain


class E2CoreBrain(ProfessionalE2Brain):
    """Single E2 professional opportunity/regime brain; legacy 2A-2F are paused."""
    pass


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Run E2 as one independent professional analyst.

    E2 owns the opportunity/regime thesis. E1 is only a cross-check and must
    never supply E2's conclusion. Execution remains exclusively E9's job.
    """
    brain = E2CoreBrain("E2_CORE")
    output, confidence, reasons = brain._analyse(snapshot)
    result = dict(output)
    result["confidence"] = float(confidence)
    result["reason_codes"] = list(reasons or ())
    result["reasoning_mode"] = "SINGLE_PROFESSIONAL_CORE"
    result["sub_engines_active"] = False
    result["sub_engines_status"] = "PAUSED"

    # The live service reads professional_reasoning.conclusion for its E2
    # diagnostic line. Previously E2 returned a valid internal thesis but did
    # not publish that field, so production logs incorrectly showed
    # question=None / finding=UNRESOLVED. Publish the E2 answer explicitly.
    result["professional_reasoning"] = {
        "question": result.get("question") or ProfessionalE2Brain.QUESTION,
        "conclusion": (
            f"REGIME={result.get('regime', 'UNRESOLVED')}; "
            f"DIRECTION={result.get('direction', 'NEUTRAL')}; "
            f"PHASE={result.get('phase', 'UNRESOLVED')}; "
            f"OPPORTUNITY={result.get('opportunity', 'NONE')}; "
            f"STATE={result.get('opportunity_state', 'UNPROVEN')}; "
            f"QUALITY={result.get('quality', 'UNPROVEN')}"
        ),
        "observations": list(result.get("observations") or ()),
        "evidence": list(result.get("evidence") or ()),
        "counter_evidence": list(result.get("counter_evidence") or ()),
        "missing_evidence": list(result.get("missing_evidence") or ()),
        "confidence": float(confidence),
        "reasoning_mode": "INDEPENDENT_E2_THESIS_FIRST",
        "e1_cross_check": result.get("alignment_with_e1", "INCONCLUSIVE"),
    }
    result["finding"] = result["professional_reasoning"]["conclusion"]
    result["reasoning_role"] = "OPPORTUNITY_REGIME_ANALYST"
    return result
