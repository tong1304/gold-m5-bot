from datetime import datetime, timezone

from replay_signal_history_v11 import historical_window, HISTORICAL_CHUNK_BY_TIMEFRAME


def test_historical_window_covers_requested_period_and_warmup():
    start, end = historical_window("2026-08-01", "2026-08-24")

    assert start == datetime(2026, 7, 30, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 24, tzinfo=timezone.utc)


def test_historical_window_accepts_timezone_aware_iso_dates():
    start, end = historical_window("2026-08-01T00:00:00+00:00", "2026-08-24T12:00:00+00:00")

    assert start == datetime(2026, 7, 30, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def test_replay_chunks_are_small_enough_for_m5_and_m15():
    assert HISTORICAL_CHUNK_BY_TIMEFRAME["5m"].days == 2
    assert HISTORICAL_CHUNK_BY_TIMEFRAME["15m"].days == 4
