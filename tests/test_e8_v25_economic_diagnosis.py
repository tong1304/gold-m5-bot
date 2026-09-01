from production_v2.e8_brain import _economic_diagnosis


def test_e8_primary_veto_is_ranked_and_secondary_reasons_are_preserved():
    reasons = [
        "NO_USABLE_STRUCTURAL_TARGET",
        "INVALID_TRADE_GEOMETRY",
        "REAL_RR_BELOW_MINIMUM",
        "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    ]

    diagnosis = _economic_diagnosis(reasons, confirmation="CONFIRMED")

    assert diagnosis["primary_veto"] == "NO_USABLE_STRUCTURAL_TARGET"
    assert diagnosis["secondary_vetoes"] == [
        "INVALID_TRADE_GEOMETRY",
        "REAL_RR_BELOW_MINIMUM",
        "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    ]
    assert diagnosis["blocking_layers"] == ["TARGET", "GEOMETRY", "RR", "PROBABILITY"]


def test_e8_next_required_event_is_actionable_for_confirmation_blocker():
    diagnosis = _economic_diagnosis(
        ["ENTRY_CONFIRMATION", "PROBABILITY_EDGE_NOT_TRUSTWORTHY"],
        confirmation="NOT_CONFIRMED",
    )

    assert diagnosis["primary_veto"] == "ENTRY_CONFIRMATION"
    assert diagnosis["next_required_event"] == "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"


def test_e8_insufficient_history_is_data_blocker_not_profit_failure():
    diagnosis = _economic_diagnosis(
        ["HISTORICAL_SAMPLE_INSUFFICIENT", "PROBABILITY_EDGE_NOT_TRUSTWORTHY"],
        confirmation="CONFIRMED",
    )

    assert diagnosis["primary_veto"] == "HISTORICAL_SAMPLE_INSUFFICIENT"
    assert diagnosis["veto_class"] == "DATA_INSUFFICIENT"
    assert diagnosis["next_required_event"] == "MORE_RESOLVED_SETUP_HISTORY"
