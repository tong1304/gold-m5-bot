from scheduler_v11 import _is_stale_market_data_error


def test_stale_market_data_is_classified_as_data_unavailable():
    exc = RuntimeError("STALE_MARKET_DATA:GOLD:5m:age=32.4m")
    assert _is_stale_market_data_error(exc) is True


def test_other_scan_errors_are_not_classified_as_stale_data():
    exc = RuntimeError("LSE_INVALID_RESPONSE:GOLD:5m")
    assert _is_stale_market_data_error(exc) is False
