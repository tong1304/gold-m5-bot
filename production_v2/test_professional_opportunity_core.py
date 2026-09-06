from production_v2.professional_opportunity import enrich_engine


def test_opportunity_intelligence_separates_quality_from_execution_and_tracks_strength():
    out = enrich_engine(
        "E6",
        {
            "direction": "BUY",
            "confidence": 0.82,
            "counter_evidence": ["AUCTION_CONFIRMATION_PENDING"],
            "setup": "LIQUIDITY_REVERSAL",
            "finding": "BUY opportunity is setup validating",
        },
    )
    op = out["professional_opportunity"]
    assert 0 <= op["opportunity_strength"] <= 100
    assert op["state"] == "OPPORTUNITY_WAITING"
    assert op["execution_quality"] == "NOT_READY"
    assert op["trade_authorized"] is False
    assert op["conditional_thesis"]
    assert op["wait_for"]


def test_e2_keeps_both_directional_opportunities_visible_when_market_bias_is_neutral():
    out = enrich_engine(
        "E2",
        {
            "direction": "NEUTRAL",
            "opportunity_direction": "NEUTRAL",
            "opportunity_book": {
                "leader": "BUY",
                "competition": "CONTESTED",
                "candidates": [
                    {"direction": "BUY", "quality": 0.72, "state": "DEVELOPING", "wait_for": ["BUY_CONFIRMATION"]},
                    {"direction": "SELL", "quality": 0.61, "state": "DEVELOPING", "wait_for": ["SELL_CONFIRMATION"]},
                ],
            },
            "confidence": 0.65,
            "reasons": ["AUCTION_ACCEPTANCE_NOT_PROVEN"],
        },
    )
    op = out["professional_opportunity"]
    assert op["direction"] == "BUY"
    assert op["competition"] == "CONTESTED"
    assert set(op["directional_opportunities"]) == {"BUY", "SELL"}
    assert op["directional_opportunities"]["SELL"]["state"] == "DEVELOPING"
    assert op["trade_authorized"] is False


def test_e5_exposes_directional_price_geometry_without_authorizing_trade():
    out = enrich_engine(
        "E5",
        {
            "direction": "NEUTRAL",
            "value_state": "DISCOUNT",
            "value_response": "ACCEPTED_BELOW_VALUE",
            "long_location_score": 0.68,
            "short_location_score": 0.41,
            "available_space_atr_long": 2.4,
            "available_space_atr_short": 1.1,
            "next_support": 79480.0,
            "next_resistance": 79620.0,
            "price": 79545.0,
        },
    )
    geometry = out["professional_opportunity"]["price_geometry"]
    assert geometry["BUY"]["available_space_atr"] == 2.4
    assert geometry["SELL"]["available_space_atr"] == 1.1
    assert geometry["BUY"]["target_reference"] == 79620.0
    assert geometry["SELL"]["target_reference"] == 79480.0
    assert out["professional_opportunity"]["trade_authorized"] is False


def test_strength_decay_marks_deteriorating_opportunity_without_killing_it():
    previous = {"opportunity_strength": 78}
    current = {
        "direction": "BUY",
        "confidence": 0.58,
        "opportunity_score": 55,
        "counter_evidence": ["STRUCTURE_CONFLICT", "FOLLOW_THROUGH_PENDING"],
    }
    prev = enrich_engine("E6", {"direction": "BUY", "confidence": 0.80})["professional_opportunity"]
    cur = enrich_engine("E6", current, {"previous_opportunity": previous})["professional_opportunity"]
    assert cur["opportunity_strength"] < prev["opportunity_strength"]
    assert cur["strength_trend"] == "DECAYING"
    assert cur["state_preservation"] == "OPPORTUNITY_ALIVE_UNLESS_EXPLICITLY_INVALIDATED"
