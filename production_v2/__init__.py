"""Production-v2: isolated nine-engine trading runtime."""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from .e7_thesis_boundary import install as _install_e7_thesis_boundary

_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
