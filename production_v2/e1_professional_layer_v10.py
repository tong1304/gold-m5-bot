"""E1 public compatibility interface backed by the V14 professional core."""
from .e1_professional_core_v14 import analyze_e1_professional_v14


def analyze_e1_professional_v10(bars):
    result = analyze_e1_professional_v14(bars)
    # Preserve the downstream function name while advancing the actual E1 brain.
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V10"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V14"
    return result


__all__ = ["analyze_e1_professional_v10", "analyze_e1_professional_v14"]
