from production_v2.opportunity_lifecycle import advance_opportunity


def test_active_thesis_without_new_candidate_is_preserved():
    previous = {
        "state": "WAITING",
        "continuity": "NEW_OPPORTUNITY_WATCH",
        "opportunity_id": "SELL|LIQUIDITY_REVERSAL",
        "direction": "SELL",
        "setup": "LIQUIDITY_REVERSAL",
        "bars_waited": 0,
        "origin_candle": "2026-09-02T10:00:00Z",
    }
    current = {
        "candidate": False,
        "ready": False,
        "invalidated": False,
        "executed": False,
        "direction": "SELL",
        "setup": "LIQUIDITY_REVERSAL",
        "thesis_status": "FORMING",
        "candle": "2026-09-02T10:05:00Z",
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "WAITING"
    assert result["opportunity_id"] == "SELL|LIQUIDITY_REVERSAL"
    assert result["bars_waited"] == 1
    assert result["continuity"] == "CONTINUING_EXISTING_OPPORTUNITY"


def test_explicit_invalidation_still_ends_previous_thesis():
    previous = {
        "state": "WAITING",
        "opportunity_id": "BUY|AUCTION_ACCEPTANCE_CONTINUATION",
        "direction": "BUY",
        "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
        "bars_waited": 1,
    }
    current = {
        "candidate": False,
        "ready": False,
        "invalidated": True,
        "executed": False,
        "direction": "BUY",
        "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
        "thesis_status": "INVALIDATED",
        "candle": "2026-09-02T10:10:00Z",
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "INVALIDATED"
    assert result["trade_authorized"] is False
