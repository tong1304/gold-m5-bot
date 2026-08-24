import pandas as pd

from v11.h1_gate import allows_trend_direction
from v11 import regime


def test_h1_buy_blocks_trend_sell_but_allows_buy():
    assert allows_trend_direction("BUY", "BUY") is True
    assert allows_trend_direction("BUY", "SELL") is False


def test_h1_sell_blocks_trend_buy_but_allows_sell():
    assert allows_trend_direction("SELL", "SELL") is True
    assert allows_trend_direction("SELL", "BUY") is False


def test_h1_neutral_does_not_force_trend_direction():
    assert allows_trend_direction("NEUTRAL", "BUY") is True
    assert allows_trend_direction("NEUTRAL", "SELL") is True


def test_h1_neutral_allows_m15_trend_to_decide(monkeypatch):
    m5 = pd.DataFrame({"close": [100.0] * 60})
    m15_info = {"regime": "TREND", "direction": "SELL", "adx14": 30.0}
    monkeypatch.setattr(regime, "_mtf_trend_direction", lambda h1: "NEUTRAL")
    monkeypatch.setattr(regime, "_classify_m15", lambda m15: m15_info)

    result = regime.classify_regime(m5, m5, m5)

    assert result["regime"] == "TREND"
    assert result["direction"] == "SELL"
    assert result["h1_bias"] == "NEUTRAL"
    assert result["h1_gate"]["directional_constraint"] is None


def test_h1_buy_conflicts_with_m15_sell_trend(monkeypatch):
    m5 = pd.DataFrame({"close": [100.0] * 60})
    m15_info = {"regime": "TREND", "direction": "SELL", "adx14": 30.0}
    monkeypatch.setattr(regime, "_mtf_trend_direction", lambda h1: "BUY")
    monkeypatch.setattr(regime, "_classify_m15", lambda m15: m15_info)

    result = regime.classify_regime(m5, m5, m5)

    assert result["regime"] == "CONFLICT"
    assert result["reason"] == "H1_BUY_BLOCKS_TREND_SELL"
