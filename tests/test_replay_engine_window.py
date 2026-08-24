import pandas as pd

import v11.replay as replay


def _frame(rows, freq):
    return pd.DataFrame({
        "datetime": pd.date_range("2026-08-01", periods=rows, freq=freq, tz="UTC"),
        "open": [100.0] * rows,
        "high": [101.0] * rows,
        "low": [99.0] * rows,
        "close": [100.5] * rows,
        "volume": [1.0] * rows,
    })


def test_replay_passes_only_bounded_history_to_engine(monkeypatch):
    m5 = _frame(140, "5min")
    m15 = _frame(140, "15min")
    seen = []

    def fake_analyze(m5_arg, m15_arg, symbol, index=None):
        seen.append((len(m5_arg), len(m15_arg), index))
        return {
            "signal": "NO_TRADE",
            "strategy": "NONE",
            "valid": False,
            "trade_levels": {"valid": False},
        }

    monkeypatch.setattr(replay.engine, "analyze", fake_analyze)
    monkeypatch.setattr(replay, "resolve_outcome", lambda signal, future: {"result": "NO_TRADE", "r_multiple": 0.0})

    replay.replay_frames(m5, m15, "BTC", start_time=m5.iloc[120].datetime, end_time=m5.iloc[125].datetime)

    assert seen
    assert all(m5_len <= 100 for m5_len, _, _ in seen)
    assert all(m15_len <= 100 for _, m15_len, _ in seen)
    assert all(index is None for _, _, index in seen)
