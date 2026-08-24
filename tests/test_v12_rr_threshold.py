import pandas as pd

from v11 import risk


def _frame():
    rows = []
    for i in range(80):
        rows.append({
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


def test_v12_accepts_structure_tp_at_1_5r(monkeypatch):
    monkeypatch.setattr(risk, "atr14", lambda df: pd.Series([1.0] * len(df)))
    monkeypatch.setattr(risk, "_nearest_levels", lambda *args: (99.0, [101.65, 102.0]))

    result = risk.calculate(_frame(), "BUY", "E1_TREND")

    assert result["valid"] is True
    assert result["tp"] == 101.65
    assert result["risk_reward"] >= 1.5
    assert result["target_rr"] == 1.5


def test_v12_rejects_structure_tp_below_1_5r(monkeypatch):
    monkeypatch.setattr(risk, "atr14", lambda df: pd.Series([1.0] * len(df)))
    monkeypatch.setattr(risk, "_nearest_levels", lambda *args: (99.0, [101.4]))

    result = risk.calculate(_frame(), "BUY", "E1_TREND")

    assert result["valid"] is False
    assert result["reason"] == "STRUCTURE_RR_BELOW_1_5"


def test_v12_skips_sub_1_5_structure_and_uses_next_qualifying_tp(monkeypatch):
    monkeypatch.setattr(risk, "atr14", lambda df: pd.Series([1.0] * len(df)))
    monkeypatch.setattr(risk, "_nearest_levels", lambda *args: (99.0, [101.4, 101.65, 102.0]))

    result = risk.calculate(_frame(), "BUY", "E1_TREND")

    assert result["valid"] is True
    assert result["tp"] == 101.65
    assert result["risk_reward"] >= 1.5
