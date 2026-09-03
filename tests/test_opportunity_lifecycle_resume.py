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


def test_developing_upstream_opportunity_enters_watching_without_trade_authority():
    current = {
        "candidate": True,
        "ready": False,
        "invalidated": False,
        "executed": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH_DOWN",
        "thesis_status": "FORMING",
        "upstream_evidence": ["E2_OPPORTUNITY_DEVELOPING", "E4_AUCTION_PENDING"],
        "candle": "2026-09-02T10:10:00Z",
    }

    result = advance_opportunity(None, current)

    assert result["state"] == "WATCHING"
    assert result["continuity"] == "NEW_DEVELOPING_OPPORTUNITY"
    assert result["opportunity_id"] == "SELL|OPPORTUNITY_WATCH_DOWN"
    assert result["trade_authorized"] is False


def test_watching_developing_opportunity_continues_across_candle():
    previous = {
        "state": "WATCHING",
        "continuity": "NEW_DEVELOPING_OPPORTUNITY",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH_DOWN",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH_DOWN",
        "bars_waited": 0,
        "origin_candle": "2026-09-02T10:10:00Z",
    }
    current = {
        "candidate": True,
        "ready": False,
        "invalidated": False,
        "executed": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH_DOWN",
        "thesis_status": "FORMING",
        "upstream_evidence": ["E2_OPPORTUNITY_DEVELOPING"],
        "candle": "2026-09-02T10:15:00Z",
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "WATCHING"
    assert result["bars_waited"] == 1
    assert result["continuity"] == "CONTINUING_DEVELOPING_OPPORTUNITY"
    assert result["trade_authorized"] is False


def test_watching_promotes_to_waiting_when_real_setup_is_confirmed():
    previous = {
        "state": "WATCHING",
        "continuity": "CONTINUING_DEVELOPING_OPPORTUNITY",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH_DOWN",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH_DOWN",
        "bars_waited": 1,
        "origin_candle": "2026-09-02T10:10:00Z",
    }
    current = {
        "candidate": True,
        "ready": False,
        "invalidated": False,
        "executed": False,
        "direction": "SELL",
        "setup": "LIQUIDITY_REVERSAL",
        "thesis_status": "CONFIRMED",
        "upstream_evidence": ["E6_CAUSAL_THESIS_CONFIRMED"],
        "candle": "2026-09-02T10:20:00Z",
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "WAITING"
    assert result["bars_waited"] == 2
    assert result["opportunity_id"] == "SELL|LIQUIDITY_REVERSAL"
    assert result["trade_authorized"] is False


def test_watching_explicit_invalidation_ends_developing_opportunity():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "BUY|AUCTION_WATCH_UP",
        "direction": "BUY",
        "setup": "AUCTION_WATCH_UP",
        "bars_waited": 2,
    }
    current = {
        "candidate": True,
        "ready": False,
        "invalidated": True,
        "executed": False,
        "direction": "BUY",
        "setup": "AUCTION_WATCH_UP",
        "thesis_status": "INVALIDATED",
        "upstream_evidence": ["E2_OPPORTUNITY_DEVELOPING"],
        "candle": "2026-09-02T10:25:00Z",
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "INVALIDATED"
    assert result["trade_authorized"] is False
