from production_v2.opportunity_lifecycle import advance_opportunity


def test_watch_persists_across_closed_candles_without_new_identity_or_event_churn():
    first = advance_opportunity(None, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-1",
        "candle": "2026-09-04T14:35:00Z",
        "candidate": True,
    })
    second = advance_opportunity(first, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-2",
        "candle": "2026-09-04T14:40:00Z",
        "candidate": True,
        "wait_for": ["E4_FOLLOW_THROUGH"],
    })
    assert first["continuity"] == "NEW_OPPORTUNITY_WATCH"
    assert second["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert second["opportunity_id"] == first["opportunity_id"]
    assert second["bars_waited"] == 1
    assert second["trade_authorized"] is False


def test_watch_promotes_to_setup_without_changing_opportunity_identity():
    watch = advance_opportunity(None, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-1",
        "candle": "2026-09-04T14:35:00Z",
        "candidate": True,
    })
    thesis = advance_opportunity(watch, {
        "direction": "SELL",
        "setup": "LOW_ACCEPTANCE",
        "event_id": "AUCTION-2",
        "candle": "2026-09-04T14:40:00Z",
        "candidate": True,
        "ready": False,
        "wait_for": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
    })
    assert thesis["state"] == "WAITING"
    assert thesis["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert thesis["opportunity_id"] == watch["opportunity_id"]
    assert thesis["bars_waited"] == 1
    assert thesis["trade_authorized"] is False


def test_direction_change_invalidates_pending_opportunity():
    watch = advance_opportunity(None, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-1",
        "candle": "2026-09-04T14:35:00Z",
        "candidate": True,
    })
    changed = advance_opportunity(watch, {
        "direction": "BUY",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-2",
        "candle": "2026-09-04T14:40:00Z",
        "candidate": True,
    })
    assert changed["state"] == "INVALIDATED"
    assert changed["invalidation_reason"] == "DIRECTION_CHANGED"
    assert changed["trade_authorized"] is False


def test_lifecycle_never_authorizes_execution_from_ready_without_explicit_execution():
    ready = advance_opportunity(None, {
        "direction": "SELL",
        "setup": "LOW_ACCEPTANCE",
        "event_id": "AUCTION-1",
        "candle": "2026-09-04T14:40:00Z",
        "candidate": True,
        "ready": True,
    })
    assert ready["state"] == "READY"
    assert ready["trade_authorized"] is False


def test_watch_invalidates_when_upstream_causal_evidence_is_explicitly_lost():
    watch = advance_opportunity(None, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-1",
        "candle": "2026-09-04T14:35:00Z",
        "candidate": True,
        "upstream_evidence": [{"source": "E4", "event": "HIGH_SWEEP_REJECTION"}],
    })
    lost = advance_opportunity(watch, {
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "AUCTION-2",
        "candle": "2026-09-04T14:40:00Z",
        "candidate": True,
        "upstream_evidence": [],
    })
    assert lost["state"] == "INVALIDATED"
    assert lost["continuity"] == "OPPORTUNITY_INVALIDATED"
    assert lost["invalidation_reason"] == "UPSTREAM_CAUSAL_EVIDENCE_LOST"
    assert lost["opportunity_id"] == watch["opportunity_id"]
    assert lost["trade_authorized"] is False
