"""Production-V2 E4 entrypoint.

V9 is the sole active E4 professional brain. Legacy 4A-4F specialists are
paused and are not invoked here. E4 is analysis-only and cannot gate or trade.
"""
from .e4_brain_v9 import analyze_e4

__all__=["analyze_e4"]
