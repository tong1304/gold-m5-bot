import pandas as pd

from v11.replay import _m15_context_end_positions


def test_m15_context_positions_match_closed_context_rule():
    m5 = pd.DataFrame({
        "datetime": pd.date_range("2026-08-23 00:00:00", periods=12, freq="5min", tz="UTC")
    })
    m15 = pd.DataFrame({
        "datetime": pd.date_range("2026-08-22 00:00:00", periods=12, freq="15min", tz="UTC")
    })

    positions = _m15_context_end_positions(m5, m15)

    expected = []
    m15_times = pd.DatetimeIndex(m15["datetime"])
    for ts in m5["datetime"]:
        expected.append(int(m15_times.searchsorted(ts - pd.Timedelta(minutes=15), side="right")))

    assert positions == expected
