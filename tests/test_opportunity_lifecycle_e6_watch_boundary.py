from production_v2.app import _e6_pending_thesis


def test_e6_pending_watch_is_preserved_as_lifecycle_candidate():
    engines = {
        "E6": {
            "setup": "OPPORTUNITY_WATCH",
            "candidate_type": "OPPORTUNITY_CANDIDATE",
            "direction": "SELL",
            "watch_only": True,
            "trade_ready": False,
            "gate_passed": False,
            "missing_proof": [
                "E4_AUCTION_FOLLOW_THROUGH",
                "E7_CONFIRMATION",
                "STRUCTURAL_SPACE_INSUFFICIENT",
            ],
        }
    }

    pending = _e6_pending_thesis(engines)

    assert pending[0] == "SELL"
    assert pending[1] == "OPPORTUNITY_WATCH"
    assert pending[2] == ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION", "STRUCTURAL_SPACE_INSUFFICIENT"]
    assert "E6_CAUSAL_SETUP_PROOF" in pending[3]
