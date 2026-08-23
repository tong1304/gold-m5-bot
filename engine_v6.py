"""Compatibility entry point. The trading system now runs Structure V7."""
from engine_v7 import *
from engine_v7 import app

# Compatibility aliases required by the existing multi-symbol runtime.
MINIMUM_ATR = float(os.getenv("MINIMUM_ATR", "0.50"))
MIN_STOP_ATR = float(os.getenv("MIN_STOP_ATR", "1.00"))
MAX_STOP_ATR = float(os.getenv("MAX_STOP_ATR", "3.00"))

ENGINE_VERSION = engine_version = "7.0"
