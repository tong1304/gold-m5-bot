from production_v2.opportunity_lifecycle import advance_opportunity


def _watch(event_id, candle):
    return {
        "candidate": True,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": event_id,
        "origin_event_id": event_id,
        "candle": candle,
        "ready": False,
        "thesis_proven": False,
        "invalidated": False,
    }


def test_new_causal_event_replaces_active_watch_even_when_setup_family_is_same():
    previous = advance_opportunity(None, _watch("2026-09-06T16:25:00Z|LOW_FAILED_BREAK_RECLAIM", "2026-09-06T16:25:00Z"))
    current = advance_opportunity(previous, _watch("2026-09-06T16:35:00Z|HIGH_SWEEP_REJECTION", "2026-09-06T16:35:00Z"))

    assert current["state"] == "REPLACED"
    assert current["continuity"] == "NEW_CAUSAL_EVENT_REPLACED_ACTIVE_OPPORTUNITY"
    assert current["previous_opportunity_id"] == previous["opportunity_id"]
    assert current["opportunity_id"] != previous["opportunity_id"]
    assert current["bars_waited"] == 0


def test_same_causal_event_preserves_opportunity_id_and_advances_one_bar():
    previous = advance_opportunity(None, _watch("2026-09-06T16:25:00Z|LOW_FAILED_BREAK_RECLAIM", "2026-09-06T16:25:00Z"))
    current = advance_opportunity(previous, _watch("2026-09-06T16:25:00Z|LOW_FAILED_BREAK_RECLAIM", "2026-09-06T16:30:00Z"))

    assert current["opportunity_id"] == previous["opportunity_id"]
    assert current["state"] == "WATCHING"
    assert current["bars_waited"] == 1
