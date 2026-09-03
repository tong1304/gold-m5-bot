"""Production-v2: isolated nine-engine trading runtime."""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e6_pending_counterflow_runtime import install as _install_e6_pending_counterflow_runtime
from .e6_opportunity_guard import install as _install_e6_opportunity_guard

_install_e6_pending_counterflow_runtime(_e6_module)
_install_e6_opportunity_guard(_e6_module)
# pipeline.py imports analyze_e6 by function reference. Rebind only after all
# E6 runtime guards are installed so production executes the final analyzer.
_pipeline_module.analyze_e6 = _e6_module.analyze_e6
_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
