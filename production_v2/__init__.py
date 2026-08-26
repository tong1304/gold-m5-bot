"""Production-v2: isolated nine-engine trading runtime."""

from trading_system.core import subengine as _subengine
from trading_system.core.professional_subengine import ProfessionalSubEngine
_subengine.SubEngine = ProfessionalSubEngine

from .pipeline import ProductionPipeline

__all__ = ["ProductionPipeline"]
