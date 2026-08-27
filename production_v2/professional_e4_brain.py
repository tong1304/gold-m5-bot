"""Production-V2 E4 professional brain entrypoint.

E4 is intentionally exposed as its own professional brain module, at the same
module level as the other professional engines. The implementation remains
analysis-only: it detects liquidity, sweeps, rejection, acceptance and failed
break/reclaim events; E9 remains the sole execution decision authority.
"""
from __future__ import annotations

from .e4_brain import analyze_e4 as _analyze_e4

ARCHITECTURE = "E4_SINGLE_PROFESSIONAL_BRAIN_V12"
PROFESSIONAL_QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
DECISION_AUTHORITY = "E9_ONLY"


def analyze_e4(snapshot=None, evidence_bus=None):
    """Run the professional E4 liquidity/auction analysis.

    The underlying V11 implementation is preserved as the calculation core;
    this module is now the canonical professional E4 entrypoint. No execution
    decision, gate or trading score is produced here.
    """
    result = dict(_analyze_e4(snapshot, evidence_bus))
    result["architecture"] = ARCHITECTURE
    result["professional_brain"] = True
    result["reasoning_role"] = "LIQUIDITY_EVENT_ANALYST"
    result["question"] = PROFESSIONAL_QUESTION
    result["decision_authority"] = DECISION_AUTHORITY
    result["trade_decision_authority"] = False
    result["decision"] = None
    result["gate"] = None
    result["score"] = None
    result["upstream_decisions_used"] = False
    result["upstream_gates_used"] = False
    result["upstream_scores_used"] = False
    return result


__all__ = ["analyze_e4", "ARCHITECTURE", "PROFESSIONAL_QUESTION", "DECISION_AUTHORITY"]
