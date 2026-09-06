from production_v2.opportunity_lifecycle import advance_opportunity


def test_watch_promotion_gets_new_setup_identity_and_keeps_origin():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 1,
        "origin_candle": "2026-09-06T00:00:00Z",
        "last_evaluated_candle": "2026-09-06T00:05:00Z",
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "setup": "LIQUIDITY_REVERSAL",
        "ready": False,
        "invalidated": False,
        "candle": "2026-09-06T00:10:00Z",
    }
    result = advance_opportunity(previous, current)
    assert result["state"] == "WAITING"
    assert result["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert result["opportunity_id"] == "SELL|LIQUIDITY_REVERSAL"
    assert result["bars_waited"] == 2
    assert result["origin_candle"] == previous["origin_candle"]
    assert result["trade_authorized"] is False


def test_same_closed_candle_is_idempotent_for_watch_age():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 1,
        "origin_candle": "2026-09-06T00:00:00Z",
        "last_evaluated_candle": "2026-09-06T00:10:00Z",
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "ready": False,
        "invalidated": False,
        "candle": "2026-09-06T00:10:00Z",
    }
    result = advance_opportunity(previous, current)
    assert result["state"] == "WATCHING"
    assert result["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert result["bars_waited"] == 1
    assert result["opportunity_id"] == previous["opportunity_id"]


def test_watch_is_preserved_when_candidate_disappears_without_invalidation():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 1,
        "origin_candle": "2026-09-06T00:00:00Z",
        "last_evaluated_candle": "2026-09-06T00:05:00Z",
    }
    current = {
        "candidate": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "ready": False,
        "invalidated": False,
        "candle": "2026-09-06T00:10:00Z",
    }
    result = advance_opportunity(previous, current)
    assert result["state"] == "WATCHING"
    assert result["continuity"] == "PRESERVING_PENDING_OPPORTUNITY"
    assert result["bars_waited"] == 2
    assert result["trade_authorized"] is False


def test_watch_expires_after_maximum_age_not_before():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 5,
        "origin_candle": "2026-09-06T00:00:00Z",
        "last_evaluated_candle": "2026-09-06T00:25:00Z",
    }
    current = {
        "candidate": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "ready": False,
        "invalidated": False,
        "candle": "2026-09-06T00:30:00Z",
    }
    result = advance_opportunity(previous, current)
    assert result["state"] == "EXPIRED"
    assert result["bars_waited"] == 6
    assert result["trade_authorized"] is False
