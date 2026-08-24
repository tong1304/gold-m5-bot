import pytest


def test_live_signal_time_is_displayed_in_bangkok_timezone():
    from statistics_page import _bangkok_display_time

    assert _bangkok_display_time("2026-08-24T16:16:00+00:00") == "25/08/2026 00:16:00"


def test_no_trade_reason_uses_recorded_rejection_reasons():
    from statistics_page import _no_trade_reason

    payload = {"signal": "NO_TRADE", "no_trade_reasons": ["RANGE_FILTER_FAILED", "NO_ALLOWED_ENGINE_SETUP"]}
    assert _no_trade_reason(payload) == "RANGE_FILTER_FAILED · NO_ALLOWED_ENGINE_SETUP"


def test_trade_without_no_trade_reason_shows_dash():
    from statistics_page import _no_trade_reason

    assert _no_trade_reason({"signal": "BUY"}) == "—"
