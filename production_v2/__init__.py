"""Production-v2: isolated nine-engine trading runtime.

E6 is the single authoritative opportunity/setup specialist. Compatibility
membranes may enrich its output, but E9 remains the sole execution authority.
"""

from .pipeline import ProductionPipeline
from . import pipeline as _pipeline_module
from . import e2_brain as _e2_module
from . import e6_brain as _e6_module
from . import e8_brain as _e8_module
from . import e9_brain as _e9_module
from . import market_data as _market_data_module
from . import professional_opportunity as _professional_opportunity_module
from .bootstrap_surgery import install as _install_bootstrap_surgery
from .e2_runtime_binding import install as _install_e2_opportunity_book
from .e6_runtime_authority import install as _install_e6_runtime_authority
from .e7_thesis_boundary import install as _install_e7_thesis_boundary
from .e8_applicability_boundary import install as _install_e8_applicability_boundary
from .e9_watch_boundary import install as _install_e9_watch_boundary
from .mtf_runtime import install as _install_mtf_runtime
from .final_runtime_binding import install as _install_final_runtime_binding
from .evidence_collaboration_runtime import install as _install_evidence_collaboration
from .e9_thesis_contract import install as _install_e9_thesis_contract
from .runtime_trace_boundary import install as _install_runtime_trace_boundary
from .opportunity_lifecycle_runtime import install as _install_opportunity_lifecycle_runtime
from .professional_opportunity_surgery import install as _install_professional_opportunity
from .terminal_opportunity_runtime import install as _install_terminal_opportunity_runtime
from .opportunity_timing_runtime_hotfix import install as _install_opportunity_timing_hotfix
from .opportunity_lifecycle_timing import install as _install_opportunity_lifecycle_timing

_install_bootstrap_surgery(_pipeline_module)
_install_mtf_runtime(_pipeline_module, _market_data_module)

# E2 opportunity intelligence: preserve conditional BUY/SELL watches without
# authorizing entry, trigger, decision, or execution.
_install_e2_opportunity_book(_pipeline_module, _e2_module)

# E6 runtime membrane is installed on the authoritative E6 module and then
# explicitly registered as the pipeline runtime override. This makes the
# opportunity-timing membrane live in the same callable used by production.
_install_e6_runtime_authority(_e6_module)
_pipeline_module.analyze_e6 = _e6_module.analyze_e6
_pipeline_module._E6_RUNTIME_OVERRIDE = _e6_module.analyze_e6

_install_e8_applicability_boundary(_e8_module)
_pipeline_module.analyze_e8 = _e8_module.analyze_e8

_install_e9_watch_boundary(_e9_module)
_install_e9_thesis_contract(_e9_module)
_pipeline_module.analyze_e9 = _e9_module.analyze_e9

# Evidence collaboration may enrich E9's ledger but never grants E6/E7/E8
# execution authority.
_install_evidence_collaboration(_e6_module, _e9_module)

_install_e7_thesis_boundary(_pipeline_module)
_install_final_runtime_binding(_pipeline_module, _e6_module, _e8_module, _e9_module)
_install_runtime_trace_boundary(_pipeline_module)
_install_opportunity_lifecycle_runtime(_pipeline_module)
_install_terminal_opportunity_runtime(_pipeline_module)

# Professional opportunity is observational only. It exposes the canonical
# E2 directional BUY/SELL radar while preserving E9 as execution authority.
_install_professional_opportunity(_professional_opportunity_module, _pipeline_module)

# Final runtime hotfix: repair stale zero-valued E6 fields by sourcing timing
# evidence from the authoritative E4/E5 upstream results, and hand every
# EARLY opportunity to E7 for confirmation without granting trade authority.
_install_opportunity_timing_hotfix(_pipeline_module)

# Lifecycle membrane: preserve FAST/STANDARD/SLOW timing semantics after the
# pipeline's imported lifecycle function normalizes opportunity state. This is
# observational only; E9 remains the sole execution authority.
_install_opportunity_lifecycle_timing(_pipeline_module)

__all__ = ["ProductionPipeline"]
