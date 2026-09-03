"""Production-v2: isolated nine-engine trading runtime."""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e6_pending_counterflow_runtime import install as _install_e6_pending_counterflow_runtime

_install_e6_pending_counterflow_runtime(_e6_module)
# pipeline.py imports analyze_e6 by function reference. Rebind that reference
# after the E6 runtime surgery so production uses the patched analyzer rather
# than the pre-surgery legacy function object.
_pipeline_module.analyze_e6 = _e6_module.analyze_e6
_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
