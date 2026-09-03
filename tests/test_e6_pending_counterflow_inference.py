from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, None, 70.0, output, ())


def test_pending_counterflow_infers_auction_direction_when_e4_direction_is_absent():
    upstream = {
        "E1": _engine("E1", {"directional_pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "NEUTRAL opportunity is emerging", "direction": "NEUTRAL", "opportunity_state": "EMERGING"}),
        "E3": _engine("E3", {"external_state": "MIXED", "internal_state": "UP"}),
        "E4": _engine("E4", {
            "event": "HIGH_LIQUIDITY_INTERACTION",
            "finding": "HIGH_LIQUIDITY_INTERACTION",
            "auction_state": "PENDING",
            "response_actor": "BUYERS",
            "liquidity_taker": "SELLERS",
        }),
        "E5": _engine("E5", {
            "finding": "ACCEPTED_AUCTION_NO_REVERSAL_EDGE",
            "value_state": "DISCOUNT",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.91,
            "available_space_atr_short": 0.63,
        }),
    }
    result = analyze_e6({"bars": [], "symbol": "XAU/USD", "timeframe": "M5"}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert result.output["direction"] == "SELL"
    assert result.output["watch_only"] is True
    assert "E4_AUCTION_FOLLOW_THROUGH" in result.output["missing_proof"]
    assert "NO_CAUSAL_OPPORTUNITY" not in result.output["reason_codes"]
    assert result.gate_passed is False
