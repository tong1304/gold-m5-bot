"""Render-only market-data compatibility adapter backed by LSE.

The legacy BinanceMarketData class name is retained so existing scanner code
keeps working, but this adapter never connects to Binance, MT5, XM, a PC, or
VPS. All candles come from London Strategic Edge (LSE).
"""
from mt5_data import LSEMarketData


class BinanceMarketData(LSEMarketData):
    """Compatibility shim: all market data comes from LSE."""

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
            raise ValueError(f"Unsupported timeframe for LSE closed-candle filtering: {timeframe}")
        return self.remove_incomplete_last_candle(frame, timeframe_minutes=minutes)
