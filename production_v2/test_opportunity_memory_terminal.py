from production_v2.missed_opportunity import measure_terminal_opportunity
from production_v2.opportunity_memory import append_terminal_outcome


def _sell_opportunity():
    return {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|origin-1",
        "direction": "SELL",
        "state": "WATCHING",
        "thesis_proven": True,
        "entry": 100.0,
        "stop_loss": 102.0,
        "origin_candle": "2026-09-06T16:00:00Z",
    }


def test_terminal_measurement_uses_previous_opportunity_and_closed_followup_only():
    previous = _sell_opportunity()
    current = {
        "state": "REPLACED",
        "opportunity_id": "BUY|OPPORTUNITY_WATCH|new-event",
        "direction": "BUY",
        "last_evaluated_candle": "2026-09-06T16:10:00Z",
    }
    bars = [
        {"timestamp": "2026-09-06T16:05:00Z", "high": 100.4, "low": 99.0},
        {"timestamp": "2026-09-06T16:10:00Z", "high": 100.2, "low": 98.8},
    ]
    result = measure_terminal_opportunity(previous, current, bars)
    assert result["opportunity_id"] == previous["opportunity_id"]
    assert result["direction"] == "SELL"
    assert result["terminal_state"] == "REPLACED"
    assert result["classification"] == "MISSED_GOOD_TRADE"
    assert result["favorable_r"] == 0.6


def test_append_terminal_outcome_is_idempotent_and_keeps_both_direction_histories():
    state = {
        "opportunities": {
            "BUY": {"opportunity_id": "BUY|WATCH|1", "state": "WATCHING"},
            "SELL": {"opportunity_id": "SELL|WATCH|2", "state": "REPLACED"},
        }
    }
    outcome = {
        "opportunity_id": "SELL|WATCH|2",
        "direction": "SELL",
        "terminal_state": "REPLACED",
        "terminal_candle": "2026-09-06T16:10:00Z",
        "classification": "GOOD_WAIT",
        "measured": True,
    }
    changed, updated = append_terminal_outcome(state, outcome)
    assert changed is True
    assert updated["missed_opportunity_outcomes"] == [outcome]
    changed_again, updated_again = append_terminal_outcome(updated, outcome)
    assert changed_again is False
    assert updated_again["missed_opportunity_outcomes"] == [outcome]
    assert updated_again["opportunities"]["BUY"]["opportunity_id"] == "BUY|WATCH|1"
