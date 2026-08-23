"""Render-only market-data adapter backed by Twelve Data.

The legacy BinanceMarketData name is retained so existing scanner code keeps
working, but this adapter never connects to Binance, MT5, XM, a PC, or VPS.
"""
from mt5_data import TwelveDataMarketData


class BinanceMarketData(TwelveDataMarketData):
    """Compatibility shim: all market data comes from Twelve Data."""

    _TIMEFRAME_MINUTES = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "45m": 45,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "8h": 480,
        "1d": 1440,
    }

    def fetch_candles(self, symbol="BTC/USDT", timeframe="5m", limit=1000):
        frame = super().fetch_candles(symbol, timeframe, limit)
        minutes = self._TIMEFRAME_MINUTES.get(str(timeframe).lower())
        if minutes is None:
            raise ValueError(f"Unsupported timeframe for Twelve Data closed-candle filtering: {timeframe}")
        return self.remove_incomplete_last_candle(frame, timeframe_minutes=minutes)
