import os
import tempfile
import pandas as pd
from v11.data_quality import validate_frame, require_closed
from v11.selection import select
from v11.risk import calculate
from signal_history import SignalHistory


def frame(n=80, start="2026-08-24 00:00:00"):
    ts = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    close = pd.Series(range(100, n + 100), dtype=float)
    return pd.DataFrame({"datetime": ts, "open": close - 0.2, "high": close + 1, "low": close - 1, "close": close})


def structure_frame(entry=180.0, support=170.0, resistance=205.0):
    df = frame(80)
    df.loc[70:74, "low"] = [support + 2, support + 1, support, support + 1, support + 2]
    df.loc[70:74, "high"] = [entry - 5, entry - 4, entry - 3, entry - 4, entry - 5]
    df.loc[70:74, "close"] = [entry - 10] * 5
    df.loc[75:79, "low"] = [entry + 1, entry + 2, entry + 3, entry + 2, entry + 1]
    df.loc[75:79, "high"] = [resistance - 2, resistance - 1, resistance, resistance - 1, resistance - 2]
    df.loc[75:79, "close"] = [entry + 1, entry + 2, entry + 3, entry + 2, entry]
    df.loc[79, "close"] = entry
    return df


def test_data_quality_rejects_duplicates_and_bad_ohlc():
    df = frame()
    df.loc[10, "datetime"] = df.loc[9, "datetime"]
    df.loc[20, "high"] = df.loc[20, "low"] - 1
    reasons = validate_frame(df, minimum=60, timeframe_minutes=5)
    assert "DUPLICATE_DATETIME" in reasons and "OHLC_INCONSISTENT" in reasons


def test_require_closed_removes_current_candle():
    df = frame()
    now = df.iloc[-1].datetime + pd.Timedelta(minutes=4)
    out = require_closed(df, timeframe_minutes=5, now=now)
    assert out.iloc[-1].datetime < now.floor("5min")


def test_selection_is_not_registry_order():
    candidates = [
        {"strategy": "Z", "direction": "BUY", "status": "PASS", "quality": 60, "freshness_bars": 2},
        {"strategy": "A", "direction": "BUY", "status": "PASS", "quality": 80, "freshness_bars": 3},
    ]
    assert select(candidates, "BUY")["strategy"] == "A"


def test_risk_requires_strategy_specific_structure_rr():
    df = structure_frame(entry=180, support=170, resistance=205)
    result = calculate(df, "BUY", "IMPULSE_PULLBACK")
    assert result["valid"]
    assert result["tp"] == 205
    assert result["risk_reward"] >= 1.5
    assert result["tp_levels"][0]["type"] == "TP1"


def test_risk_rejects_structure_below_strategy_rr_instead_of_extending_tp():
    df = structure_frame(entry=180, support=170, resistance=190)
    result = calculate(df, "BUY", "IMPULSE_PULLBACK")
    assert result["valid"] is False
    assert result["reason"] == "STRUCTURE_RR_BELOW_1.5"
    assert result["first_tp"] == 190
    assert result["first_tp_rr"] < 1.5


def test_risk_uses_structure_support_for_sell_tp():
    df = structure_frame(entry=180, support=155, resistance=190)
    result = calculate(df, "SELL", "IMPULSE_PULLBACK")
    assert result["valid"]
    assert result["tp"] == 155
    assert result["risk_reward"] >= 1.5


def test_risk_can_add_safe_tp_extensions_without_moving_primary_structure_tp():
    df = frame(80)
    df.loc[70:74, "low"] = [177, 176, 175, 176, 177]
    df.loc[70:74, "high"] = [179, 180, 181, 180, 179]
    df.loc[75:79, "low"] = [181, 182, 183, 182, 181]
    df.loc[75:79, "high"] = [193, 194, 195, 194, 193]
    df.loc[79, "close"] = 180.0
    result = calculate(df, "BUY", "IMPULSE_PULLBACK")
    assert result["valid"]
    assert result["tp"] == 195
    assert result["tp_levels"][0]["price"] == 195
    assert result["tp_levels"][0]["type"] == "TP1"
    assert all(p["risk_reward"] >= 1.5 for p in result["tp_levels"])


def test_risk_does_not_accept_target_price_override():
    df = structure_frame(entry=180, support=170, resistance=205)
    result = calculate(df, "BUY", "IMPULSE_PULLBACK", {"target_price": 9999})
    assert result["valid"]
    assert result["tp"] == 205


def test_history_dedup_is_atomic():
    with tempfile.TemporaryDirectory() as d:
        h = SignalHistory(os.path.join(d, "signals.db"))
        payload = {"signal_id": "X", "symbol": "BTC", "signal": "BUY", "closed_candle": "2026-08-24T00:00:00+00:00", "created_at": "2026-08-24T00:05:00+00:00", "trade_levels": {"entry": 100, "sl": 99, "tp": 102}}
        assert h.record_signal(payload) is True
        assert h.record_signal(payload) is False
        assert h.get("X")["result"] == "OPEN"
