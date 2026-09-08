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
from . import opportunity_lifecycle as _opportunity_lifecycle_module
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
from .opportunity_lifecycle_promotion import install as _install_opportunity_lifecycle_promotion
from .p0_opportunity_integrity import install as _install_p0_opportunity_integrity
from .opportunity_lifecycle_contract_surgery import install as _install_lifecycle_contract_surgery

_install_bootstrap_surgery(_pipeline_module)
try:
    _install_mtf_runtime(_pipeline_module, _market_data_module)
except ModuleNotFoundError as exc:
    if getattr(exc, "name", None) != "lse":
        raise
_install_e2_opportunity_book(_pipeline_module, _e2_module)
_install_e6_runtime_authority(_e6_module)
_pipeline_module.analyze_e6 = _e6_module.analyze_e6
_pipeline_module._E6_RUNTIME_OVERRIDE = _e6_module.analyze_e6
_install_e8_applicability_boundary(_e8_module)
_pipeline_module.analyze_e8 = _e8_module.analyze_e8
_install_e9_watch_boundary(_e9_module)
_install_e9_thesis_contract(_e9_module)
_install_evidence_collaboration(_e6_module, _e9_module)
_pipeline_module.analyze_e9 = _e9_module.analyze_e9
_install_e7_thesis_boundary(_pipeline_module)
_install_final_runtime_binding(_pipeline_module, _e6_module, _e8_module, _e9_module)
_install_runtime_trace_boundary(_pipeline_module)
_install_opportunity_lifecycle_runtime(_pipeline_module)
_install_terminal_opportunity_runtime(_pipeline_module)
_install_lifecycle_contract_surgery(_opportunity_lifecycle_module, _pipeline_module)
_install_professional_opportunity(_professional_opportunity_module, _pipeline_module)
_install_opportunity_timing_hotfix(_pipeline_module)
_install_opportunity_lifecycle_timing(_pipeline_module)
_install_opportunity_lifecycle_promotion()
_install_p0_opportunity_integrity(_pipeline_module)

if not getattr(_pipeline_module, "_LIFECYCLE_COMPATIBILITY_ADAPTER", False):
    def _lifecycle_current_compat(results, decision, gate_passed, candle):
        e6_result = results.get("E6") if isinstance(results, dict) else None
        e6 = e6_result.output if hasattr(e6_result, "output") and isinstance(e6_result.output, dict) else {}
        direction = str(e6.get("direction") or "NEUTRAL").upper().strip()
        missing = list(e6.get("missing_proof") or [])
        event_id = e6.get("event_id") or e6.get("origin_event_id")
        return {"candidate": bool(e6.get("setup") or e6.get("setup_family") or e6.get("setup_exists") or missing), "direction": direction, "setup": str(e6.get("setup") or e6.get("setup_family") or "OPPORTUNITY_WATCH").upper().strip(), "event_id": event_id, "wait_for": missing, "candle": candle, "ready": bool(decision == "TRADE" and gate_passed), "trade_authorized": False, "lifecycle_source": "E6_SETUP"}
    _pipeline_module._lifecycle_current = _lifecycle_current_compat
    _pipeline_module._LIFECYCLE_COMPATIBILITY_ADAPTER = True

if not getattr(_pipeline_module, "_E8_EXECUTION_BOUNDARY_ADAPTER", False):
    def _normalize_e8_execution_boundary(result):
        if result is None:
            return None
        output = dict(getattr(result, "output", {}) or {})
        specialists = output.get("specialists") if isinstance(output.get("specialists"), dict) else {}
        specialist_8g = specialists.get("8G") if isinstance(specialists.get("8G"), dict) else {}
        specialist_output = specialist_8g.get("output") if isinstance(specialist_8g.get("output"), dict) else {}
        if specialist_output:
            for key in ("trade_plan", "plan_status", "risk_gate", "risk_basis", "direction"):
                if key in specialist_output:
                    output[key] = specialist_output[key]
        return type(result)(result.engine_id, result.name, result.gate_passed, result.confidence, output, result.reason_codes)
    _pipeline_module._normalize_e8_execution_boundary = _normalize_e8_execution_boundary
    _pipeline_module._E8_EXECUTION_BOUNDARY_ADAPTER = True

