from production_v2.contracts import EngineResult
from production_v2 import e6_pending_event_surgery as surgery


def _result(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", ())))


def _upstream():
    return {
        "E1": _result("E1", {"directional_pressure": "BEARISH", "market_state": "TRANSITION"}),
        "E2": _result("E2", {"finding": "NEUTRAL opportunity is unproven", "opportunity_maturity": "UNRESOLVED", "direction": "NEUTRAL"}),
        "E3": _result("E3", {"external_state": "MIXED", "internal_state": "MIXED", "lifecycle": "ACTIVE"}),
        "E4": _result("E4", {
            "event": "LOW_SWEEP_REJECTION",
            "event_id": "2026-09-05T22:45:00Z|LOW_SWEEP_REJECTION|LOW|79770.00000000|UP",
            "direction": "DOWN",
            "auction_state": "PENDING",
            "auction_information": "MEDIUM_INFORMATION",
        }),
        "E5": _result("E5", {
            "finding": "ACCEPTED_AUCTION_NO_REVERSAL_EDGE",
            "value_state": "DISCOUNT",
            "preferred_location": "",
            "available_space_atr_long": 0.7877,
            "available_space_atr_short": 0.3005,
        }),
    }


def test_low_sweep_pending_becomes_contested_watch_not_no_setup():
    candidate = surgery._generic_candidate(_upstream())
    assert candidate is not None
    assert candidate["direction"] == "BUY"
    assert "E4_PENDING_AUCTION_EVENT" in candidate["counter"]
    assert "E1_COUNTERFLOW" in candidate["counter"]
    assert "E4_AUCTION_FOLLOW_THROUGH" in candidate["missing"]


def test_runtime_surgery_preserves_trade_veto():
    class Pipeline:
        pass

    pipeline = Pipeline()
    pipeline.analyze_e6 = lambda market_data, upstream: _result(
        "E6",
        {
            "setup": "NO_SETUP",
            "finding": "No surviving causal opportunity thesis from E1-E5; legacy setup output is suppressed.",
            "reason_codes": ["NO_CAUSAL_OPPORTUNITY"],
            "trade_ready": False,
            "gate_passed": False,
        },
    )
    surgery.install(pipeline)
    result = pipeline.analyze_e6({}, _upstream())
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["watch_only"] is True
    assert result.output["trade_ready"] is False
    assert result.output["gate_passed"] is False
    assert result.output["e6_thesis_proven"] is False
    assert result.output["direction"] == "BUY"
    assert result.output["thesis_status"] == "CONTESTED"
    assert result.output["opportunity_id"].startswith("BUY|OPPORTUNITY_WATCH|")
