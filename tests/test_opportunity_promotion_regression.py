from production_v2.opportunity_lifecycle import advance_opportunity


def test_watch_promotes_to_setup_with_new_setup_identity():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 1,
        "origin_candle": "2026-09-05T15:50:00Z",
    }
    current = {
        "candidate": True,
        "ready": False,
        "direction": "SELL",
        "setup": "LIQUIDITY_RESPONSE",
        "candle": "2026-09-05T15:55:00Z",
        "event_id": "2026-09-05T15:55:00Z|HIGH_SWEEP_REJECTION|HIGH|79760|DOWN",
        "wait_for": ["E7_CONFIRMATION"],
        "upstream_evidence": ["E4_DIRECTIONAL_AUCTION_EVIDENCE"],
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "WAITING"
    assert result["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert result["setup"] == "LIQUIDITY_RESPONSE"
    assert result["opportunity_id"] == "SELL|LIQUIDITY_RESPONSE"
    assert result["origin_candle"] == previous["origin_candle"]


def test_watch_can_promote_to_ready_without_execution_authority():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "BUY|OPPORTUNITY_WATCH",
        "direction": "BUY",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 2,
        "origin_candle": "2026-09-05T16:00:00Z",
    }
    current = {
        "candidate": True,
        "ready": True,
        "direction": "BUY",
        "setup": "AUCTION_ACCEPTANCE_CONTINUATION",
        "candle": "2026-09-05T16:05:00Z",
        "event_id": "2026-09-05T16:05:00Z|HIGH_ACCEPTANCE|HIGH|79800|UP",
        "wait_for": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
        "upstream_evidence": ["E4_AUCTION_CONFIRMED"],
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "READY"
    assert result["continuity"] == "PROMOTED_PENDING_OPPORTUNITY_TO_SETUP"
    assert result["opportunity_id"] == "BUY|AUCTION_ACCEPTANCE_CONTINUATION"
    assert result["trade_authorized"] is False


def test_watch_continuity_is_preserved_when_setup_is_still_a_watch():
    previous = {
        "state": "WATCHING",
        "opportunity_id": "SELL|OPPORTUNITY_WATCH",
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "bars_waited": 1,
    }
    current = {
        "candidate": True,
        "ready": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "candle": "2026-09-05T16:00:00Z",
        "event_id": "event-2",
        "wait_for": ["E2_OPPORTUNITY_CONFIRMATION"],
        "upstream_evidence": ["E4_AUCTION_PENDING"],
    }

    result = advance_opportunity(previous, current)

    assert result["state"] == "WATCHING"
    assert result["opportunity_id"] == "SELL|OPPORTUNITY_WATCH"
    assert result["continuity"] == "CONTINUING_UPSTREAM_WATCH"
