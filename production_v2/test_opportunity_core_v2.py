from production_v2.opportunity_core import OpportunityRecord


def test_placeholder_thesis_does_not_erase_meaningful_lifecycle_state():
    record = OpportunityRecord.from_lifecycle(
        {
            "opportunity_id": "SELL|EVENT-A",
            "direction": "SELL",
            "setup": "HIGH_FAILED_BREAK_RECLAIM",
            "state": "WAITING",
            "thesis_state": "VALIDATING",
            "confirmation_state": "CONFIRMING",
            "e6_thesis_proven": False,
        },
        "XAUUSD",
        "M5",
    )
    assert record.thesis_state == "VALIDATING"
    assert record.confirmation_state == "CONFIRMING"


def test_placeholder_setup_falls_back_to_meaningful_candidate_setup():
    record = OpportunityRecord.from_lifecycle(
        {
            "opportunity_id": "SELL|EVENT-A",
            "direction": "SELL",
            "setup": "UNKNOWN",
            "candidate_setup": "HIGH_FAILED_BREAK_RECLAIM",
            "state": "WATCHING",
        },
        "XAUUSD",
        "M5",
    )
    assert record.setup == "HIGH_FAILED_BREAK_RECLAIM"
