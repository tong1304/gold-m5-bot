from types import SimpleNamespace

from production_v2.terminal_opportunity_runtime import install


def test_terminal_transition_is_measured_once_and_preserves_counter_direction():
    module = SimpleNamespace()

    def advance(previous, current_by_direction, *, leader="NEUTRAL", competition="UNCONTESTED"):
        return {
            "opportunities": {
                "BUY": previous.get("opportunities", {}).get("BUY", {"state": "WATCHING", "direction": "BUY", "opportunity_id": "BUY|WATCH|1"}),
                "SELL": {
                    "state": "REPLACED",
                    "direction": "SELL",
                    "opportunity_id": "SELL|WATCH|1",
                    "terminal_candle": "2026-09-06T16:10:00Z",
                },
            },
            "leader": leader,
            "competition": competition,
        }

    module.advance_opportunity_directions = advance
    install(module)

    previous = {
        "opportunities": {
            "BUY": {"state": "WATCHING", "direction": "BUY", "opportunity_id": "BUY|WATCH|1"},
            "SELL": {
                "state": "WATCHING",
                "direction": "SELL",
                "opportunity_id": "SELL|WATCH|1",
                "thesis_proven": True,
                "entry": 100.0,
                "stop_loss": 102.0,
                "origin_candle": "2026-09-06T16:00:00Z",
            },
        }
    }
    current = {
        "BUY": {"candidate": True, "direction": "BUY"},
        "SELL": {
            "candidate": False,
            "direction": "SELL",
            "closed_followup_bars": [
                {"timestamp": "2026-09-06T16:05:00Z", "high": 100.4, "low": 99.0},
                {"timestamp": "2026-09-06T16:10:00Z", "high": 100.2, "low": 98.8},
            ],
        },
    }
    result = module.advance_opportunity_directions(previous, current)
    assert result["missed_opportunity_count"] == 1
    assert result["missed_opportunity_measurement"]["opportunity_id"] == "SELL|WATCH|1"
    assert result["missed_opportunity_measurement"]["classification"] == "MISSED_GOOD_TRADE"
    assert result["opportunities"]["BUY"]["opportunity_id"] == "BUY|WATCH|1"

    second = module.advance_opportunity_directions(result, current)
    assert second["missed_opportunity_count"] == 1
