import numpy as np
import pandas as pd

from v11.strategies.multi_strategy import (
    liquidity_sweep,
    trend_pullback,
    vwap_mean_reversion,
    opening_range_breakout,
)


def candles(n=100, start=100.0, drift=0.0):
    close = start + np.arange(n) * drift
    open_ = close - 0.02
    high = np.maximum(open_, close) + 0.05
    low = np.minimum(open_, close) - 0.05
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": np.ones(n)})


def test_trend_pullback_rejects_weak_trend():
    frame = candles(100, drift=0.0)
    result = trend_pullback(frame, "BUY", {"m15": {"direction": "BUY"}, "regime": {"trend_strength": 0.10}})
    assert result.status == "FAIL"
    assert "TREND_STRENGTH_TOO_WEAK" in result.reasons


def test_liquidity_sweep_rejects_strong_countertrend():
    frame = candles(100, drift=0.10)
    result = liquidity_sweep(frame, "BUY", {"m15": {"direction": "SELL"}, "regime": {"trend_strength": 1.20}})
    assert result.status == "FAIL"
    assert "STRONG_COUNTERTREND_SWEEP_REJECTED" in result.reasons


def test_vwap_reversion_rejects_strong_continuation():
    frame = candles(100, start=100.0, drift=0.30)
    result = vwap_mean_reversion(frame, "BUY", {"m15": {"direction": "NEUTRAL"}, "regime": {"trend_strength": 1.50}})
    assert result.status == "FAIL"
    assert "STRONG_TREND_CONTINUATION" in result.reasons


def test_opening_range_rejects_uncompressed_range():
    frame = candles(100, start=100.0, drift=0.05)
    result = opening_range_breakout(frame, "BUY", {"m15": {"direction": "BUY"}, "regime": {"compression_ratio": 1.10, "range_ratio": 2.0}})
    assert result.status == "FAIL"
    assert "OPENING_RANGE_NOT_COMPRESSED" in result.reasons
