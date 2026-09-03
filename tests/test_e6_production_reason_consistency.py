from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, None, 70.0, output, ())


def test_production_style_pending_acceptance_has_consistent_e6_reason_codes():
    upstream = {
        "E1": _engine("E1", {"directional_pressure": "UP", "pressure": "UP", "structure": "BULLISH"}),
        "E2": _engine("E2", {
            "finding": "NEUTRAL opportunity is emerging based on closed-candle evidence.",
            "direction": "NEUTRAL",
            "opportunity_state": "EMERGING",
        }),
        "E3": _engine("E3", {
            "external_state": "MIXED",
            "internal_state": "UP",
            "finding": "STRUCTURE_FORMING",
            "structure_integrity": "VALID",
        }),
        "E4": _engine("E4", {
            "event": "HIGH_ACCEPTANCE_CANDIDATE",
            "finding": "HIGH_ACCEPTANCE_CANDIDATE",
            "auction_state": "PENDING",
            "liquidity_taker": "BUYERS",
            "response_actor": "BUYERS",
        }),
        "E5": _engine("E5", {
            "finding": "FAVORABLE_LOCATION",
            "value_state": "EQUILIBRIUM",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.7658,
            "available_space_atr_short": 1.4309,
        }),
    }

    result = analyze_e6({"bars": [], "symbol": "XAU/USD", "timeframe": "M5"}, upstream)
    output = result.output

    assert output["setup"] == "OPPORTUNITY_WATCH"
    assert output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert output["direction"] == "BUY"
    assert output["watch_only"] is True
    assert "E4_AUCTION_FOLLOW_THROUGH" in output["missing_proof"]
    assert "E7_CONFIRMATION" in output["missing_proof"]
    assert "NO_CAUSAL_OPPORTUNITY" not in output.get("reason_codes", [])
    assert "NO_CAUSAL_OPPORTUNITY" not in output.get("reasons", [])
    assert "NO_CAUSAL_OPPORTUNITY" not in result.reason_codes
    assert result.gate_passed is False
