from __future__ import annotations

import pandas as pd

from control_app.backtest.data import gold_market_open
from control_app.backtest.engine import run_backtest


def fixture_frames(symbol, start, end, api_key=None):
    base = pd.date_range(end=pd.Timestamp(end), periods=180, freq="5min", tz="UTC")
    def frame(freq):
        idx = pd.date_range(end=base[-1], periods=180, freq=freq, tz="UTC")
        price = pd.Series(range(100, 100 + len(idx)), dtype=float)
        return pd.DataFrame({"datetime": idx, "open": price, "high": price + 0.5, "low": price - 0.5, "close": price + 0.1})
    return {"5m": frame("5min"), "15m": frame("15min"), "1h": frame("1h")}


def test_backtest_uses_isolated_replay_and_marks_no_live_side_effects():
    result = run_backtest(
        "BTC",
        pd.Timestamp("2026-08-01", tz="UTC").to_pydatetime(),
        pd.Timestamp("2026-08-02", tz="UTC").to_pydatetime(),
        run_id="TEST-1",
        data_loader=fixture_frames,
    )
    assert result.run_id == "TEST-1"
    assert result.metadata["lookahead_safe"] is True
    assert result.metadata["live_orders_allowed"] is False
    assert result.metadata["telegram_alert_sent"] is False
    assert "strategy_breakdown" in result.statistics


def test_gold_market_session_has_daily_break():
    closed, reason = gold_market_open(pd.Timestamp("2026-08-25 17:30", tz="America/New_York"))
    assert closed is False
    assert reason == "DAILY_BREAK"
