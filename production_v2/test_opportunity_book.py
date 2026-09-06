import pytest

from production_v2.opportunity_book import build_candidate, compare_candidates, update_book


def test_book_keeps_competing_directional_candidates():
    book = update_book({}, [
        build_candidate("BUY", "TREND_CONTINUATION", "2026-09-06T12:50:00Z", quality=0.78),
        build_candidate("SELL", "SWEEP_REJECTION", "2026-09-06T12:50:00Z", quality=0.62),
    ])
    assert {x["direction"] for x in book["candidates"]} == {"BUY", "SELL"}
    assert book["leader"] == "BUY"
    assert book["competition"] == "CONTESTED"


def test_same_candle_does_not_duplicate_candidate():
    candidate = build_candidate("BUY", "TREND_CONTINUATION", "C1")
    once = update_book({}, [candidate])
    twice = update_book(once, [candidate])
    assert len(twice["candidates"]) == 1


def test_poor_entry_does_not_invalidate_opportunity():
    candidate = build_candidate("BUY", "TREND_CONTINUATION", "C1", quality=0.8, wait_for=["PULLBACK"])
    assert candidate["state"] == "FORMING"
    assert candidate["wait_for"] == ["PULLBACK"]


def test_invalid_direction_is_rejected():
    with pytest.raises(ValueError):
        build_candidate("HOLD", "BALANCE", "C1")


def test_terminal_candidates_are_not_leaders():
    buy = build_candidate("BUY", "TREND_CONTINUATION", "C1", quality=0.9)
    sell = build_candidate("SELL", "SWEEP_REJECTION", "C1", quality=0.8)
    sell["state"] = "INVALIDATED"
    comparison = compare_candidates([buy, sell])
    assert comparison["leader"] == "BUY"
    assert comparison["competition"] == "UNCONTESTED"
