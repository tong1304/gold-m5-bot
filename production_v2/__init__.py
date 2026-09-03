"""Production-v2: isolated nine-engine trading runtime.

Runtime installation order is intentional: bootstrap wrappers are installed
first, M15/M5 snapshot routing is installed next, then final E6/E8/E9 guards
are installed and rebound into the pipeline. This prevents app-level startup
wrappers from replacing final authority boundaries.
"""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from . import e8_brain as _e8_module
from . import e9_brain as _e9_module
from . import market_data as _market_data_module
from .bootstrap_surgery import install as _install_bootstrap_surgery
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e6_pending_counterflow_runtime import install as _install_e6_pending_counterflow_runtime
from .e6_opportunity_guard import install as _install_e6_opportunity_guard
from .e8_applicability_boundary import install as _install_e8_applicability_boundary
from .e9_watch_boundary import install as _install_e9_watch_boundary
from .mtf_runtime import install as _install_mtf_runtime

# Bootstrap must initialize before final authority guards. Its pipeline
# analyzer wrappers are then superseded by the guarded module analyzers.
_install_bootstrap_surgery(_pipeline_module)

# Freeze one M5 snapshot and route M15 context only to E1/E2. The adapter also
# annotates every engine with its declared timeframe and snapshot identity.
_install_mtf_runtime(_pipeline_module, _market_data_module)

# E6 owns the causal thesis boundary.
_install_e6_pending_counterflow_runtime(_e6_module)
_install_e6_opportunity_guard(_e6_module)
_pipeline_module.analyze_e6 = _e6_module.analyze_e6

# E8 applicability remains a hard boundary around economics.
_install_e8_applicability_boundary(_e8_module)
_pipeline_module.analyze_e8 = _e8_module.analyze_e8

# E9 watch governance is the final decision boundary.
_install_e9_watch_boundary(_e9_module)
_pipeline_module.analyze_e9 = _e9_module.analyze_e9

# E7 is pipeline-owned because it consumes the E6 thesis boundary.
_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
