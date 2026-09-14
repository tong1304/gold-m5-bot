from .opportunity_lifecycle_progression import advance_lifecycle_stage


def advance(previous, event_id, candle, **evidence):
    return advance_lifecycle_stage(
        previous,
        {"direction": "BUY", "candidate": True, "event_id": event_id, "candle": candle, **evidence},
    )


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
