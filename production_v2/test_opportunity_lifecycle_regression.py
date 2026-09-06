from production_v2.opportunity_lifecycle import advance_opportunity_directions


def test_counter_direction_watch_survives_leader_switch():
    previous = {"opportunities": {"BUY": {"opportunity_id": "BUY|DIRECTIONAL_WATCH|a", "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "state": "WATCHING", "event_id": "a", "origin_event_id": "a", "origin_candle": "c1", "last_evaluated_candle": "c1", "bars_waited": 1}, "SELL": {"opportunity_id": "SELL|DIRECTIONAL_WATCH|b", "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "state": "WATCHING", "event_id": "b", "origin_event_id": "b", "origin_candle": "c1", "last_evaluated_candle": "c1", "bars_waited": 1}}}
    current = {"BUY": {"candidate": False, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "candle": "c2"}, "SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "event_id": "c2|SELL_WATCH", "candle": "c2", "wait_for": ["SELL_CONFIRMATION"]}}
    result = advance_opportunity_directions(previous, current, leader="SELL", competition="CONTESTED")
    assert result["leader"] == "SELL"
    assert result["active_directions"] == ["BUY", "SELL"]
    assert result["opportunities"]["BUY"]["opportunity_id"] == "BUY|DIRECTIONAL_WATCH|a"
    assert result["opportunities"]["BUY"]["origin_event_id"] == "a"
    assert result["opportunities"]["SELL"]["opportunity_id"] == "SELL|DIRECTIONAL_WATCH|b"
    assert result["trade_authorized"] is False


def test_counter_direction_without_event_does_not_inherit_e4_event():
    previous = {"opportunities": {}}
    current = {"BUY": {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "candle": "c2"}, "SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "event_id": "e4-sell", "candle": "c2"}}
    result = advance_opportunity_directions(previous, current, leader="SELL", competition="CONTESTED")
    assert result["opportunities"]["BUY"]["event_id"] in (None, "")
    assert result["opportunities"]["BUY"]["origin_event_id"] in (None, "")
    assert result["opportunities"]["SELL"]["event_id"] == "e4-sell"


def test_watch_ages_only_on_new_candle_and_expires_at_limit():
    previous = {"opportunities": {"SELL": {"opportunity_id": "SELL|DIRECTIONAL_WATCH", "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "state": "WATCHING", "origin_candle": "c1", "last_evaluated_candle": "c1", "bars_waited": 4}}}
    same = {"SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candle": "c1"}}
    same_result = advance_opportunity_directions(previous, same, leader="SELL")
    assert same_result["opportunities"]["SELL"]["bars_waited"] == 4
    next_result = advance_opportunity_directions(previous, {"SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candle": "c5"}}, leader="SELL")
    assert next_result["opportunities"]["SELL"]["bars_waited"] == 5
    expired = advance_opportunity_directions(next_result, {"SELL": {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "candle": "c6"}}, leader="SELL")
    assert expired["opportunities"]["SELL"]["state"] == "EXPIRED"
    assert expired["opportunities"]["SELL"]["invalidation_reason"] == "WATCH_MAX_AGE_REACHED"
