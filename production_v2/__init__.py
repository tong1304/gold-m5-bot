"""Production-v2: isolated nine-engine trading runtime."""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e6_pending_counterflow_runtime import install as _install_e6_pending_counterflow_runtime

_install_e6_pending_counterflow_runtime(_e6_module)
_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
