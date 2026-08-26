from __future__ import annotations

from typing import Any

from trading_system.engines.e2.professional_regime import ProfessionalE2Brain


# E2's production entry point is deliberately direct: production_v2 calls
# analyze_e2(), and this module owns the E2 brain invocation.  Sub-engines stay
# paused; E1 is only an independent upstream market-state input.
E2_BRAIN = ProfessionalE2Brain


def analyze_e2(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Analyze the opportunity/regime directly with the real E2 brain.

    No E2 sub-engine, scorer, gate, or newly-created replacement brain is
    inserted between the production pipeline and the real E2 implementation.
    """
    brain = E2_BRAIN("E2_CORE")
    output, confidence, reasons = brain._analyse(snapshot)
    result = dict(output)
    result["confidence"] = float(confidence)
    result["reason_codes"] = list(reasons or ())
    result["reasoning_mode"] = "REAL_PRODUCTION_E2_BRAIN_DIRECT"
    result["sub_engines_active"] = False
    result["sub_engines_status"] = "PAUSED"
    result["reasoning_role"] = "OPPORTUNITY_REGIME_ANALYST"
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
    return result
