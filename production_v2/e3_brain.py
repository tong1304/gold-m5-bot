"""Compatibility entrypoint for E3 V6.

The implementation lives in e3_brain_v6.py so the V6 brain can evolve
without mixing its structural contract with the legacy V5 implementation.
E3 remains a single brain; E1/E2 and E4-E9 are untouched.
"""

from .e3_brain_v6 import analyze_e3, _compress, _bos, _sweep_failure

__all__ = ["analyze_e3", "_compress", "_bos", "_sweep_failure"]
