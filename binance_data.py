"""Backward-compatible name for the XM MT5 market-data adapter."""
from mt5_data import XMMarketData


class BinanceMarketData(XMMarketData):
    """Compatibility shim: all live market data comes from XM MT5.

    The old class name is retained so existing scanner code does not change,
    but this adapter never connects to Binance. Candle reads are normalized to
    CLOSED candles before they reach the signal engine.
    """

    _TIMEFRAME_MINUTES = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        frame = super().fetch_candles(symbol, timeframe, limit)
        minutes = self._TIMEFRAME_MINUTES.get(str(timeframe).lower())
        if minutes is None:
            raise ValueError(f"Unsupported timeframe for XM closed-candle filtering: {timeframe}")
        return self.remove_incomplete_last_candle(frame, timeframe_minutes=minutes)
