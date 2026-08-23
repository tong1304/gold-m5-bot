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


def test_bridge_url_is_required(monkeypatch):
    monkeypatch.delenv("MT5_BRIDGE_URL", raising=False)
    try:
        mt5_data.XMMarketData()
    except RuntimeError as exc:
        assert "MT5_BRIDGE_URL" in str(exc)
    else:
        raise AssertionError("expected missing bridge URL failure")
