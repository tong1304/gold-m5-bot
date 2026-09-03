"""Production-v2: isolated nine-engine trading runtime.

Runtime installation order is intentional: bootstrap wrappers are installed
first, M15/M5 snapshot routing is installed next, then final E6/E8/E9 guards
are installed and rebound into the pipeline. A final runtime binding membrane
reasserts those authority bindings immediately before each pipeline execution.
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
from .final_runtime_binding import install as _install_final_runtime_binding

# Bootstrap initializes before final authority guards.
_install_bootstrap_surgery(_pipeline_module)

# Freeze one M5 snapshot and route M15 context only to E1/E2.
_install_mtf_runtime(_pipeline_module, _market_data_module)

# E6 owns causal thesis formation.
_install_e6_pending_counterflow_runtime(_e6_module)
_install_e6_opportunity_guard(_e6_module)
_pipeline_module.analyze_e6 = _e6_module.analyze_e6

# E8 owns trade economics and is not applicable without a surviving E6 thesis.
_install_e8_applicability_boundary(_e8_module)
_pipeline_module.analyze_e8 = _e8_module.analyze_e8

# E9 owns final governance and watch-state governance.
_install_e9_watch_boundary(_e9_module)
_pipeline_module.analyze_e9 = _e9_module.analyze_e9

# E7 remains pipeline-owned because it consumes the E6 thesis boundary.
_install_e7_thesis_boundary(_pipeline_module)

# Last: guarantee that app/startup code cannot leave stale analyzer references
# in the live pipeline between initialization and the next closed candle.
_install_final_runtime_binding(_pipeline_module, _e6_module, _e8_module, _e9_module)

__all__ = ["ProductionPipeline"]
