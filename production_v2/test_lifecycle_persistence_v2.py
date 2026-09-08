from production_v2.opportunity_lifecycle_progression import advance_lifecycle_stage


def test_e6_validating_thesis_persists_when_next_candle_has_no_new_trigger():
    previous = {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|evt-1",
        "direction": "SELL",
        "event_id": "evt-1",
        "origin_event_id": "evt-1",
        "lifecycle_stage": "THESIS",
        "thesis_state": "VALIDATING",
        "missing_proof": ["E4_FOLLOW_THROUGH", "E7_CONFIRMATION"],
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "event_id": "evt-1",
        "setup": "HIGH_FAILED_BREAK_RECLAIM",
        "candle": "2026-09-08T08:45:00Z",
        "thesis_state": "UNKNOWN",
        "missing_proof": [],
        "e7_confirmation_state": "PENDING",
    }
    progressed = advance_lifecycle_stage(previous, current)
    assert progressed["opportunity_id"] == previous["opportunity_id"]
    assert progressed["thesis_state"] == "VALIDATING"
    assert "E4_FOLLOW_THROUGH" in progressed["missing_proof"]


def test_e7_confirming_persists_without_a_new_trigger():
    previous = {
        "opportunity_id": "SELL|OPPORTUNITY_WATCH|evt-2",
        "direction": "SELL",
        "event_id": "evt-2",
        "origin_event_id": "evt-2",
        "lifecycle_stage": "CONFIRMING",
        "thesis_state": "VALIDATING",
        "e7_confirmation_state": "CONFIRMING",
    }
    current = {
        "candidate": True,
        "direction": "SELL",
        "event_id": "evt-2",
        "setup": "HIGH_FAILED_BREAK_RECLAIM",
        "candle": "2026-09-08T08:50:00Z",
        "e7_confirmation_state": "PENDING",
        "e7_confirmed": False,
    }
    progressed = advance_lifecycle_stage(previous, current)
    assert progressed["opportunity_id"] == previous["opportunity_id"]
    assert progressed["lifecycle_stage"] == "CONFIRMING"
    assert progressed["e7_confirmation_state"] == "CONFIRMING"
