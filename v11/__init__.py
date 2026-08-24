"""V12 MTF engine with dedicated BTC B1-B3 and GOLD G1-G5 strategies."""
from . import engine as _engine
from .engine_gold import analyze as _gold_analyze
from .strategy_engine import ENGINE_NAMES

# Keep the public engine module used by scheduler/live scanner, but route GOLD
# through its dedicated G-series and keep BTC on B1-B3 only.
_original_analyze = _engine.analyze
_ENGINE_VERSION = "12.4-MTF-H1-HARD-GATE-M15-M5-BTC-B1-B3-GOLD-G1-G5"
_engine.ENGINE_VERSION = _ENGINE_VERSION


def _analyze(m5, m15=None, symbol=None, index=None, setup_state=None, h1=None):
    normalized = str(symbol or "").upper()
    if normalized in ("GOLD", "XAU/USD", "XAU"):
        return _gold_analyze(m5, m15=m15, symbol=symbol, index=index, setup_state=setup_state, h1=h1)
    return _original_analyze(m5, m15=m15, symbol=symbol, index=index, setup_state=setup_state, h1=h1)


_engine.analyze = _analyze
ENGINE_VERSION = _ENGINE_VERSION
analyze = _analyze

__all__ = ["ENGINE_VERSION", "analyze", "ENGINE_NAMES"]
