from datetime import datetime, timezone

from scripts.run_latest_24h_backtest import build_latest_24h_window


def test_latest_24h_window_is_exactly_24_hours_and_utc():
    now = datetime(2026, 9, 2, 3, 15, 0, tzinfo=timezone.utc)
    start, end = build_latest_24h_window(now)
    assert end == now
    assert start == datetime(2026, 9, 1, 3, 15, 0, tzinfo=timezone.utc)
    assert end - start == __import__('datetime').timedelta(hours=24)


def test_latest_24h_window_requires_timezone_aware_now():
    try:
        build_latest_24h_window(datetime(2026, 9, 2, 3, 15, 0))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError for naive datetime")
