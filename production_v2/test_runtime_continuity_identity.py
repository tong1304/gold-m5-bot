from .opportunity_lifecycle_progression import advance_lifecycle_stage


def advance(previous, event_id, candle, **evidence):
    return advance_lifecycle_stage(previous, {"direction": "BUY", "candidate": True, "event_id": event_id, "candle": candle, **evidence})


def test_event_changes_preserve_opportunity_and_origin_identity():
    first = advance(None, "EVENT-A", "2026-09-07T10:00:00Z")
    second = advance(first, "EVENT-B", "2026-09-07T10:05:00Z", confirmed=True)
    assert second["opportunity_id"] == first["opportunity_id"]
    assert second["origin_event_id"] == "EVENT-A"
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
