from production_v2.e2_opportunity_surgery import enrich_directional_opportunity_book


def test_e2_preserves_primary_and_counter_directional_opportunities():
    result = enrich_directional_opportunity_book(
        {"direction": "UP", "opportunity_score": 72.0},
        candle="C3",
        buy_score=0.72,
        sell_score=0.48,
    )

    assert result["opportunity_book"]["competition"] == "CONTESTED"
    assert result["opportunity_book"]["leader"] == "BUY"
    assert {c["direction"] for c in result["opportunity_book"]["candidates"]} == {"BUY", "SELL"}
    assert result["direction"] == "UP"
    assert result["opportunity_direction"] == "UP"


def test_e2_does_not_convert_counter_opportunity_into_trade_signal():
    result = enrich_directional_opportunity_book(
        {"direction": "DOWN", "opportunity_score": 61.0},
        candle="C4",
        buy_score=0.44,
        sell_score=0.61,
    )

    assert result["opportunity_book"]["leader"] == "SELL"
    assert result["opportunity_book"]["competition"] == "CONTESTED"
    assert result["entry"] is None
    assert result["trigger"] is None
    assert result["decision"] is None
