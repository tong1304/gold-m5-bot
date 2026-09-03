"""Production-v2: isolated nine-engine trading runtime.

Runtime installation order is intentional: bootstrap wrappers are installed
first, then the final E6/E8/E9 boundaries are installed and rebound into the
pipeline. This prevents app-level bootstrap initialization from replacing the
final governance contracts.
"""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from . import e8_brain as _e8_module
from . import e9_brain as _e9_module
from .bootstrap_surgery import install as _install_bootstrap_surgery
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e6_pending_counterflow_runtime import install as _install_e6_pending_counterflow_runtime
from .e6_opportunity_guard import install as _install_e6_opportunity_guard
from .e8_applicability_boundary import install as _install_e8_applicability_boundary
from .e9_watch_boundary import install as _install_e9_watch_boundary

# Bootstrap surgery must be the innermost runtime wrapper. app.py may call the
# same installer again, but its own idempotence guard makes that call a no-op.
_install_bootstrap_surgery(_pipeline_module)

# Install final E6 guards after bootstrap, then rebind pipeline's imported
# function reference. E6 remains the sole owner of the causal thesis boundary.
_install_e6_pending_counterflow_runtime(_e6_module)
_install_e6_opportunity_guard(_e6_module)
_pipeline_module.analyze_e6 = _e6_module.analyze_e6

# E8 applicability is the outer boundary around any bootstrap economics.
_install_e8_applicability_boundary(_e8_module)
_pipeline_module.analyze_e8 = _e8_module.analyze_e8

# E9 watch governance is the final boundary; rebind it last.
_install_e9_watch_boundary(_e9_module)
_pipeline_module.analyze_e9 = _e9_module.analyze_e9

# E7 is pipeline-owned because it consumes the E6 thesis boundary.
_install_e7_thesis_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
