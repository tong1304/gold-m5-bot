from datetime import datetime, timedelta, timezone

from production_v2.mtf_runtime import _closed_m15_from_m5


def _bars(count=6):
    start = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        stamp = start + timedelta(minutes=5 * index)
        rows.append({
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100.5 + index,
            "timestamp": stamp.isoformat().replace("+00:00", "Z"),
            "candle_id": stamp.isoformat().replace("+00:00", "Z"),
            "is_closed": True,
        })
    return rows


def test_three_closed_m5_bars_form_one_aligned_m15_context_candle():
    result = _closed_m15_from_m5(_bars())
    assert len(result) == 2
    assert result[0]["timeframe"] == "M15"
    assert result[0]["open"] == 100.0
    assert result[0]["high"] == 103.0
    assert result[0]["low"] == 99.0
    assert result[0]["close"] == 102.5
    assert result[0]["is_closed"] is True


def test_incomplete_m5_group_is_not_promoted_to_m15():
    result = _closed_m15_from_m5(_bars(5))
    assert len(result) == 1
