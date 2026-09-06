from production_v2.opportunity_lifecycle import advance_opportunity_directions


def test_counter_direction_watch_survives_leader_switch():
    previous = {
        "opportunities": {
            "BUY": {
                "opportunity_id": "BUY|DIRECTIONAL_WATCH|a",
                "direction": "BUY",
                "setup": "OPPORTUNITY_WATCH",
                "state": "WATCHING",
                "event_id": "a",
                "origin_event_id": "a",
                "origin_candle": "c1",
                "last_evaluated_candle": "c1",
                "bars_waited": 1,
            },
            "SELL": {
                "opportunity_id": "SELL|DIRECTIONAL_WATCH|b",
                "direction": "SELL",
                "setup": "OPPORTUNITY_WATCH",
                "state": "WATCHING",
                "event_id": "b",
                "origin_event_id": "b",
                "origin_candle": "c1",
                "last_evaluated_candle": "c1",
                "bars_waited": 1,
            },
        }
    }
    current = {
        "BUY": {"candidate": False, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "candle": "c2"},
        "SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "event_id": "c2|SELL_WATCH", "candle": "c2", "wait_for": ["SELL_CONFIRMATION"]},
    }

    result = advance_opportunity_directions(previous, current, leader="SELL", competition="CONTESTED")

    assert result["leader"] == "SELL"
    assert result["active_directions"] == ["BUY", "SELL"]
    assert result["opportunities"]["BUY"]["state"] in {"WATCHING", "WAITING", "READY"}
    assert result["opportunities"]["BUY"]["opportunity_id"] == "BUY|DIRECTIONAL_WATCH|a"
    assert result["opportunities"]["BUY"]["origin_event_id"] == "a"
    assert result["opportunities"]["SELL"]["opportunity_id"] == "SELL|DIRECTIONAL_WATCH|b"
    assert result["trade_authorized"] is False
