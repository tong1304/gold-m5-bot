from production_v2.e4_event_lifecycle_surgery import _repair


def _bar(ts, close):
    return {
        "timestamp": ts,
        "open": close - 1.0,
        "high": close + 2.0,
        "low": close - 2.0,
        "close": close,
        "is_closed": True,
    }


def _output():
    return {
        "event": {
            "type": "HIGH_ACCEPTANCE_CANDIDATE",
            "directional_implication": "UP",
            "event_level": 100.0,
            "event_atr": 10.0,
            "event_candle_id": "2026-09-05T16:30:00Z",
            "event_candle": {"open": 99.0, "high": 104.0, "low": 98.0, "close": 103.0},
        },
        "event_id": "2026-09-05T16:30:00Z|HIGH_ACCEPTANCE_CANDIDATE|HIGH|100|UP",
        "event_candle_id": "2026-09-05T16:30:00Z",
        "event_level": 100.0,
        "event_atr_frozen": 10.0,
        "auction_state": "PENDING",
        "auction_phase": "PENDING",
        "event_age_bars": 0,
    }


def test_event_age_uses_evaluation_timestamp_when_bars_lag_one_candle():
    bars = [
        _bar("2026-09-05T16:25:00Z", 98.0),
        _bar("2026-09-05T16:30:00Z", 103.0),
        _bar("2026-09-05T16:35:00Z", 104.0),
    ]
    repaired = _repair(
        _output(),
        bars,
        {"evaluation_candle_timestamp": "2026-09-05T16:40:00Z"},
        None,
    )
    assert repaired["auction_lifecycle_repaired"] is True
    assert repaired["event_age_bars"] == 2
    assert repaired["auction_state"] == "CONFIRMED"
    assert repaired["follow_through_bars"] == 2


def test_pending_event_does_not_age_from_last_bar_when_evaluation_is_same_candle():
    bars = [
        _bar("2026-09-05T16:25:00Z", 98.0),
        _bar("2026-09-05T16:30:00Z", 103.0),
    ]
    repaired = _repair(
        _output(),
        bars,
        {"candle_close_timestamp": "2026-09-05T16:30:00Z"},
        None,
    )
    assert repaired["event_age_bars"] == 0
    assert repaired["auction_state"] == "PENDING"
