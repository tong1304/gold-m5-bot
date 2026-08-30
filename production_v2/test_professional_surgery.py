from production_v2.professional_surgery import enrich_professional_opportunity


def test_e1_exposes_directional_opportunity_without_authorizing_trade():
    out = enrich_professional_opportunity("E1", {"state": "TREND_UP", "direction": "UP", "confidence": 0.82}, {"symbol": "BTC", "timeframe": "M5"})
    op = out["professional_surgery"]
    assert op["direction"] == "BUY"
    assert op["state"] in {"WATCH", "EMERGING", "DEVELOPING"}
    assert op["entry_authorized"] is False
    assert op["next_required_event"]


def test_e4_sweep_rejection_maps_conditional_reversal_opportunity():
    out = enrich_professional_opportunity("E4", {"finding": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING", "liquidity_taker": "BUYERS", "response_actor": "SELLERS", "auction_quality": 56.04}, {"symbol": "BTC", "timeframe": "M5"})
    op = out["professional_surgery"]
    assert op["direction"] == "SELL"
    assert op["state"] == "CONDITIONAL"
    assert op["entry_authorized"] is False
    assert "reclaim" in op["next_required_event"].lower()


def test_e5_premium_long_space_is_visible_as_constrained_not_hidden():
    out = enrich_professional_opportunity("E5", {"finding": "FAVORABLE_LOCATION", "value_state": "PREMIUM", "structural_location": "AT_RESISTANCE", "available_space_atr_long": 0.40, "available_space_atr_short": 2.90}, {"symbol": "BTC", "timeframe": "M5"})
    op = out["professional_surgery"]
    assert op["direction"] == "SELL"
    assert op["state"] == "CONDITIONAL"
    assert op["constraints"]
    assert "space" in " ".join(op["constraints"]).lower()


def test_e9_never_converts_visibility_into_trade_authority():
    out = enrich_professional_opportunity("E9", {"decision": "NO_TRADE", "execution": "BLOCKED", "setup": "VALIDATING"}, {"symbol": "BTC", "timeframe": "M5"})
    op = out["professional_surgery"]
    assert op["entry_authorized"] is False
    assert op["trade_authorized"] is False
    assert op["state"] in {"WATCH", "CONDITIONAL", "BLOCKED"}
