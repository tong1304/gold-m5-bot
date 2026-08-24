import pandas as pd

from v11.data_quality import validate_frame


def _frame(times):
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(times, utc=True),
            "open": [100.0] * len(times),
            "high": [101.0] * len(times),
            "low": [99.0] * len(times),
            "close": [100.5] * len(times),
        }
    )


def test_gold_dst_daily_break_is_allowed():
    # 2026-08-24 is inside US daylight-saving time. Gold's normal
    # New York 17:00-18:00 maintenance break is 21:00-22:00 UTC.
    times = [
        "2026-08-24T20:45:00Z",
        "2026-08-24T21:00:00Z",
        "2026-08-24T22:00:00Z",
        "2026-08-24T22:15:00Z",
    ]
    errors = validate_frame(_frame(times), minimum=2, timeframe_minutes=15, market="GOLD")
    assert "LARGE_DATA_GAP" not in errors


def test_gold_winter_daily_break_is_allowed():
    # In winter the same New York 17:00-18:00 break becomes 22:00-23:00 UTC.
    times = [
        "2026-01-05T21:45:00Z",
        "2026-01-05T22:00:00Z",
        "2026-01-05T23:00:00Z",
        "2026-01-05T23:15:00Z",
    ]
    errors = validate_frame(_frame(times), minimum=2, timeframe_minutes=15, market="GOLD")
    assert "LARGE_DATA_GAP" not in errors


def test_gold_dst_weekend_gap_is_allowed():
    times = [
        "2026-08-21T20:45:00Z",
        "2026-08-21T21:00:00Z",
        "2026-08-23T22:00:00Z",
        "2026-08-23T22:15:00Z",
    ]
    errors = validate_frame(_frame(times), minimum=2, timeframe_minutes=15, market="GOLD")
    assert "LARGE_DATA_GAP" not in errors


def test_gold_intraday_gap_is_still_rejected():
    times = [
        "2026-08-24T09:00:00Z",
        "2026-08-24T09:15:00Z",
        "2026-08-24T10:30:00Z",
    ]
    errors = validate_frame(_frame(times), minimum=2, timeframe_minutes=15, market="GOLD")
    assert "LARGE_DATA_GAP" in errors
