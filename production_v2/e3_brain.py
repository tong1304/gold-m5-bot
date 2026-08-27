"""Production V2 E3 — single professional brain interface.

The public E3 interface is intentionally identical in shape to E1/E2/E5:
one specialist brain, analysis-only, no execution authority. The locked V8
implementation remains the E3 calculation authority behind this stable module
interface; no E1/E2/E4-E9 behavior is changed here.
"""
from .e3_brain_v8 import analyze_e3

QUESTION = "What is price structure communicating?"
ARCHITECTURE = "E3_PROFESSIONAL_CORE_ONLY"
DECISION_AUTHORITY = "E9_ONLY"

__all__ = ["analyze_e3", "QUESTION", "ARCHITECTURE", "DECISION_AUTHORITY"]
