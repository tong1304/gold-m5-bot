import pandas as pd

from binance_data import BinanceMarketData


def test_binance_5m_ohlcv_is_normalized_to_engine_schema():
    provider = BinanceMarketData()
    raw = [
        [1700000000000, "36000.1", "36010.2", "35990.0", "36005.5", "12.3"],
        [1700000300000, "36005.5", "36020.0", "36000.0", "36015.0", "10.1"],
    ]
    frame = provider.normalize_ohlcv(raw)

    assert list(frame.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert pd.api.types.is_datetime64_any_dtype(frame["datetime"])
    assert frame.iloc[-1]["close"] == 36015.0


def test_binance_provider_does_not_require_api_keys_for_market_data():
    provider = BinanceMarketData()
    assert provider.api_key == ""
    assert provider.secret == ""
    assert provider.exchange.id == "binance"
