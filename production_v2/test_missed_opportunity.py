from production_v2.missed_opportunity import classify_opportunity


def test_watch_without_proven_geometry_is_good_wait():
    result = classify_opportunity(
        {"direction": "SELL", "state": "WATCHING", "thesis_proven": False},
        [{"high": 101, "low": 99}],
    )
    assert result["classification"] == "GOOD_WAIT"
    assert result["measured"] is True


def test_proven_opportunity_that_moves_without_execution_is_missed():
    result = classify_opportunity(
        {"direction": "SELL", "state": "READY", "thesis_proven": True, "entry": 100, "stop_loss": 102},
        [{"high": 100.2, "low": 99}],
    )
    assert result["classification"] == "MISSED_GOOD_TRADE"
    assert result["favorable_r"] == 0.5


def test_large_favorable_extension_is_late_entry():
    result = classify_opportunity(
        {"direction": "BUY", "state": "READY", "thesis_proven": True, "entry": 100, "stop_loss": 98},
        [{"high": 102.5, "low": 99.8}],
    )
    assert result["classification"] == "LATE_ENTRY"
    assert result["favorable_r"] == 1.25


def test_invalidated_opportunity_with_adverse_move_is_false():
    result = classify_opportunity(
        {"direction": "BUY", "state": "INVALIDATED", "thesis_proven": False, "entry": 100, "stop_loss": 98},
        [{"high": 100.1, "low": 98.5}],
    )
    assert result["classification"] == "FALSE_OPPORTUNITY"


def test_detector_never_authorizes_trade():
    result = classify_opportunity(
        {"direction": "BUY", "state": "READY", "thesis_proven": True, "entry": 100, "stop_loss": 98},
        [{"high": 101, "low": 99.8}],
    )
    assert "trade_authorized" not in result
