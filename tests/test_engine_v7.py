import pandas as pd
import numpy as np

import engine_v7 as e


def candles(n=140):
    idx = pd.date_range("2026-08-01", periods=n, freq="5min", tz="UTC")
    close = np.linspace(100, 120, n)
    return pd.DataFrame({
        "datetime": idx,
        "open": close - 0.2,
        "high": close + 0.4,
        "low": close - 0.4,
        "close": close,
        "volume": 1.0,
    })


def test_trade_levels_reject_less_than_two_r():
    df = candles()
    result = e.build_trade_levels(df, len(df)-1, "BUY", invalidation=118.0, target=121.0)
    assert result["valid"] is False
    assert result["reason"] == "RR_BELOW_2R"


def test_trade_levels_use_sweep_invalidation_and_liquidity_target():
    df = candles()
    result = e.build_trade_levels(df, len(df)-1, "BUY", invalidation=118.0, target=125.0)
    assert result["valid"] is True
    assert result["sl"] < result["entry"] < result["tp"]
    assert result["risk_reward"] >= 2.0


def test_resolve_same_candle_hits_is_ambiguous():
    future = pd.DataFrame([{"high": 105.0, "low": 95.0}])
    result = e.resolve_trade("BUY", 100.0, 95.0, 105.0, future)
    assert result[0] == "AMBIGUOUS"
