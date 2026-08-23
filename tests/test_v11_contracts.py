import pandas as pd
from v11.contracts import StrategyResult
from v11.common import candle_metrics, atr14, momentum_move


def frame():
    return pd.DataFrame([
        {"open": 100, "high": 103, "low": 99, "close": 102, "volume": 1},
        {"open": 102, "high": 105, "low": 101, "close": 104, "volume": 1},
        {"open": 104, "high": 108, "low": 103, "close": 107, "volume": 1},
    ])


def test_strategy_result_is_structured():
    r = StrategyResult.pass_("MOMENTUM", "BUY", {"body_ratio": 0.75})
    assert r.status == "PASS"
    assert r.direction == "BUY"
    assert r.strategy == "MOMENTUM"
    assert r.evidence["body_ratio"] == 0.75


def test_candle_metrics_has_body_and_wicks_without_confirmation_flag():
    m = candle_metrics(frame().iloc[-1])
    assert m["body"] == 3
    assert m["range"] == 5
    assert m["body_ratio"] == 0.6
    assert "confirmation" not in m


def test_atr_and_momentum_are_available():
    x = pd.concat([frame()] * 8, ignore_index=True)
    assert atr14(x).iloc[-1] > 0
    assert momentum_move(x, 2) > 0
