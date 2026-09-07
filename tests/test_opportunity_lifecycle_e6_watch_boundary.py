from production_v2.contracts import EngineResult
from production_v2.e6_runtime_authority import _pending_event_rescue


def test_e6_pending_watch_is_preserved_as_lifecycle_candidate():
    result = EngineResult(
        "E6",
        "Setup Brain",
        False,
        0.0,
        {
            "setup": "NO_SETUP",
            "finding": "NO CAUSAL SETUP HYPOTHESIS",
            "trade_ready": False,
            "gate_passed": False,
        },
        ("NO_CAUSAL_OPPORTUNITY",),
    )
    upstream = {
        "E4": EngineResult(
            "E4",
            "Liquidity/Auction Analyst",
            False,
            70.0,
            {
                "event": "HIGH_SWEEP_REJECTION",
                "auction_state": "PENDING",
                "event_id": "2026-09-07T10:00:00Z|HIGH_SWEEP_REJECTION",
            },
        ),
        "E5": EngineResult(
            "E5",
            "Location/Value Analyst",
            False,
            0.0,
            {"available_space_atr_short": 1.20},
        ),
    }

    rescued = _pending_event_rescue(result, upstream)
    output = rescued.output

    assert output["direction"] == "SELL"
    assert output["setup"] == "OPPORTUNITY_WATCH"
    assert output["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert output["watch_only"] is True
    assert output["trade_ready"] is False
    assert output["gate_passed"] is False
    assert output["missing_proof"] == ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]
    assert "E6_CAUSAL_SETUP_PROOF" not in output["missing_proof"]
    assert output["execution_authority"] == "E9"
