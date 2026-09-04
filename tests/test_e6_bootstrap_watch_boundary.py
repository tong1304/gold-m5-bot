from production_v2 import pipeline as pipeline_module
from production_v2.bootstrap_surgery import install
from production_v2.contracts import EngineResult


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 70.0, output, ())


def test_bootstrap_does_not_promote_e6_opportunity_watch_into_setup():
    upstream = {
        "E1": _engine("E1", {"directional_pressure": "UP"}),
        "E2": _engine("E2", {"finding": "NEUTRAL opportunity is emerging", "direction": "NEUTRAL", "opportunity_state": "EMERGING"}),
        "E3": _engine("E3", {"external_state": "MIXED", "internal_state": "MIXED"}),
        "E4": _engine("E4", {"event": "HIGH_ACCEPTANCE_CANDIDATE", "finding": "HIGH_ACCEPTANCE_CANDIDATE", "auction_state": "PENDING", "response_actor": "BUYERS", "liquidity_taker": "BUYERS"}),
        "E5": _engine("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "PREMIUM", "structural_location": "AT_RESISTANCE", "available_space_atr_long": 1.20, "available_space_atr_short": 0.60}),
    }
    install(pipeline_module)
    output = pipeline_module.analyze_e6({}, upstream).output
    assert output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert output["setup"] == "OPPORTUNITY_WATCH"
    assert output["watch_only"] is True
    assert output["trade_ready"] is False
    assert output["gate_passed"] is False
    assert output.get("setup_exists") is not True
    assert output["opportunity_stage"] == "OPPORTUNITY_WATCH"
    assert "E4_AUCTION_FOLLOW_THROUGH" in output["missing_proof"]
    assert "NO_CAUSAL_OPPORTUNITY" not in output["reason_codes"]
