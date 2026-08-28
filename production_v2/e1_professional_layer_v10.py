"""E1 public compatibility interface backed by the V12 professional core."""
from .e1_professional_core_v12 import analyze_e1_professional_v12


def analyze_e1_professional_v10(bars):
    result = analyze_e1_professional_v12(bars)
    # Preserve the downstream function name while advancing the actual E1 brain.
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V10"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V12"
    return result


__all__ = ["analyze_e1_professional_v10", "analyze_e1_professional_v12"]
