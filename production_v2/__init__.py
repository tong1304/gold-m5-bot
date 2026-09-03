"""Production-v2: isolated nine-engine trading runtime."""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from . import e8_brain as _e8_module
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e6_pending_counterflow_runtime import install as _install_e6_pending_counterflow_runtime
from .e6_opportunity_guard import install as _install_e6_opportunity_guard
from .e8_applicability_boundary import install as _install_e8_applicability_boundary

_install_e6_pending_counterflow_runtime(_e6_module)
_install_e6_opportunity_guard(_e6_module)
# pipeline.py imports analyze_e6 by function reference. Rebind only after all
# E6 runtime guards are installed so production executes the final analyzer.
_pipeline_module.analyze_e6 = _e6_module.analyze_e6

_install_e8_applicability_boundary(_e8_module)
# pipeline.py also imports analyze_e8 by function reference. Rebind after the
# applicability guard so E8 cannot evaluate economics without an E6 thesis.
_pipeline_module.analyze_e8 = _e8_module.analyze_e8

_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
