from __future__ import annotations

"""E4 — Professional Liquidity & Auction Brain.

Canonical top-level E4 brain entrypoint, kept at the same repository level as
``professional_e3_brain.py``.  The implementation remains the existing
single-brain E4 implementation in ``production_v2.e4_brain_v9`` so this
structural change does not duplicate or fork trading logic.

E4 is analysis-only: it reports liquidity, sweep, rejection, acceptance and
failed-break evidence. It does not authorize trades, apply gates, or emit a
trade decision; E9 remains the decision authority.
"""

from production_v2.e4_brain_v9 import (
    ARCHITECTURE,
    QUESTION,
    analyze_e4,
)

__all__ = ["ARCHITECTURE", "QUESTION", "analyze_e4"]
