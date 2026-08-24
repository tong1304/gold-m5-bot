import numpy as np
import pandas as pd

from v11 import engine


def candles(n=140, start=100.0, drift=0.08):
    close = start + np.arange(n) * drift + np.sin(np.arange(n) / 3.0) * 0.15
    open_ = close - 0.03
    high = np.maximum(open_, close) + 0.08
    low = np.minimum(open_, close) - 0.08
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": np.ones(n)})


def test_engine_attaches_regime_without_composite_score():
    result = engine.analyze(candles(140, drift=0.05), candles(120, drift=0.10), "BTC", index=None)
    assert "regime" in result
    assert "strategy_candidates" in result
    assert all("score" not in candidate for candidate in result["strategy_candidates"])


def test_engine_keeps_structure_risk_contract():
    result = engine.analyze(candles(140, drift=0.12), candles(120, drift=0.20), "BTC", index=None)
    assert "trade_levels" in result
    if result["trade_levels"].get("valid"):
        assert result["trade_levels"]["rr"] >= engine.MIN_RISK_REWARD
