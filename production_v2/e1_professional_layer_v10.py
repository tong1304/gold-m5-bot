"""E1 V10-compatible public interface backed by the V11 professional core."""
from .e1_professional_core_v11 import analyze_e1_professional_v11

analyze_e1_professional_v10 = analyze_e1_professional_v11

__all__ = ["analyze_e1_professional_v10", "analyze_e1_professional_v11"]
