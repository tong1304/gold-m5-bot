from production_v2.contracts import EngineResult
from production_v2.e6_brain import analyze_e6

# Regression fixture mirrors the 2026-09-06 live LOW_ACCEPTANCE_CANDIDATE case.


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, None, 70.0, output, ())


def test_pending_low_acceptance_event_survives_e6_as_watch():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "directional_pressure": "BEARISH", "pressure": "BEARISH"}),
        "E2": _engine("E2", {"finding": "NEUTRAL opportunity is unproven based on closed-candle evidence", "direction": "NEUTRAL", "opportunity_state": "UNPROVEN", "opportunity_maturity": "UNPROVEN"}),
        "E3": _engine("E3", {"external_state": "UP", "internal_state": "MIXED", "protected_active_regime": "UP", "protected_completeness": "COMPLETE"}),
        "E4": _engine("E4", {"event": "LOW_ACCEPTANCE_CANDIDATE", "finding": "LOW_ACCEPTANCE_CANDIDATE", "event_id": "2026-09-06T12:05:00Z|LOW_ACCEPTANCE_CANDIDATE|LOW|79922.14|DOWN", "auction_state": "PENDING", "liquidity_taker": "SELLERS", "response_actor": "SELLERS", "liquidity_quality": 81.25}),
        "E5": _engine("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "DISCOUNT", "structural_location": "INSIDE_STRUCTURE", "available_space_atr_long": 1.217, "available_space_atr_short": 0.422}),
    }
    result = analyze_e6({"bars": [], "symbol": "BTC/USD", "timeframe": "M5"}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert result.output["direction"] == "SELL"
    assert result.output["watch_only"] is True
    assert result.output["trade_ready"] is False
    assert "NO_CAUSAL_OPPORTUNITY" not in result.output["reason_codes"]
    assert "E4_AUCTION_FOLLOW_THROUGH" in result.output["missing_proof"]
