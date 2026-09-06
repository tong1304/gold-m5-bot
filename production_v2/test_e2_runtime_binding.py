from production_v2 import e2_brain
from production_v2.e2_runtime_binding import install


def test_e2_runtime_binding_attaches_directional_book_without_execution_side_effects(monkeypatch):
    base = {
        "direction": "UP",
        "opportunity_direction": "UP",
        "buy_confirmation_required": ["BUY_CONFIRMATION"],
        "sell_confirmation_required": ["SELL_CONFIRMATION"],
    }

    monkeypatch.setattr(e2_brain, "analyze_e2", lambda snapshot: dict(base))
    install(type("Pipeline", (), {})(), e2_brain)
    output = e2_brain.analyze_e2({"bars": [], "candle": {"timestamp": "2026-09-06T13:10:00Z"}})

    assert {x["direction"] for x in output["opportunity_book"]["candidates"]} == {"BUY", "SELL"}
    assert output["opportunity_competition"] == "CONTESTED"
    assert output["entry"] is None if "entry" in output else True
    assert output["trigger"] is None if "trigger" in output else True
    assert output["decision"] is None if "decision" in output else True
