"""Production E3 entrypoint — V7 professional market-structure brain.

E3 remains analysis-only. E1/E2 and E4-E9 are not modified.
Legacy regression helpers remain exported for compatibility; production
analysis itself is delegated to V7.
"""

from .e3_brain_v7 import analyze_e3
from .e3_brain_v6 import _compress, _bos, _sweep_failure

__all__ = ["analyze_e3", "_compress", "_bos", "_sweep_failure"]
