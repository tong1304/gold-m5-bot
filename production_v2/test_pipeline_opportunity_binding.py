from production_v2.pipeline import bind_e2_opportunity_book


def test_pipeline_e2_binding_preserves_both_directional_watches_without_execution():
    output = {
        "direction": "UP",
        "opportunity_direction": "UP",
        "buy_confirmation_required": ["BUY_CONFIRMATION"],
        "sell_confirmation_required": ["SELL_CONFIRMATION"],
        "market_tree": {"directional_evidence": {"up": 5, "down": 5}},
    }

    enriched = bind_e2_opportunity_book(
        output,
        candle={"timestamp": "2026-09-06T13:10:00Z"},
        previous_book=None,
    )

    assert enriched["direction"] == "UP"
    assert enriched["counter_direction_preserved"] is True
    candidates = enriched["opportunity_book"]["candidates"]
    assert {candidate["direction"] for candidate in candidates} == {"BUY", "SELL"}
    assert enriched["opportunity_competition"] == "CONTESTED"
    assert enriched["opportunity_selection"]["selection_authority"].startswith("E6_")
    assert enriched.get("entry") is None
    assert enriched.get("trigger") is None
    assert enriched.get("decision") is None
