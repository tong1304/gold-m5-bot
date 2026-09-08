from .opportunity_lifecycle_progression import advance_lifecycle_stage


def advance(previous, event_id, candle, **evidence):
    return advance_lifecycle_stage(previous, {"direction": "BUY", "candidate": True, "event_id": event_id, "candle": candle, **evidence})


def test_event_changes_create_a_new_causal_opportunity_identity():
    first = advance(None, "EVENT-A", "2026-09-07T10:00:00Z")
    second = advance(first, "EVENT-B", "2026-09-07T10:05:00Z", confirmed=True)
    assert second["opportunity_id"] != first["opportunity_id"]
    assert second["opportunity_id"] == "BUY|OPPORTUNITY|EVENT-B"
    assert second["origin_event_id"] == "EVENT-B"
    assert second["event_id"] == "EVENT-B"
    assert second["last_progression_candle"] == "2026-09-07T10:05:00Z"


def test_terminal_opportunity_reopens_only_for_a_new_causal_event():
    first = advance(None, "EVENT-A", "2026-09-07T10:00:00Z")
    expired = advance(first, "EVENT-A", "2026-09-07T10:05:00Z", execution_state="EXPIRED")
    stale = advance(expired, "EVENT-A", "2026-09-07T10:10:00Z", thesis_proven=True)
    fresh = advance(expired, "EVENT-B", "2026-09-07T10:10:00Z")
    assert stale["opportunity_id"] == first["opportunity_id"]
    assert stale["lifecycle_stage"] == "EXPIRED"
    assert fresh["lifecycle_stage"] == "WATCH"
    assert fresh["opportunity_id"] != first["opportunity_id"]
    assert fresh["origin_event_id"] == "EVENT-B"


def test_missing_event_field_preserves_prior_causal_identity_for_active_opportunity():
    first = advance(None, "EVENT-A", "2026-09-08T08:40:00Z", setup="HIGH_FAILED_BREAK_RECLAIM")
    second = advance(first, None, "2026-09-08T08:45:00Z", setup="HIGH_FAILED_BREAK_RECLAIM")
    assert second["opportunity_id"] == first["opportunity_id"]
    assert second["event_id"] == "EVENT-A"
    assert second["origin_event_id"] == "EVENT-A"


def test_setup_wording_change_preserves_identity_for_same_event():
    first = advance(None, "EVENT-A", "2026-09-08T08:40:00Z", setup="OPPORTUNITY_WATCH")
    second = advance(first, "EVENT-A", "2026-09-08T08:45:00Z", setup="HIGH_FAILED_BREAK_RECLAIM")
    assert second["opportunity_id"] == first["opportunity_id"]


def test_terminal_opportunity_never_revives_on_same_causal_event():
    first = advance(None, "EVENT-A", "2026-09-08T08:40:00Z")
    expired = advance(first, "EVENT-A", "2026-09-08T08:45:00Z", execution_state="EXPIRED")
    stale = advance(expired, "EVENT-A", "2026-09-08T08:50:00Z", thesis_proven=True, e7_confirmed=True, e8_ready=True, e9_trade=True)
    assert expired["lifecycle_stage"] == "EXPIRED"
    assert stale["lifecycle_stage"] == "EXPIRED"
    assert stale["trade_authorized"] is False
    assert stale["opportunity_id"] == first["opportunity_id"]
