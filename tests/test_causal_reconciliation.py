from production_v2.causal_reconciliation import reconcile_causal_evidence


def test_conflicting_directional_evidence_is_noise_not_a_watch():
    result = reconcile_causal_evidence(
        {
            "E1": {"pressure": "DOWN", "trend_state": "NONE", "market_state": "TRANSITION"},
            "E2": {"direction": "NEUTRAL", "reasons": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"]},
            "E3": {"structure_direction": "NEUTRAL"},
            "E4": {"auction_state": "PENDING", "direction": "BUY", "event": "HIGH_FAILED_BREAK_RECLAIM"},
            "E5": {"available_space_atr_long": 0.80, "available_space_atr_short": 0.40},
        }
    )
    assert result["state"] == "NO_SETUP"
    assert result["direction"] == "NEUTRAL"
    assert "DIRECTIONAL_CONFLICT" in result["reasons"]


def test_pending_auction_with_directional_alignment_creates_waiting_thesis():
    result = reconcile_causal_evidence(
        {
            "E1": {"pressure": "UP", "trend_state": "UP", "market_state": "TREND"},
            "E2": {"direction": "BUY", "opportunity_maturity": "DEVELOPING"},
            "E3": {"structure_direction": "BUY", "active_regime": "UP"},
            "E4": {"auction_state": "PENDING", "direction": "BUY", "event": "SWEEP_RECLAIM"},
            "E5": {"available_space_atr_long": 1.20, "available_space_atr_short": 0.40},
        }
    )
    assert result["state"] == "DEVELOPING_THESIS"
    assert result["direction"] == "BUY"
    assert "E4_AUCTION_PENDING" in result["evidence"]
    assert "AUCTION_CONFIRMATION" in result["wait_for"]
    assert "E6_CAUSAL_SETUP_PROOF" in result["wait_for"]


def test_confirmed_upstream_without_e6_setup_is_not_a_ready_setup():
    result = reconcile_causal_evidence(
        {
            "E1": {"pressure": "UP", "trend_state": "UP"},
            "E2": {"direction": "BUY", "opportunity_maturity": "CONFIRMED"},
            "E3": {"structure_direction": "BUY", "active_regime": "UP"},
            "E4": {"auction_state": "CONFIRMED", "direction": "BUY"},
            "E5": {"available_space_atr_long": 1.20},
            "E6": {"setup": "NO_SETUP", "reasons": ["STRUCTURAL_SPACE_INSUFFICIENT"]},
        }
    )
    assert result["state"] == "THESIS_CONFIRMED_SETUP_NOT_FORMED"
    assert result["ready"] is False
    assert "E6_CAUSAL_SETUP_PROOF" in result["wait_for"]
