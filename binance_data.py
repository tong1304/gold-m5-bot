"""Backward-compatible name for the XM MT5 market-data adapter."""
from mt5_data import XMMarketData


class BinanceMarketData(XMMarketData):
    """Compatibility shim: all market data now comes from XM MT5."""

    pass
