from production_v2.pipeline import _build_causal_event_anchor


def test_e4_anchor_survives_missing_e2_candidate_and_e6_rewording():
    previous = {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|event-A",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "state": "WATCHING",
        "bars_waited": 1,
        "last_evaluated_candle": "2026-09-06T16:40:00Z",
        "event_id": "event-A",
        "origin_event_id": "event-A",
    }
    e4 = {
        "event_id": "event-A",
        "event_candle_id": "2026-09-06T16:35:00Z",
        "auction_state": "PENDING",
        "event": "HIGH_FAILED_BREAK_RECLAIM",
    }
    result = _build_causal_event_anchor(e4, previous, "2026-09-06T16:45:00Z")
    assert result["event_id"] == "event-A"
    assert result["origin_event_id"] == "event-A"
    assert result["event_candle"] == "2026-09-06T16:35:00Z"
    assert result["age_bars"] == 2


def test_new_e4_event_is_not_hidden_by_previous_opportunity():
    previous = {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|event-A",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "state": "WATCHING",
        "bars_waited": 2,
        "last_evaluated_candle": "2026-09-06T16:45:00Z",
        "event_id": "event-A",
        "origin_event_id": "event-A",
    }
    e4 = {
        "event_id": "event-B",
        "event_candle_id": "2026-09-06T16:50:00Z",
        "auction_state": "PENDING",
        "event": "LOW_FAILED_BREAK_RECLAIM",
    }
    result = _build_causal_event_anchor(e4, previous, "2026-09-06T16:50:00Z")
    assert result["event_id"] == "event-B"
    assert result["origin_event_id"] == "event-B"
    assert result["event_candle"] == "2026-09-06T16:50:00Z"
    assert result["age_bars"] == 0
