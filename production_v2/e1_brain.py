"""E1 Market-State Brain.

Stable public contract. The professional classifier and reconciliation layers
are isolated from E2-E9 so E1 can evolve without changing downstream ownership.
"""
from .e1_brain_v3 import MARKET_STATES, QUESTION, OWNERSHIP
from .e1_reconciliation import analyze_e1

PROFESSIONAL_QUESTION = QUESTION
E1_OWNERSHIP = OWNERSHIP
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"

__all__ = ["MARKET_STATES", "PROFESSIONAL_QUESTION", "EVIDENCE_HIERARCHY", "E1_OWNERSHIP", "analyze_e1"]
