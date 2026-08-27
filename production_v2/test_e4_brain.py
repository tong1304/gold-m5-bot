"""TDD coverage for the E4 Liquidity & Auction state machine."""
from production_v2.e4_brain import _classify_auction_response


def _bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def _event(kind, direction, level=100.0):
    return {"type": kind, "direction": direction, "zone": {"lower": level, "upper": level, "price": level}}


def test_sweep_rejection_is_pending_without_follow_through():
    bars = [_bar(99.8, 100.8, 99.6, 100.1), _bar(100.1, 101.2, 99.9, 100.2)]
    result = _classify_auction_response(_event("HIGH_SWEEP_REJECTION", "DOWN"), bars, 1.0, event_index=0)
    assert result["response"] == "REJECTION_PENDING"
    assert result["confirmed"] is False


def test_sweep_rejection_confirms_only_after_directional_follow_through():
    bars = [_bar(99.8, 101.0, 99.5, 99.9), _bar(99.9, 100.1, 98.7, 98.9), _bar(98.9, 99.2, 98.2, 98.4)]
    result = _classify_auction_response(_event("HIGH_SWEEP_REJECTION", "DOWN"), bars, 1.0, event_index=0)
    assert result["response"] == "REJECTION_CONFIRMED"
    assert result["confirmed"] is True
    assert result["follow_through_bars"] >= 1


def test_break_acceptance_requires_close_and_follow_through_beyond_liquidity():
    bars = [_bar(99.8, 100.9, 99.7, 100.4), _bar(100.4, 101.2, 100.1, 100.8), _bar(100.8, 101.5, 100.5, 101.1)]
    result = _classify_auction_response(_event("HIGH_ACCEPTANCE_CANDIDATE", "UP"), bars, 1.0, event_index=0)
    assert result["response"] == "ACCEPTANCE_CONFIRMED"
    assert result["confirmed"] is True


def test_failed_break_reclaim_is_rejection_not_acceptance():
    bars = [_bar(100.2, 101.0, 99.9, 100.6), _bar(100.6, 101.0, 99.4, 99.8), _bar(99.8, 100.0, 98.8, 99.0)]
    result = _classify_auction_response(_event("HIGH_FAILED_BREAK_RECLAIM", "DOWN"), bars, 1.0, event_index=1)
    assert result["response"] == "REJECTION_CONFIRMED"
    assert result["confirmed"] is True
