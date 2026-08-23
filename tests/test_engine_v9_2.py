"""V9.2 H1 decision tests."""
import pandas as pd
import engine_v9_2 as engine


def _frame(closes):
    return pd.DataFrame({"open": closes, "high": [x + 1 for x in closes], "low": [x - 1 for x in closes], "close": closes, "volume": [1.0] * len(closes)})


def test_h1_buy_requires_structure_and_ema_alignment():
    closes = list(range(100, 151))
    result = engine._h1_decision(_frame(closes))
    assert result["bias"] == "BUY"
    assert result["ema_context"] == "BUY"
    assert result["decision"] == "BUY"
    assert result["volatility_state"] == "NORMAL"


def test_h1_neutral_when_structure_and_ema_conflict():
    closes = list(range(150, 100, -1)) + [150]
    result = engine._h1_decision(_frame(closes))
    assert result["bias"] == "SELL"
    assert result["ema_context"] == "BUY"
    assert result["decision"] == "NEUTRAL"


def test_h1_neutral_when_volatility_is_extreme():
    closes = list(range(100, 151))
    frame = _frame(closes)
    frame.loc[len(frame) - 1, "high"] = 200
    frame.loc[len(frame) - 1, "low"] = 50
    result = engine._h1_decision(frame)
    assert result["volatility_state"] == "EXTREME"
    assert result["decision"] == "NEUTRAL"
