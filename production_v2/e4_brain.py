"""Production V2 E4 — single professional brain interface.

The public E4 interface is intentionally identical in shape to E1/E2/E5:
one specialist brain, analysis-only, no execution authority. The locked V14
implementation remains the E4 calculation authority behind this stable module
interface; no E1-E3/E5-E9 behavior is changed here.
"""
from .e4_brain_v14 import analyze_e4

QUESTION = "Where is liquidity, who took it, and did price accept or reject the auction?"
ARCHITECTURE = "E4_PROFESSIONAL_CORE_ONLY"
DECISION_AUTHORITY = "E9_ONLY"

__all__ = ["analyze_e4", "QUESTION", "ARCHITECTURE", "DECISION_AUTHORITY"]
