from production_v2.opportunity_lifecycle import advance_opportunity, advance_lifecycle


def test_waiting_opportunity_continues_on_next_closed_candle():
    previous = {"state":"WAITING","opportunity_id":"SELL|TREND_PULLBACK","direction":"SELL","setup":"TREND_PULLBACK","bars_waited":0,"origin_candle":"2026-09-02T09:45:00Z"}
    current = {"candidate":True,"direction":"SELL","setup":"TREND_PULLBACK","ready":False,"invalidated":False,"candle":"2026-09-02T09:50:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WAITING"
    assert lifecycle["continuity"] == "CONTINUING_EXISTING_OPPORTUNITY"
    assert lifecycle["bars_waited"] == 1
    assert lifecycle["opportunity_id"] == previous["opportunity_id"]
    assert lifecycle["last_evaluated_candle"] == current["candle"]


def test_waiting_opportunity_becomes_ready_when_all_proof_is_complete():
    previous = {"state":"WAITING","opportunity_id":"BUY|BREAKOUT","direction":"BUY","setup":"BREAKOUT","bars_waited":2,"origin_candle":"2026-09-02T09:40:00Z"}
    current = {"candidate":True,"direction":"BUY","setup":"BREAKOUT","ready":True,"invalidated":False,"candle":"2026-09-02T09:55:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "READY"
    assert lifecycle["continuity"] == "ADVANCING_EXISTING_OPPORTUNITY"
    assert lifecycle["bars_waited"] == 3


def test_waiting_opportunity_is_replaced_when_direction_changes():
    previous = {"state":"WAITING","opportunity_id":"SELL|LIQUIDITY_REVERSAL","direction":"SELL","setup":"LIQUIDITY_REVERSAL","bars_waited":1,"origin_candle":"2026-09-02T09:45:00Z"}
    current = {"candidate":True,"direction":"BUY","setup":"LIQUIDITY_REVERSAL","ready":False,"invalidated":False,"candle":"2026-09-02T09:50:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "REPLACED"
    assert lifecycle["continuity"] == "DIRECTION_CHANGED_REPLACED_OPPORTUNITY"
    assert lifecycle["invalidation_reason"] == "DIRECTION_CHANGED"
    assert lifecycle["previous_opportunity_id"] == previous["opportunity_id"]


def test_new_candidate_starts_waiting_without_forcing_trade():
    lifecycle = advance_opportunity(None, {"candidate":True,"direction":"BUY","setup":"TREND_PULLBACK","ready":False,"invalidated":False,"candle":"2026-09-02T10:00:00Z"})
    assert lifecycle["state"] == "WAITING"
    assert lifecycle["continuity"] == "NEW_OPPORTUNITY_WATCH"
    assert lifecycle["bars_waited"] == 0
    assert lifecycle["trade_authorized"] is False


def test_watching_opportunity_stays_watching_on_next_candle_with_upstream_evidence():
    previous = {"state":"WATCHING","opportunity_id":"BUY|OPPORTUNITY_WATCH","direction":"BUY","setup":"OPPORTUNITY_WATCH","bars_waited":0,"origin_candle":"2026-09-03T00:15:00Z"}
    current = {"candidate":True,"direction":"BUY","setup":"OPPORTUNITY_WATCH","ready":False,"invalidated":False,"thesis_status":"FORMING","upstream_evidence":["E2_OPPORTUNITY_DEVELOPING"],"candle":"2026-09-03T00:20:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WATCHING"
    assert lifecycle["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert lifecycle["bars_waited"] == 1
    assert lifecycle["opportunity_id"] == previous["opportunity_id"]
    assert lifecycle["trade_authorized"] is False


def test_watching_setup_family_does_not_promote_without_explicit_thesis_proof():
    previous = {"state":"WATCHING","opportunity_id":"BUY|OPPORTUNITY_WATCH","direction":"BUY","setup":"OPPORTUNITY_WATCH","bars_waited":1,"origin_candle":"2026-09-03T00:15:00Z"}
    current = {"candidate":True,"direction":"BUY","setup":"TREND_PULLBACK","ready":False,"thesis_proven":False,"invalidated":False,"thesis_status":"FORMING","upstream_evidence":["E6_CAUSAL_SETUP_NOT_PROVEN"],"candle":"2026-09-03T00:20:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WATCHING"
    assert lifecycle["lifecycle_state"] == "OPPORTUNITY_WATCH"
    assert lifecycle["opportunity_phase"] == "OPPORTUNITY_WATCH"
    assert lifecycle["continuity"] == "PRESERVING_PENDING_OPPORTUNITY"
    assert lifecycle["bars_waited"] == 2
    assert lifecycle["trade_authorized"] is False


def test_pending_upstream_event_does_not_become_trigger_pending_before_thesis_proof():
    previous = {"state":"WATCHING","opportunity_id":"SELL|HIGH_FAILED_BREAK_RECLAIM","direction":"SELL","setup":"HIGH_FAILED_BREAK_RECLAIM","bars_waited":0,"origin_candle":"2026-09-04T13:35:00Z"}
    current = {"causal_opportunity":False,"candidate":False,"thesis_proven":False,"direction":"SELL","setup":"HIGH_FAILED_BREAK_RECLAIM","invalidated":False,"candle":"2026-09-04T13:40:00Z"}
    lifecycle = advance_lifecycle(previous, current, bar_id="2026-09-04T13:40:00Z")
    assert lifecycle["state"] == "WATCHING"
    assert lifecycle["lifecycle_state"] == "OPPORTUNITY_WATCH"
    assert lifecycle["opportunity_phase"] == "OPPORTUNITY_WATCH"
    assert lifecycle["wait_for"] == "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"
    assert lifecycle["age_bars"] == 1
    assert lifecycle["trade_authorized"] is False


def test_pending_upstream_event_promotes_to_trigger_pending_only_after_thesis_proof():
    previous = {"state":"WATCHING","opportunity_id":"SELL|HIGH_FAILED_BREAK_RECLAIM","direction":"SELL","setup":"HIGH_FAILED_BREAK_RECLAIM","bars_waited":1,"origin_candle":"2026-09-04T13:35:00Z"}
    current = {"causal_opportunity":True,"candidate":True,"thesis_proven":True,"direction":"SELL","setup":"HIGH_FAILED_BREAK_RECLAIM","ready":False,"invalidated":False,"candle":"2026-09-04T13:45:00Z"}
    lifecycle = advance_lifecycle(previous, current, bar_id="2026-09-04T13:45:00Z")
    assert lifecycle["state"] == "WAITING"
    assert lifecycle["lifecycle_state"] == "TRIGGER_PENDING"
    assert lifecycle["opportunity_phase"] == "TRIGGER_PENDING"
    assert lifecycle["bars_waited"] == 2
    assert lifecycle["trade_authorized"] is False


def test_active_opportunity_is_idempotent_when_same_closed_candle_is_evaluated_twice():
    previous = {"state":"WATCHING","opportunity_id":"SELL|OPPORTUNITY_WATCH","direction":"SELL","setup":"OPPORTUNITY_WATCH","bars_waited":1,"origin_candle":"2026-09-05T23:20:00Z","last_evaluated_candle":"2026-09-05T23:25:00Z"}
    current = {"candidate":True,"direction":"SELL","setup":"OPPORTUNITY_WATCH","ready":False,"invalidated":False,"candle":"2026-09-05T23:25:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WATCHING"
    assert lifecycle["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert lifecycle["bars_waited"] == 1
    assert lifecycle["last_evaluated_candle"] == current["candle"]


def test_same_direction_watch_keeps_identity_when_new_related_event_arrives():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|2026-09-06T13:15:00Z|HIGH_FAILED_BREAK_RECLAIM|HIGH|79850|DOWN",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "2026-09-06T13:15:00Z|HIGH_FAILED_BREAK_RECLAIM|HIGH|79850|DOWN",
        "origin_event_id": "2026-09-06T13:15:00Z|HIGH_FAILED_BREAK_RECLAIM|HIGH|79850|DOWN",
        "bars_waited": 1,
        "origin_candle": "2026-09-06T13:15:00Z",
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "ready": False,
        "thesis_proven": False,
        "invalidated": False,
        "event_id": "2026-09-06T13:20:00Z|HIGH_FAILED_BREAK_RECLAIM|HIGH|79814.67|DOWN",
        "candle": "2026-09-06T13:25:00Z",
    }
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WATCHING"
    assert lifecycle["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert lifecycle["opportunity_id"] == previous["opportunity_id"]
    assert lifecycle["origin_event_id"] == previous["origin_event_id"]
    assert lifecycle["event_id"] == current["event_id"]
    assert lifecycle["bars_waited"] == 2
    assert lifecycle["trade_authorized"] is False
