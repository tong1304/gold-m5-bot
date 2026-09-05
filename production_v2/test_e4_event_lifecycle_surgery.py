from production_v2.e4_event_lifecycle_surgery import _repair


def _bar(ts: str, close: float) -> dict:
    return {"timestamp": ts, "open": close, "high": close, "low": close, "close": close}


def test_pending_acceptance_advances_to_confirmed_after_two_closed_candles():
    bars = [
        _bar("2026-09-05T16:10:00Z", 79700.0),
        _bar("2026-09-05T16:15:00Z", 79763.41),
        _bar("2026-09-05T16:20:00Z", 79805.72),
        _bar("2026-09-05T16:25:00Z", 79863.99),
    ]
    output = {
        "event_candle_id": "2026-09-05T16:15:00Z",
        "event_level": 79763.41,
        "event_atr": 47.140714,
        "auction_state": "PENDING",
        "event": {
            "index": 3,
            "event_candle_id": "2026-09-05T16:15:00Z",
            "event_level": 79763.41,
            "event_atr": 47.140714,
            "directional_implication": "UP",
        },
    }

    repaired = _repair(output, bars)

    assert repaired["auction_state"] == "CONFIRMED"
    assert repaired["event_age_bars"] == 2
    assert repaired["follow_through_bars"] == 2
    assert repaired["auction_confirmation"] == "FOLLOW_THROUGH_CONFIRMED"


def test_pending_event_invalidates_on_post_event_reclamation():
    bars = [
        _bar("2026-09-05T16:15:00Z", 79763.41),
        _bar("2026-09-05T16:20:00Z", 79805.72),
        _bar("2026-09-05T16:25:00Z", 79750.00),
    ]
    output = {
        "event_candle_id": "2026-09-05T16:15:00Z",
        "event_level": 79763.41,
        "event_atr": 47.140714,
        "auction_state": "PENDING",
        "event": {
            "index": 2,
            "event_candle_id": "2026-09-05T16:15:00Z",
            "event_level": 79763.41,
            "event_atr": 47.140714,
            "directional_implication": "UP",
        },
    }

    repaired = _repair(output, bars)

    assert repaired["auction_state"] == "INVALIDATED"
    assert repaired["event_age_bars"] == 2
    assert repaired["auction_confirmation"] == "POST_EVENT_RECLAMATION"
