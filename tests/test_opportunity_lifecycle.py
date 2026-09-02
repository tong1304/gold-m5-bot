from production_v2.opportunity_lifecycle import advance_opportunity


def test_upstream_watch_waits_across_next_closed_candle():
    first = advance_opportunity(
        {}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"}
    )
    assert first["state"] == "WAITING"
    assert first["bars_waited"] == 0
    assert first["opportunity_id"] == "SELL|OPPORTUNITY_WATCH"

    second = advance_opportunity(
        first, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:15:00Z"}
    )
    assert second["state"] == "WAITING"
    assert second["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert second["bars_waited"] == 1


def test_pending_watch_promotes_to_real_setup_without_resetting_thesis():
    first = advance_opportunity(
        {}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"}
    )
    promoted = advance_opportunity(
        first, {"candidate": True, "direction": "SELL", "setup": "SWEEP_RECLAIM", "ready": False, "invalidated": False, "executed": False, "thesis_status": "VALIDATING", "candle": "2026-09-02T10:15:00Z"}
    )
    assert promoted["state"] == "WAITING"
    assert promoted["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert promoted["direction"] == "SELL"
    assert promoted["setup"] == "SWEEP_RECLAIM"
    assert promoted["bars_waited"] == 1


def test_direction_change_invalidates_pending_opportunity():
    first = advance_opportunity(
        {}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"}
    )
    changed = advance_opportunity(
        first, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:15:00Z"}
    )
    assert changed["state"] == "INVALIDATED"
    assert changed["invalidation_reason"] == "DIRECTION_CHANGED"


def test_explicit_invalidation_is_hard_stop():
    first = advance_opportunity(
        {}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"}
    )
    invalidated = advance_opportunity(
        first, {"candidate": False, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": [], "ready": False, "invalidated": True, "executed": False, "thesis_status": "NONE", "candle": "2026-09-02T10:15:00Z"}
    )
    assert invalidated["state"] == "INVALIDATED"
    assert invalidated["invalidation_reason"] == "CURRENT_CANDLE_INVALIDATED"


def test_upstream_watch_invalidates_when_causal_evidence_is_lost():
    first = advance_opportunity(
        {}, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"}
    )
    lost = advance_opportunity(
        first, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": [], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:15:00Z"}
    )
    assert lost["state"] == "INVALIDATED"
    assert lost["invalidation_reason"] == "UPSTREAM_CAUSAL_EVIDENCE_LOST"
