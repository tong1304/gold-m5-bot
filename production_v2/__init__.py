"""Production-v2: isolated nine-engine trading runtime."""

from trading_system.core import subengine as _subengine
from trading_system.core.professional_subengine import ProfessionalSubEngine
_subengine.SubEngine = ProfessionalSubEngine

# Install E2 opportunity guard before pipeline imports the engine dispatcher.
# E2 remains a single professional core; the guard only prevents trend context
# from being mislabeled as an opportunity without concrete setup evidence.
from . import e2_opportunity_patch as _e2_opportunity_patch

# Install the E9 evidence-consistency guard before pipeline imports its
# decision function. E1-E8 remain evidence-only; E9 remains sole authority.
from . import e9_consistency_patch as _e9_consistency_patch

from .pipeline import ProductionPipeline

__all__ = ["ProductionPipeline"]
