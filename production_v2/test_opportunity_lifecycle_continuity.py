from production_v2.opportunity_lifecycle import advance_opportunity


def test_watch_preserves_concrete_missing_proof_across_closed_candles():
    first = advance_opportunity(None, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "evt-1",
        "candle": "2026-09-06T07:10:00Z",
        "candidate": True,
        "ready": False,
        "invalidated": False,
        "thesis_proven": False,
        "wait_for": ["E4_AUCTION_FOLLOW_THROUGH", "E3_INTERNAL_STRUCTURE_ALIGNMENT"],
    })
    assert first["state"] == "WATCHING"
    assert first["bars_waited"] == 0

    second = advance_opportunity(first, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "evt-1",
        "candle": "2026-09-06T07:15:00Z",
        "candidate": True,
        "ready": False,
        "invalidated": False,
        "thesis_proven": False,
        "wait_for": ["E4_AUCTION_FOLLOW_THROUGH", "E3_INTERNAL_STRUCTURE_ALIGNMENT"],
    })
    assert second["state"] == "WATCHING"
    assert second["bars_waited"] == 1
    assert second["opportunity_id"] == first["opportunity_id"]
    assert second["wait_for"] == ["E4_AUCTION_FOLLOW_THROUGH", "E3_INTERNAL_STRUCTURE_ALIGNMENT"]


def test_watch_promotes_only_when_real_setup_exists():
    first = advance_opportunity(None, {
        "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "event_id": "evt-1",
        "candle": "2026-09-06T07:10:00Z", "candidate": True, "ready": False,
        "invalidated": False, "thesis_proven": False,
        "wait_for": ["E4_AUCTION_FOLLOW_THROUGH"],
    })
    promoted = advance_opportunity(first, {
        "direction": "SELL", "setup": "LIQUIDITY_REVERSAL", "event_id": "evt-1",
        "candle": "2026-09-06T07:15:00Z", "candidate": True, "ready": False,
        "invalidated": False, "thesis_proven": True,
        "wait_for": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
    })
    assert promoted["state"] == "WAITING"
    assert promoted["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert promoted["setup"] == "LIQUIDITY_REVERSAL"
    assert promoted["bars_waited"] == 1


def test_watch_expires_after_maximum_age():
    state = None
    for minute in (0, 5, 10, 15, 20, 25):
        candle = f"2026-09-06T07:{minute:02d}:00Z"
        state = advance_opportunity(state, {
            "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "event_id": "evt-1",
            "candle": candle, "candidate": True, "ready": False,
            "invalidated": False, "thesis_proven": False,
            "wait_for": ["E4_AUCTION_FOLLOW_THROUGH"],
        })
    assert state["state"] == "EXPIRED"
    assert state["bars_waited"] == 6
    assert state["invalidation_reason"] == "WATCH_MAX_AGE_REACHED"
