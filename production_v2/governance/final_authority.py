"""Canonical E9 final-authority boundary.

This module deliberately delegates the existing, tested governance rules to the
legacy compatibility implementation during migration.  The public boundary is
E9-only: audit/enrichment layers may provide evidence, but they cannot become a
second trade authority.
"""

from ..professional_governance import enforce_final_authority

__all__ = ["enforce_final_authority"]
