from production_v2.professional_surgery import enrich_professional_opportunity


def test_e1_exposes_directional_opportunity_without_authorizing_trade():
    out = enrich_professional_opportunity("E1", {"state": "TREND_UP", "direction": "UP", "confidence": 0.82}, {"symbol": "BTC", "timeframe": "M5"})
    assert out["opportunity_direction"] == "BUY"
    assert out["opportunity_state"] in {"WATCH", "EMERGING", "DEVELOPING"}
    assert out["entry_authorized"] is False
    assert out["opportunity_next_event"]


def test_e4_sweep_rejection_maps_conditional_reversal_opportunity():
    out = enrich_professional_opportunity("E4", {"finding": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING", "liquidity_taker": "BUYERS", "response_actor": "SELLERS", "auction_quality": 56.04}, {"symbol": "BTC", "timeframe": "M5"})
    assert out["opportunity_direction"] == "SELL"
    assert out["opportunity_state"] == "CONDITIONAL"
    assert out["entry_authorized"] is False
    assert "reclaim" in out["opportunity_next_event"].lower()


def test_e5_premium_long_space_is_visible_as_constrained_not_hidden():
    out = enrich_professional_opportunity("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "PREMIUM", "structural_location": "AT_RESISTANCE", "available_space_atr_long": 0.40, "available_space_atr_short": 2.90}, {"symbol": "BTC", "timeframe": "M5"})
    assert out["opportunity_direction"] == "SELL"
    assert out["opportunity_state"] == "CONDITIONAL"
    assert out["opportunity_constraints"]
    assert "space" in " ".join(out["opportunity_constraints"]).lower()


def test_e9_never_converts_visibility_into_trade_authority():
    out = enrich_professional_opportunity("E9", {"decision": "NO_TRADE", "execution": "BLOCKED", "setup": "VALIDATING"}, {"symbol": "BTC", "timeframe": "M5"})
    assert out["entry_authorized"] is False
    assert out["trade_authorized"] is False
    assert out["opportunity_state"] in {"WATCH", "CONDITIONAL", "BLOCKED"}
