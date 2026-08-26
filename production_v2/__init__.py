"""Production-v2: isolated nine-engine trading runtime."""

from trading_system.core import subengine as _subengine
from trading_system.core.professional_subengine import ProfessionalSubEngine
_subengine.SubEngine = ProfessionalSubEngine

# Install the E9 evidence-consistency guard before pipeline imports its
# decision function. E1-E8 remain evidence-only; E9 remains sole authority.
from . import e9_consistency_patch as _e9_consistency_patch

from .pipeline import ProductionPipeline

__all__ = ["ProductionPipeline"]
