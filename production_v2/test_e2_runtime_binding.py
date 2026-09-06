from types import SimpleNamespace

from production_v2.e2_runtime_binding import install


def test_e2_runtime_binding_attaches_directional_book_without_execution_side_effects():
    base = {
        "direction": "UP",
        "opportunity_direction": "UP",
        "buy_confirmation_required": ["BUY_CONFIRMATION"],
        "sell_confirmation_required": ["SELL_CONFIRMATION"],
        "market_tree": {"directional_evidence": {"up": 5, "down": 5}},
    }
    pipeline = SimpleNamespace(analyze_e2=lambda snapshot: dict(base))
    e2 = SimpleNamespace(analyze_e2=pipeline.analyze_e2)

    install(pipeline, e2)
    output = pipeline.analyze_e2({"candle": {"timestamp": "2026-09-06T13:10:00Z"}})

    assert {x["direction"] for x in output["opportunity_book"]["candidates"]} == {"BUY", "SELL"}
    assert output["opportunity_competition"] == "CONTESTED"
    assert output.get("entry") is None
    assert output.get("trigger") is None
    assert output.get("decision") is None
