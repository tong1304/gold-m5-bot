import pandas as pd
from v11.engine import analyze, detect_m15_trend, get_strategy_registry, ENGINE_VERSION


def candles(n=140, start=100.0, step=0.2):
    rows=[]
    for i in range(n):
        o=start+i*step; c=o+step; rows.append({"open":o,"high":c+0.2,"low":o-0.1,"close":c,"volume":1})
    return pd.DataFrame(rows)


def test_registries_are_asset_specific():
    assert len(get_strategy_registry("BTC")) == 5
    assert len(get_strategy_registry("GOLD")) == 6
    assert "LIQUIDITY_SWEEP" not in get_strategy_registry("BTC")
    assert "EMA_PULLBACK" in get_strategy_registry("GOLD")


def test_m15_trend_is_directional_or_neutral():
    result=detect_m15_trend(candles())
    assert result["direction"] in {"BUY","SELL","NEUTRAL"}


def test_engine_returns_v11_schema_and_no_trade_when_alignment_is_not_proven():
    m5=candles(); m15=candles()
    result=analyze(m5,m15,"BTC")
    assert result["engine_version"] == ENGINE_VERSION
    assert result["signal"] in {"BUY","SELL","NO_TRADE"}
    assert "strategy_candidates" in result
    if result["signal"] == "NO_TRADE":
        assert result["trade_levels"]["valid"] is False
