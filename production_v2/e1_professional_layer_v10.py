"""E1 V10-compatible public interface backed by the V11 professional core."""
from .e1_professional_core_v11 import analyze_e1_professional_v11


def analyze_e1_professional_v10(bars):
    result = analyze_e1_professional_v11(bars)
    # Keep the established public contract name for downstream compatibility.
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V10"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V11"
    return result


__all__ = ["analyze_e1_professional_v10", "analyze_e1_professional_v11"]
