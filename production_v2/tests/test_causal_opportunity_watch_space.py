from production_v2.causal_reconciliation import reconcile_causal_evidence


def test_developing_aligned_opportunity_remains_watchable_when_long_space_is_constrained():
    engines = {
        "E1": {
            "direction": "UP",
            "finding": "MARKET_STATE=RANGE; PRESSURE=UP",
        },
        "E2": {
            "direction": "UP",
            "finding": "UP opportunity is developing based on closed-candle evidence.",
            "opportunity_maturity": "DEVELOPING",
            "state": "DEVELOPING",
            "reasons": "AUCTION_CONFIRMATION_PENDING; AUCTION_ACCEPTANCE_NOT_PROVEN",
        },
        "E3": {
            "direction": "UP",
            "structure_direction": "UP",
            "finding": "BULLISH_STRUCTURE",
        },
        "E4": {
            "event": "HIGH_LIQUIDITY_INTERACTION",
            "auction_state": "PENDING",
            "liquidity_taker": "BUYERS",
            "response_actor": "UNCLEAR",
        },
        "E5": {
            "finding": "FAVORABLE_LOCATION",
            "available_space_atr_long": 0.96,
            "reasons": "LONG_SPACE_CONSTRAINED; EXTENSION_RISK",
        },
        "E6": {
            "setup": "NO_SETUP",
            "reasons": "E6_CAUSAL_SETUP_PROOF",
        },
    }

    result = reconcile_causal_evidence(engines)

    assert result["state"] == "OPPORTUNITY_WATCH"
    assert result["direction"] == "BUY"
    assert result["ready"] is False
    assert "SPACE_CONSTRAINT_TRACKED_NOT_OPPORTUNITY_INVALIDATION" in result["evidence"]
    assert "SUFFICIENT_STRUCTURAL_SPACE" in result["wait_for"]
    assert "E2_OPPORTUNITY_CONFIRMATION" in result["wait_for"]
