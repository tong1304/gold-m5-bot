from production_v2.opportunity_lifecycle import advance_opportunity


def test_waiting_opportunity_continues_on_next_closed_candle():
    previous = {
        "state": "WAITING",
        "opportunity_id": "SELL|TREND_PULLBACK",
        "direction": "SELL",
        "setup": "TREND_PULLBACK",
        "bars_waited": 0,
        "origin_candle": "2026-09-02T09:45:00Z",
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "setup": "TREND_PULLBACK",
        "ready": False,
        "invalidated": False,
        "candle": "2026-09-02T09:50:00Z",
    }

    lifecycle = advance_opportunity(previous, current)

    assert lifecycle["state"] == "WAITING"
    assert lifecycle["continuity"] == "CONTINUING_EXISTING_OPPORTUNITY"
    assert lifecycle["bars_waited"] == 1
    assert lifecycle["opportunity_id"] == previous["opportunity_id"]
    assert lifecycle["last_evaluated_candle"] == current["candle"]


def test_waiting_opportunity_becomes_ready_when_all_proof_is_complete():
    previous = {
        "state": "WAITING",
        "opportunity_id": "BUY|BREAKOUT",
        "direction": "BUY",
        "setup": "BREAKOUT",
        "bars_waited": 2,
        "origin_candle": "2026-09-02T09:40:00Z",
    }
    current = {
        "candidate": True,
        "direction": "BUY",
        "setup": "BREAKOUT",
        "ready": True,
        "invalidated": False,
        "candle": "2026-09-02T09:55:00Z",
    }

    lifecycle = advance_opportunity(previous, current)

    assert lifecycle["state"] == "READY"
    assert lifecycle["continuity"] == "ADVANCING_EXISTING_OPPORTUNITY"
    assert lifecycle["bars_waited"] == 3


def test_waiting_opportunity_is_invalidated_when_direction_changes():
    previous = {
        "state": "WAITING",
        "opportunity_id": "SELL|LIQUIDITY_REVERSAL",
        "direction": "SELL",
        "setup": "LIQUIDITY_REVERSAL",
        "bars_waited": 1,
        "origin_candle": "2026-09-02T09:45:00Z",
    }
    current = {
        "candidate": True,
        "direction": "BUY",
        "setup": "LIQUIDITY_REVERSAL",
        "ready": False,
        "invalidated": False,
        "candle": "2026-09-02T09:50:00Z",
    }

    lifecycle = advance_opportunity(previous, current)

    assert lifecycle["state"] == "INVALIDATED"
    assert lifecycle["continuity"] == "OPPORTUNITY_INVALIDATED"
    assert lifecycle["invalidation_reason"] == "DIRECTION_CHANGED"


def test_new_candidate_starts_waiting_without_forcing_trade():
    lifecycle = advance_opportunity(
        None,
        {
            "candidate": True,
            "direction": "BUY",
            "setup": "TREND_PULLBACK",
            "ready": False,
            "invalidated": False,
            "candle": "2026-09-02T10:00:00Z",
        },
    )

    assert lifecycle["state"] == "WAITING"
    assert lifecycle["continuity"] == "NEW_OPPORTUNITY_WATCH"
    assert lifecycle["bars_waited"] == 0
    assert lifecycle["trade_authorized"] is False
