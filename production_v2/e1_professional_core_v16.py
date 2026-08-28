"""E1 V16 runtime contract: normalize the public reasoning mirror.

The V15/V16 arbitration core already selects the market state correctly, but
its inherited professional_reasoning dictionary can retain stale V14 fields.
The runtime consumes that dictionary first, so this adapter makes the public
E1 state single-source-of-truth before any downstream engine sees it.
"""
from __future__ import annotations

from typing import Any

from .e1_professional_core_v15 import analyze_e1_professional_v15


def analyze_e1_professional_v16(bars: list[dict[str, Any]] | None) -> dict[str, Any]:
    result = analyze_e1_professional_v15(bars)
    if result.get("analysis_status") != "COMPLETE":
        return result

    market_state = str(result.get("market_state") or "UNCLEAR").upper()
    trend_state = str(result.get("trend_state") or "NONE").upper()

    # Market state is authoritative. A trend state is only valid when the
    # market state itself is TREND_UP/TREND_DOWN; otherwise it must be NONE.
    expected_trend = {"TREND_UP": "UP", "TREND_DOWN": "DOWN"}.get(market_state, "NONE")
    if expected_trend != trend_state:
        trend_state = expected_trend
        result["trend_state"] = trend_state
        result["reasons"] = list(dict.fromkeys([
            *(result.get("reasons") or []),
            "V16_STATE_TELEMETRY_RECONCILED",
        ]))

    reasoning = dict(result.get("professional_reasoning") or {})
    reasoning.update({
        "question": result.get("question", "What is the market doing right now?"),
        "market_state": market_state,
        "trend_state": trend_state,
        "volatility_state": result.get("volatility_state", "UNKNOWN"),
        "structure_state": result.get("structure_state", "UNCLEAR"),
        "directional_pressure": result.get("directional_pressure", "NEUTRAL"),
        "transition": result.get("transition", "UNKNOWN"),
        "transition_status": result.get("transition_status", result.get("transition", "UNKNOWN")),
        "dominant_direction": result.get("dominant_direction", "NEUTRAL"),
        "state_source_of_truth": "E1_TOP_LEVEL_RESULT",
        "reasoning_mirror_synchronized": True,
    })
    result["professional_reasoning"] = reasoning
    result["e1_contract_version"] = "PROFESSIONAL_MARKET_STATE_V16_RUNTIME"
    result["e1_engine_version"] = "PROFESSIONAL_MARKET_STATE_V16_RUNTIME"
    result["architecture"] = "E1_SINGLE_PROFESSIONAL_BRAIN_V16_RUNTIME"
    result["e1_trade_authority"] = False
    return result


__all__ = ["analyze_e1_professional_v16"]
