import os

from production_v2.contracts import EngineResult


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 70.0, output, ())


def test_production_runtime_installs_final_e6_authority_and_preserves_pending_watch():
    os.environ["PRODUCTION_V2_DISABLE_LIVE"] = "1"
    import production_v2.app as app_module

    pipeline_module = app_module.pipeline_module
    assert getattr(pipeline_module, "_E6_RUNTIME_AUTHORITY_INSTALLED", False) is True

    upstream = {
        "E1": _engine("E1", {"directional_pressure": "SELL"}),
        "E2": _engine("E2", {"finding": "NEUTRAL opportunity is unproven based on closed-candle evidence", "direction": "NEUTRAL", "opportunity_state": "UNRESOLVED"}),
        "E3": _engine("E3", {"external_state": "BULLISH", "internal_state": "MIXED", "lifecycle": "VALID"}),
        "E4": _engine("E4", {"finding": "LOW_ACCEPTANCE_CANDIDATE", "auction_state": "PENDING", "event_id": "2026-09-06T12:05:00Z|LOW_ACCEPTANCE_CANDIDATE|LOW|79922.14|DOWN"}),
        "E5": _engine("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "DISCOUNT", "available_space_atr_short": 0.4218, "available_space_atr_long": 1.2170}),
    }

    result = pipeline_module.analyze_e6({"bars": [], "symbol": "BTC/USD", "timeframe": "M5"}, upstream)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["watch_only"] is True
    assert result.output["trade_ready"] is False
    assert result.output["e6_thesis_proven"] is False
    assert "E4_AUCTION_FOLLOW_THROUGH" in result.output["missing_proof"]
