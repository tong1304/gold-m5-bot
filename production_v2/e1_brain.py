"""E1 Market-State Brain.

Stable public contract. Professional classification, reconciliation, and
regime-handoff protection are isolated from E2-E9.
"""
from .e1_brain_v3 import MARKET_STATES, QUESTION, OWNERSHIP
from .e1_transition_guard_v3 import analyze_e1

PROFESSIONAL_QUESTION = QUESTION
E1_OWNERSHIP = OWNERSHIP
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"

__all__ = ["MARKET_STATES", "PROFESSIONAL_QUESTION", "EVIDENCE_HIERARCHY", "E1_OWNERSHIP", "analyze_e1"]
