from production_v2.opportunity_lifecycle import advance_lifecycle


def test_pending_watch_promotes_without_losing_causal_identity():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|event-1",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "event-1",
        "origin_event_id": "event-1",
        "bars_waited": 1,
        "origin_candle": "2026-09-06T12:05:00Z",
        "last_evaluated_candle": "2026-09-06T12:10:00Z",
    }
    current = {
        "candidate": True,
        "thesis_proven": True,
        "ready": False,
        "direction": "SELL",
        "setup": "LIQUIDITY_RESPONSE",
        "event_id": "event-1",
        "origin_event_id": "event-1",
        "candle": "2026-09-06T12:15:00Z",
        "wait_for": ["E7_CONFIRMATION"],
    }
    result = advance_lifecycle(previous, current)
    assert result["state"] == "WAITING"
    assert result["opportunity_phase"] == "TRIGGER_PENDING"
    assert result["opportunity_id"] == previous["opportunity_id"]
    assert result["bars_waited"] == 2


def test_pending_watch_expires_only_after_max_age():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|event-2",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "event-2",
        "bars_waited": 4,
        "last_evaluated_candle": "2026-09-06T12:25:00Z",
    }
    current = {
        "candidate": True,
        "thesis_proven": False,
        "ready": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "event-2",
        "candle": "2026-09-06T12:30:00Z",
    }
    result = advance_lifecycle(previous, current)
    assert result["state"] == "EXPIRED"
    assert result["opportunity_phase"] == "EXPIRED"
    assert result["bars_waited"] == 5
