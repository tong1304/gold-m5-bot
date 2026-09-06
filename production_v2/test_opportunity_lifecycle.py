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
    assert lifecycle["continuity"] == "DIRECTION_CHANGED"
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


def test_watching_opportunity_promotes_to_waiting_only_when_real_setup_appears():
    previous = {"state":"WATCHING","opportunity_id":"BUY|OPPORTUNITY_WATCH","direction":"BUY","setup":"OPPORTUNITY_WATCH","bars_waited":1,"origin_candle":"2026-09-03T00:15:00Z"}
    current = {"candidate":True,"direction":"BUY","setup":"TREND_PULLBACK","ready":False,"invalidated":False,"thesis_status":"FORMING","upstream_evidence":["E6_CAUSAL_SETUP_PROOF"],"candle":"2026-09-03T00:20:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WAITING"
    assert lifecycle["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert lifecycle["bars_waited"] == 2
    assert lifecycle["opportunity_id"] == "BUY|TREND_PULLBACK"
    assert lifecycle["trade_authorized"] is False


def test_pending_upstream_event_does_not_become_invalidated_just_because_e6_is_not_yet_proven():
    previous = {"state":"WATCHING","opportunity_id":"SELL|HIGH_FAILED_BREAK_RECLAIM","direction":"SELL","setup":"HIGH_FAILED_BREAK_RECLAIM","bars_waited":0,"origin_candle":"2026-09-04T13:35:00Z"}
    current = {"causal_opportunity":False,"candidate":False,"direction":"SELL","setup":"HIGH_FAILED_BREAK_RECLAIM","invalidated":False,"candle":"2026-09-04T13:40:00Z"}
    lifecycle = advance_lifecycle(previous, current, bar_id="2026-09-04T13:40:00Z")
    assert lifecycle["lifecycle_state"] == "OPPORTUNITY_WATCH"
    assert lifecycle["wait_for"] == "CAUSAL_FOLLOW_THROUGH_OR_INVALIDATION"
    assert lifecycle["age_bars"] == 1


def test_active_opportunity_is_idempotent_when_same_closed_candle_is_evaluated_twice():
    previous = {"state":"WATCHING","opportunity_id":"SELL|OPPORTUNITY_WATCH","direction":"SELL","setup":"OPPORTUNITY_WATCH","bars_waited":1,"origin_candle":"2026-09-05T23:20:00Z","last_evaluated_candle":"2026-09-05T23:25:00Z"}
    current = {"candidate":True,"direction":"SELL","setup":"OPPORTUNITY_WATCH","ready":False,"invalidated":False,"candle":"2026-09-05T23:25:00Z"}
    lifecycle = advance_opportunity(previous, current)
    assert lifecycle["state"] == "WATCHING"
    assert lifecycle["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert lifecycle["bars_waited"] == 1
    assert lifecycle["last_evaluated_candle"] == current["candle"]
