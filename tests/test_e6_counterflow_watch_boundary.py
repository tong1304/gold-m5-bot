from production_v2.e6_brain import analyze_e6


def _engines():
    return {
        "e1": {
            "directional_pressure": "DOWN",
            "market_state": "TRANSITION",
            "structure": "BULLISH",
            "directional_consensus": 0.75,
        },
        "e2": {
            "finding": "NEUTRAL opportunity is unproven based on closed-candle evidence.",
            "reasons": ["AUCTION_ACCEPTANCE_NOT_PROVEN", "DIRECTIONAL_EDGE_NOT_ESTABLISHED"],
        },
        "e3": {
            "external_state": "MIXED",
            "internal_state": "MIXED",
            "protected_integrity": "VALID",
            "protected_completeness": "NO_DIRECTIONAL_REGIME",
        },
        "e4": {
            "event": "LOW_SWEEP_REJECTION",
            "finding": "LOW_SWEEP_REJECTION",
            "liquidity_taker": "SELLERS",
            "response_actor": "BUYERS",
            "auction_state": "PENDING",
            "auction_quality": 45.21,
        },
        "e5": {
            "finding": "WAIT_CONFIRMATION",
            "value_state": "EQUILIBRIUM",
            "value_response": "REJECTED_ABOVE_VALUE",
            "repricing_state": "REPRICING_FAILED",
            "structural_location": "INSIDE_STRUCTURE",
            "available_space_atr_long": 0.4266,
            "available_space_atr_short": 0.1573,
        },
    }


def test_counterflow_sweep_is_watch_not_no_causal_opportunity():
    out = analyze_e6(**_engines()).to_dict()

    assert out["setup"] == "OPPORTUNITY_WATCH"
    assert out["candidate_type"] == "OPPORTUNITY_CANDIDATE"
    assert out["direction"] == "BUY"
    assert out["watch_only"] is True
    assert out["trade_ready"] is False
    assert out["trade_permission"] is False
    assert out["gate_passed"] is False
    assert "NO_CAUSAL_OPPORTUNITY" not in out["reason_codes"]
    assert "E4_AUCTION_FOLLOW_THROUGH" in out["missing_proof"]
    assert "E7_CONFIRMATION" in out["missing_proof"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in out["missing_proof"]
    assert "No causal setup hypothesis" not in out["finding"]


def test_pending_sweep_without_location_does_not_create_watch():
    engines = _engines()
    engines["e5"] = {
        "finding": "WAIT_CONFIRMATION",
        "value_state": "EQUILIBRIUM",
        "value_response": "NEUTRAL",
        "repricing_state": "UNCONFIRMED",
        "structural_location": "INSIDE_STRUCTURE",
        "available_space_atr_long": 0.4266,
        "available_space_atr_short": 0.1573,
    }
    out = analyze_e6(**engines).to_dict()

    assert out["setup"] not in {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE"}
    assert out["trade_ready"] is False
