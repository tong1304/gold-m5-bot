"""E1 Market-State Brain.

Implementation is isolated in e1_brain_v3 so the E1 contract stays stable while
its decision model can be evolved independently of E2-E9.
"""
from .e1_brain_v3 import MARKET_STATES, QUESTION, OWNERSHIP, analyze_e1

PROFESSIONAL_QUESTION = QUESTION
E1_OWNERSHIP = OWNERSHIP
EVIDENCE_HIERARCHY = "DATA_QUALITY -> VOLATILITY -> STRUCTURE -> PRESSURE -> PERSISTENCE -> STATE -> TRANSITION"

__all__ = ["MARKET_STATES", "PROFESSIONAL_QUESTION", "EVIDENCE_HIERARCHY", "E1_OWNERSHIP", "analyze_e1"]
