import pandas as pd

import mt5_data


def test_symbol_mapping_uses_xm_defaults():
    assert mt5_data.MT5_SYMBOLS["BTC"] == "BTCUSD"
    assert mt5_data.MT5_SYMBOLS["GOLD"] == "XAUUSD"


def test_normalize_bridge_candles_returns_utc_ohlcv():
    payload = {
        "candles": [
            {"time": 1000, "open": 10, "high": 12, "low": 9, "close": 11, "tick_volume": 5},
            {"time": 1300, "open": 11, "high": 13, "low": 10, "close": 12, "tick_volume": 7},
        ]
    }
    frame = mt5_data.normalize_bridge_candles(payload)
    assert list(frame.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert str(frame["datetime"].dt.tz) == "UTC"


def test_remove_incomplete_last_candle_keeps_only_closed_bars():
    frame = pd.DataFrame({
        "datetime": pd.to_datetime([
            "2026-08-23 02:20:00+00:00",
            "2026-08-23 02:25:00+00:00",
            "2026-08-23 02:30:00+00:00",
        ], utc=True),
        "open": [1, 2, 3],
        "high": [2, 3, 4],
        "low": [0, 1, 2],
        "close": [1.5, 2.5, 3.5],
        "volume": [10, 11, 12],
    })
    closed = mt5_data.XMMarketData.remove_incomplete_last_candle(
        frame, now=pd.Timestamp("2026-08-23 02:27:30+00:00"), timeframe_minutes=5
    )
    assert closed["datetime"].tolist() == list(pd.to_datetime([
        "2026-08-23 02:20:00+00:00",
        "2026-08-23 02:25:00+00:00",
    ], utc=True))


def test_bridge_url_is_required(monkeypatch):
    monkeypatch.delenv("MT5_BRIDGE_URL", raising=False)
    try:
        mt5_data.XMMarketData()
    except RuntimeError as exc:
        assert "MT5_BRIDGE_URL" in str(exc)
    else:
        raise AssertionError("expected missing bridge URL failure")
