from production_v2.opportunity_lifecycle import advance_opportunity


def test_upstream_watch_waits_across_next_closed_candle():
    first = advance_opportunity({}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"})
    assert first["state"] == "WATCHING"
    assert first["bars_waited"] == 0
    assert first["opportunity_id"] == "SELL|OPPORTUNITY_WATCH"
    assert first["canonical_stage"] == "WATCH"
    assert first["opportunity_record"]["decision_authority"] == "E9_ONLY"
    second = advance_opportunity(first, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:15:00Z"})
    assert second["state"] == "WATCHING"
    assert second["continuity"] == "CONTINUING_UPSTREAM_WATCH"
    assert second["bars_waited"] == 1
    assert second["opportunity_id"] == first["opportunity_id"]


def test_pending_watch_promotes_to_real_setup_without_resetting_thesis():
    first = advance_opportunity({}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"})
    promoted = advance_opportunity(first, {"candidate": True, "direction": "SELL", "setup": "SWEEP_RECLAIM", "ready": False, "invalidated": False, "executed": False, "thesis_status": "VALIDATING", "candle": "2026-09-02T10:15:00Z"})
    assert promoted["state"] == "WAITING"
    assert promoted["continuity"] == "PROMOTED_PENDING_OPPORTUNITY"
    assert promoted["direction"] == "SELL"
    assert promoted["setup"] == "SWEEP_RECLAIM"
    assert promoted["bars_waited"] == 1
    assert promoted["canonical_stage"] == "THESIS"


def test_direction_change_replaces_pending_opportunity():
    first = advance_opportunity({}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"})
    changed = advance_opportunity(first, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:15:00Z"})
    assert changed["state"] == "REPLACED"
    assert changed["invalidation_reason"] == "DIRECTION_CHANGED"
    assert changed["previous_opportunity_id"] == first["opportunity_id"]
    assert changed["opportunity_id"] != first["opportunity_id"]
    assert changed["canonical_stage"] == "INVALIDATED"


def test_explicit_invalidation_is_hard_stop():
    first = advance_opportunity({}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"})
    invalidated = advance_opportunity(first, {"candidate": False, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": [], "ready": False, "invalidated": True, "executed": False, "thesis_status": "NONE", "candle": "2026-09-02T10:15:00Z"})
    assert invalidated["state"] == "INVALIDATED"
    assert invalidated["invalidation_reason"] == "CURRENT_CANDLE_INVALIDATED"
    assert invalidated["canonical_stage"] == "INVALIDATED"


def test_upstream_watch_invalidates_when_causal_evidence_is_lost():
    first = advance_opportunity({}, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": ["E4_AUCTION_PENDING"], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:10:00Z"})
    lost = advance_opportunity(first, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "upstream_evidence": [], "ready": False, "invalidated": False, "executed": False, "thesis_status": "FORMING", "candle": "2026-09-02T10:15:00Z", "upstream_evidence_lost": True})
    assert lost["state"] == "INVALIDATED"
    assert lost["invalidation_reason"] == "UPSTREAM_CAUSAL_EVIDENCE_LOST"


def test_fast_early_timing_propagates_confirmation_window_without_authorizing_trade():
    result = advance_opportunity({}, {"candidate": True, "direction": "BUY", "setup": "OPPORTUNITY_WATCH", "ready": False, "invalidated": False, "candle": "2026-09-02T10:10:00Z", "opportunity_phase": "EARLY_OPPORTUNITY", "opportunity_speed": "FAST", "confirmation_window": "NEXT_CLOSED_M5_CANDLE", "wait_for": "FAST_CLOSED_CANDLE_CONFIRMATION", "chase_prohibited": False})
    assert result["state"] == "WATCHING"
    assert result["opportunity_speed"] == "FAST"
    assert result["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert result["wait_for"] == "FAST_CLOSED_CANDLE_CONFIRMATION"
    assert result["chase_prohibited"] is False
    assert result["trade_authorized"] is False


def test_standard_timing_propagates_normal_confirmation_window():
    result = advance_opportunity({}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "ready": False, "invalidated": False, "candle": "2026-09-02T10:10:00Z", "opportunity_phase": "EARLY_OPPORTUNITY", "opportunity_speed": "STANDARD", "confirmation_window": "NEXT_CLOSED_M5_CANDLE", "wait_for": "CLOSED_CANDLE_CONFIRMATION", "chase_prohibited": False})
    assert result["opportunity_speed"] == "STANDARD"
    assert result["confirmation_window"] == "NEXT_CLOSED_M5_CANDLE"
    assert result["wait_for"] == "CLOSED_CANDLE_CONFIRMATION"
    assert result["trade_authorized"] is False


def test_late_timing_forbids_chase_and_waits_for_new_causal_event():
    result = advance_opportunity({}, {"candidate": True, "direction": "SELL", "setup": "OPPORTUNITY_WATCH", "ready": False, "invalidated": False, "candle": "2026-09-02T10:10:00Z", "opportunity_phase": "LATE_OPPORTUNITY", "opportunity_speed": "SLOW", "confirmation_window": "NEW_CAUSAL_EVENT", "wait_for": "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT", "chase_prohibited": True})
    assert result["opportunity_speed"] == "SLOW"
    assert result["confirmation_window"] == "NEW_CAUSAL_EVENT"
    assert result["wait_for"] == "NO_CHASE;WAIT_FOR_NEW_CAUSAL_EVENT"
    assert result["chase_prohibited"] is True
    assert result["trade_authorized"] is False
