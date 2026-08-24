import pytest

from live_scanner_v11 import _normalize


def test_normalize_ignores_gold_day_marker_rows():
    raw = {
        "data": [
            {"day": "2026-08-22"},
            {"timestamp": "2026-08-24T17:00:00Z", "open": 1, "high": 2, "low": 0, "close": 1.5},
            {"timestamp": "2026-08-24T17:15:00Z", "open": 1.5, "high": 2.5, "low": 1, "close": 2},
        ]
    }
    frame = _normalize(raw, "GOLD", "15m")
    assert len(frame) == 2
    assert frame["datetime"].notna().all()
    assert list(frame["close"]) == [1.5, 2.0]


def test_normalize_rejects_response_with_only_metadata_rows():
    raw = {"data": [{"day": "2026-08-22"}]}
    with pytest.raises(RuntimeError, match="no_candle_rows"):
        _normalize(raw, "GOLD", "15m")
