import numpy as np
import pandas as pd

from v11.regime import build_regime_context


def candles(n=140, start=100.0, drift=0.08):
    close = start + np.arange(n) * drift + np.sin(np.arange(n) / 3.0) * 0.15
    open_ = close - 0.03
    high = np.maximum(open_, close) + 0.08
    low = np.minimum(open_, close) - 0.08
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": np.ones(n)})


def test_build_regime_context_exposes_normalized_metrics():
    ctx = build_regime_context(candles(140, drift=0.12), candles(120, drift=0.20))
    assert ctx["m15_direction"] in {"BUY", "SELL", "NEUTRAL"}
    assert ctx["atr"] > 0
    assert 0 <= ctx["body_ratio"] <= 1
    assert ctx["range_ratio"] >= 0


def test_build_regime_context_is_deterministic():
    m5 = candles(140, drift=0.05)
    m15 = candles(120, drift=0.10)
    assert build_regime_context(m5, m15) == build_regime_context(m5, m15)
