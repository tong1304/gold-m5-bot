from production_v2.app import _e6_pending_thesis


def test_e6_pending_thesis_never_waits_on_self_proof():
    direction, setup, missing, evidence = _e6_pending_thesis({
        "E6": {
            "setup": "OPPORTUNITY_WATCH",
            "direction": "SELL",
            "watch_only": True,
            "trade_ready": False,
            "gate_passed": False,
            "missing_proof": ["E4_AUCTION_FOLLOW_THROUGH"],
            "supporting_evidence": ["E4_DIRECTIONAL_AUCTION_EVIDENCE"],
        }
    })

    assert direction == "SELL"
    assert setup == "OPPORTUNITY_WATCH"
    assert "E6_CAUSAL_SETUP_PROOF" not in missing
    assert "E6_CAUSAL_SETUP_PROOF" not in evidence
