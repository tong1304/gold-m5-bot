from production_v2.opportunity_lifecycle_progression import advance_lifecycle_stage


def test_watch_promotes_to_highest_proven_stage_without_artificial_one_stage_delay():
    previous = {
        "opportunity_id": "BUY|OPPORTUNITY_WATCH|evt-42",
        "origin_event_id": "evt-42",
        "event_id": "evt-42",
        "direction": "BUY",
        "lifecycle_stage": "WATCH",
        "state": "WATCHING",
    }
    current = {
        "candidate": True,
        "direction": "BUY",
        "setup": "LIQUIDITY_RESPONSE",
        "event_id": "evt-42",
        "origin_event_id": "evt-42",
        "candle": "2026-09-07T08:50:00Z",
        "confirmed": True,
        "e4_state": "CONFIRMED",
        "thesis_proven": True,
        "e7_confirmed": True,
        "e7_confirmation_state": "TRIGGER_CONFIRMED",
        "e8_ready": True,
        "e8_economic_state": "RISK_READY",
        "e9_trade": True,
    }

    progressed = advance_lifecycle_stage(previous, current)

    assert progressed["lifecycle_stage"] == "TRADE"
    assert progressed["trade_authorized"] is True
    assert progressed["opportunity_id"] == "BUY|OPPORTUNITY_WATCH|evt-42"
    assert progressed["event_id"] == "evt-42"
    assert progressed["origin_event_id"] == "evt-42"
    assert progressed["stage_history"][-1]["stage"] == "TRADE"


def test_watch_promotes_directly_to_e7_when_e6_and_e7_are_proven_but_e8_is_not_ready():
    previous = {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|evt-43",
        "origin_event_id": "evt-43",
        "event_id": "evt-43",
        "direction": "SELL",
        "lifecycle_stage": "WATCH",
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "setup": "LIQUIDITY_RESPONSE",
        "event_id": "evt-43",
        "origin_event_id": "evt-43",
        "candle": "2026-09-07T08:55:00Z",
        "e4_state": "CONFIRMED",
        "thesis_proven": True,
        "e7_confirmed": True,
        "e7_confirmation_state": "TRIGGER_CONFIRMED",
        "e8_ready": False,
        "e9_trade": False,
    }

    progressed = advance_lifecycle_stage(previous, current)

    assert progressed["lifecycle_stage"] == "E7_CONFIRMED"
    assert progressed["trade_authorized"] is False
    assert progressed["wait_for_stage"] == "E8_READY"
