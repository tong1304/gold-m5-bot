"""V12 MTF engine with dedicated BTC B1-B3 and GOLD G1-G3 strategies."""
from . import engine as _engine
from .engine_gold import analyze as _gold_analyze
from .strategy_engine import ENGINE_NAMES
from .professional_decision import wrap as _wrap_professional_decision

# Keep the public engine module used by scheduler/live scanner, but route GOLD
# through its dedicated G-series and keep BTC on B1-B3 only.
_original_analyze = _engine.analyze
LEGACY_ENGINE_VERSION = _engine.ENGINE_VERSION
ENGINE_VERSION = "PROFESSIONAL-DECISION-9E-v1.0"

# E1-E8 remain specialist evidence producers. The wrapper gives E9 the only
# system-level authority to emit BUY/SELL/NO_TRADE.
_engine.analyze = _wrap_professional_decision(_original_analyze, _gold_analyze)
_engine.ENGINE_VERSION = ENGINE_VERSION

analyze = _engine.analyze

__all__ = ["ENGINE_VERSION", "LEGACY_ENGINE_VERSION", "analyze", "ENGINE_NAMES"]
