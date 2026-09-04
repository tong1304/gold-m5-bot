"""Production-v2: isolated nine-engine trading runtime.

E6 is a single authoritative specialist: ``production_v2.e6_brain.analyze_e6``
is bound directly into the pipeline. Compatibility modules may expose helper
functions, but no E6 wrapper is installed at package startup.
"""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e6_brain as _e6_module
from . import e8_brain as _e8_module
from . import e9_brain as _e9_module
from . import market_data as _market_data_module
from .bootstrap_surgery import install as _install_bootstrap_surgery
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e8_applicability_boundary import install as _install_e8_applicability_boundary
from .e9_watch_boundary import install as _install_e9_watch_boundary
from .mtf_runtime import install as _install_mtf_runtime
from .final_runtime_binding import install as _install_final_runtime_binding
from .evidence_collaboration_runtime import install as _install_evidence_collaboration
from .e9_thesis_contract import install as _install_e9_thesis_contract
from .runtime_trace_boundary import install as _install_runtime_trace_boundary

_install_bootstrap_surgery(_pipeline_module)
_install_mtf_runtime(_pipeline_module, _market_data_module)

# E6 single authority: no pending-counterflow, opportunity-guard, or runtime
# authority monkey-patch is installed. Those modules remain compatibility
# helpers only and cannot replace the authoritative E6 callable.
_pipeline_module.analyze_e6 = _e6_module.analyze_e6

_install_e8_applicability_boundary(_e8_module)
_pipeline_module.analyze_e8 = _e8_module.analyze_e8

_install_e9_watch_boundary(_e9_module)
_install_e9_thesis_contract(_e9_module)
_pipeline_module.analyze_e9 = _e9_module.analyze_e9

# Evidence collaboration may enrich E9's ledger but never wraps E6.
_install_evidence_collaboration(_e6_module, _e9_module)

_install_e7_thesis_boundary(_pipeline_module)
_install_final_runtime_binding(_pipeline_module, _e6_module, _e8_module, _e9_module)
_install_runtime_trace_boundary(_pipeline_module)

__all__ = ["ProductionPipeline"]
