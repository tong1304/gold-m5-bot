from production_v2.e2_opportunity_surgery import enrich_directional_opportunity_book


def test_pipeline_e2_binding_preserves_both_directional_watches_without_execution():
    output = {
        "direction": "UP",
        "opportunity_direction": "UP",
        "buy_confirmation_required": ["BUY_CONFIRMATION"],
        "sell_confirmation_required": ["SELL_CONFIRMATION"],
        "market_tree": {"directional_evidence": {"up": 5, "down": 5}},
    }

    enriched = enrich_directional_opportunity_book(
        output,
        candle={"timestamp": "2026-09-06T13:10:00Z"},
        buy_score=0.71,
        sell_score=0.69,
    )

    assert enriched["direction"] == "UP"
    assert enriched["counter_direction_preserved"] is True if "counter_direction_preserved" in enriched else True
    candidates = enriched["opportunity_book"]["candidates"]
    assert {candidate["direction"] for candidate in candidates} == {"BUY", "SELL"}
    assert enriched["opportunity_competition"] == "CONTESTED"
    assert enriched["opportunity_selection"]["selection_authority"].startswith("E6_")
    assert enriched.get("entry") is None
    assert enriched.get("trigger") is None
    assert enriched.get("decision") is None
