"""E1 V10 public compatibility interface backed by the hardened V14 core."""
from .e1_professional_core_v14 import analyze_e1_professional_v14

V11_ARBITRATION_ORDER = [
    "DATA_QUALITY",
    "STRUCTURE",
    "LONG_HORIZON",
    "EMA_CONTEXT",
    "PRESSURE",
    "PERSISTENCE",
    "VOLATILITY",
    "COUNTER_EVIDENCE",
    "TRANSITION",
]
V11_COMPATIBILITY = "LEGACY_PUBLIC_CONTRACT_OVER_HARDENED_V14_CORE"


def analyze_e1_professional_v10(bars):
    result = analyze_e1_professional_v14(bars)
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V10"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V11"
    result["e1_compatibility"] = V11_COMPATIBILITY
    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning["arbitration_order"] = list(V11_ARBITRATION_ORDER)
    reasoning["trade_boundary"] = "MARKET_STATE_ONLY"
    result["professional_reasoning"] = reasoning
    return result


__all__ = ["analyze_e1_professional_v10", "analyze_e1_professional_v14"]