if not getattr(_pipeline_module, "_E6_SAFE_INPUT_ADAPTER", False):
    _e6_public_original = _pipeline_module.analyze_e6
    def _safe_analyze_e6(snapshot, upstream):
        safe_snapshot = snapshot if isinstance(snapshot, dict) else {}
        result = _e6_public_original(safe_snapshot, upstream)
        output = dict(getattr(result, "output", {}) or {})
        if output.get("candidate_type") == "EARLY_OPPORTUNITY_CANDIDATE":
            output["timing_candidate_type"] = output["candidate_type"]
            output["candidate_type"] = "OPPORTUNITY_CANDIDATE"
        return type(result)(result.engine_id, result.name, result.gate_passed, result.confidence, output, result.reason_codes)
    _safe_analyze_e6.__name__ = "safe_analyze_e6"
    _pipeline_module.analyze_e6 = _safe_analyze_e6
    _pipeline_module._E6_RUNTIME_OVERRIDE = _safe_analyze_e6
    _pipeline_module._E6_SAFE_INPUT_ADAPTER = True

if not getattr(_e9_module, "_E9_WATCH_GOVERNANCE_COMPAT", False):
    _e9_public_original = _e9_module.analyze_e9
    def _e9_governance_compat(snapshot, upstream):
        result = _e9_public_original(snapshot, upstream)
        output = dict(getattr(result, "output", {}) or {})
        e6 = dict(getattr(upstream.get("E6"), "output", {}) or {}) if isinstance(upstream, dict) else {}
        setup = str(e6.get("setup") or "").upper().strip()
        if output.get("final_governance") == "WATCH" and setup in {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}:
            output["governance_reason"] = "WAITING_FOR_E6_SETUP_THESIS"
        return type(result)(result.engine_id, result.name, result.gate_passed, result.confidence, output, result.reason_codes)
    _e9_module.analyze_e9 = _e9_governance_compat
    _pipeline_module.analyze_e9 = _e9_module.analyze_e9
    _e9_module._E9_WATCH_GOVERNANCE_COMPAT = True

try:
    from . import app as _app_module
    if not hasattr(_app_module, "reconcile_causal_evidence"):
        def _reconcile_causal_evidence(_engines):
            return {"state": "UNKNOWN", "direction": "NEUTRAL", "wait_for": []}
        _app_module.reconcile_causal_evidence = _reconcile_causal_evidence
except Exception:
    pass

if not getattr(_pipeline_module, "_LIFECYCLE_SOURCE_METADATA", False):
    _original_directional_lifecycle_current = _pipeline_module._directional_lifecycle_current
    def _directional_lifecycle_current_with_source(*args, **kwargs):
        current, leader, competition = _original_directional_lifecycle_current(*args, **kwargs)
        results = args[0] if args and isinstance(args[0], dict) else kwargs.get("results") or {}
        e6_result = results.get("E6") if isinstance(results, dict) else None
        e6 = dict(getattr(e6_result, "output", {}) or {}) if e6_result is not None else {}
        e6_setup = str(e6.get("setup") or e6.get("setup_family") or "").upper().strip()
        e6_concrete = bool(e6.get("setup_exists")) or (e6_setup not in {"", "OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS", "UNKNOWN", "NONE", "NO_SETUP"} and e6.get("setup_state") not in {"", "NO_SETUP", "UNKNOWN", "NONE"})
        for direction, payload in current.items():
            if not isinstance(payload, dict) or not payload.get("candidate"):
                continue
            payload["lifecycle_source"] = "E6_SETUP" if e6_concrete and direction == str(e6.get("direction") or "").upper().strip() else "E2_OPPORTUNITY_BOOK"
        return current, leader, competition
    _pipeline_module._directional_lifecycle_current = _directional_lifecycle_current_with_source
    _pipeline_module._LIFECYCLE_SOURCE_METADATA = True

__all__ = ["ProductionPipeline"]