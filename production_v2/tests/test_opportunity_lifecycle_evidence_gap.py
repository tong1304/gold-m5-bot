from production_v2.opportunity_lifecycle import advance_opportunity


def test_persisted_watch_survives_one_upstream_evidence_gap_and_clock_advances():
    previous = advance_opportunity(None, {
        "candidate": True,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "event_id": "2026-09-06T16:25:00Z|LOW_FAILED_BREAK_RECLAIM",
        "origin_event_id": "2026-09-06T16:25:00Z|LOW_FAILED_BREAK_RECLAIM",
        "candle": "2026-09-06T16:25:00Z",
        "ready": False,
        "thesis_proven": False,
        "invalidated": False,
    })
    current = advance_opportunity(previous, {
        "candidate": False,
        "direction": "SELL",
        "setup": "OPPORTUNITY_WATCH",
        "candle": "2026-09-06T16:30:00Z",
        "ready": False,
        "thesis_proven": False,
        "invalidated": False,
    })

    assert current["opportunity_id"] == previous["opportunity_id"]
    assert current["event_id"] == previous["event_id"]
    assert current["origin_event_id"] == previous["origin_event_id"]
    assert current["bars_waited"] == 1
    assert current["state"] == "WATCHING"
