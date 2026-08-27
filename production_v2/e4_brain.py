"""Production-V2 E4 entrypoint.

V10 is the sole active E4 professional liquidity/auction brain. Legacy 4A-4F
specialists remain paused and are not invoked here. E4 is analysis-only and
cannot gate or authorize trades; E9 remains the sole decision authority.
"""
from .e4_brain_v9 import analyze_e4

__all__ = ["analyze_e4"]
