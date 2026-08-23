"""Compatibility shim for Structure V7.

The application still imports ``engine_v6`` for historical compatibility, but
there must be only ONE mutable engine module.  Previously ``engine_v6`` copied
configuration values from ``engine_v7``; changing ``engine_v6.SPREAD`` or
``engine_v6.SYMBOL`` therefore did not change the globals actually read by V7
functions.  This shim installs the compatibility names on the V7 module and
aliases the module object so all callers share the same runtime state.
"""
import os
import sys

import engine_v7 as _v7

# Explicit compatibility/runtime names expected by app.py, replay and older
# modules.  They are installed on the real V7 module, not on a second module
# namespace.
_v7.MINIMUM_ATR = float(os.getenv("MINIMUM_ATR", "0.50"))
_v7.MIN_STOP_ATR = float(os.getenv("MIN_STOP_ATR", "1.00"))
_v7.MAX_STOP_ATR = float(os.getenv("MAX_STOP_ATR", "3.00"))
_v7.SPREAD = float(os.getenv("SPREAD", "0.20"))
_v7.SLIPPAGE = float(os.getenv("SLIPPAGE", "0.05"))
_v7.SIGNAL_HISTORY_POINTS = int(os.getenv("SIGNAL_HISTORY_POINTS", "200"))
_v7.MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
_v7.RISK_REWARD = max(float(os.getenv("RISK_REWARD", str(_v7.MIN_RISK_REWARD))), 2.0)
_v7.FORWARD_BARS = int(os.getenv("FORWARD_BARS", "24"))
_v7.ENGINE_VERSION = "7.0"
_v7.engine_version = _v7.ENGINE_VERSION

# From this point on, ``import engine_v6`` returns the same module object as
# ``import engine_v7``.  Runtime assignments made by app.py/live_scanner/
# replay_signal_history therefore affect the globals used by V7 immediately.
sys.modules[__name__] = _v7
