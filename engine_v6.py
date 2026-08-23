"""Compatibility entry point for the current Structure V7 engine.

The public application still imports ``engine_v6`` for compatibility, but the
actual strategy is Structure V7. Keep all runtime configuration aliases here
explicit so callers do not depend on names imported through ``import *``.
"""
import os

import engine_v7 as _v7
from engine_v7 import *  # noqa: F401,F403 - preserve legacy engine_v6 API
from engine_v7 import app

ENGINE_VERSION = "7.0"
engine_version = ENGINE_VERSION

# Explicit compatibility/runtime aliases.  app.py, replay and older modules
# are allowed to set these per symbol at runtime.
MINIMUM_ATR = float(os.getenv("MINIMUM_ATR", "0.50"))
MIN_STOP_ATR = float(os.getenv("MIN_STOP_ATR", "1.00"))
MAX_STOP_ATR = float(os.getenv("MAX_STOP_ATR", "3.00"))
SPREAD = float(os.getenv("SPREAD", "0.20"))
SLIPPAGE = float(os.getenv("SLIPPAGE", "0.05"))
SIGNAL_HISTORY_POINTS = int(os.getenv("SIGNAL_HISTORY_POINTS", "200"))
MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
RISK_REWARD = max(float(os.getenv("RISK_REWARD", str(MIN_RISK_REWARD))), 2.0)
FORWARD_BARS = int(os.getenv("FORWARD_BARS", "24"))

# Keep the underlying V7 module synchronized when a legacy caller changes a
# configuration attribute directly on engine_v6.
base = _v7.base
