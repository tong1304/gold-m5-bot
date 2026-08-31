from production_v2.e6_brain import _auction, _candidates


def test_pending_liquidity_event_does_not_create_reversal_setup():
    auction = _auction({
        "event": "HIGH_FAILED_BREAK_RECLAIM",
        "auction_state": "PENDING",
        "event_age_bars": 0,
        "event_level": 4441.75,
        "event_id": "pending-event",
    })
    candidates = _candidates(
        "SELL",
        auction,
        {"trend_state": "DOWN", "pressure": "DOWN"},
        {"internal_state": "NEUTRAL", "external_state": "UP"},
        {},
    )
    assert not any(c["name"] == "LIQUIDITY_REVERSAL" for c in candidates)
