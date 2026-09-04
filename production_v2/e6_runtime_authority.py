from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .e6_opportunity_guard import _direction, _fallback_opportunity, _watch

WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
RUNTIME_AUTHORITY_VERSION = "E6_FINAL_OPPORTUNITY_MEMBRANE_V7"


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _falseish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (int, float)):
        return value == 0
    return str(value).strip().upper() in {"", "FALSE", "NO", "NONE", "NULL", "N/A", "NOT_READY"}


def _watch_marked(output: dict[str, Any]) -> bool:
    setup = str(output.get("setup") or "").upper().strip()
    candidate_type = str(output.get("candidate_type") or "").upper().strip()
    return setup in WATCH_SETUPS or candidate_type == "OPPORTUNITY_CANDIDATE" or output.get("watch_only") is True


def _has_no_setup(result: EngineResult) -> bool:
    out = _out(result)
    setup = str(out.get("setup") or "").upper().strip()
    finding = str(out.get("finding") or "").upper().strip()
    reasons = {str(code).upper().strip() for code in (*(out.get("reason_codes") or []), *(out.get("reasons") or []), *(result.reason_codes or ()))}
    legacy_no_causal_finding = "NO CAUSAL SETUP HYPOTHESIS" in finding or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding
    if legacy_no_causal_finding and _falseish(out.get("trade_ready")) and _falseish(out.get("gate_passed")):
        return True
    return setup in {"", "NO_SETUP", "UNKNOWN", "NONE"} and "NO_CAUSAL_OPPORTUNITY" in reasons


def _normalize_watch_semantics(output: dict[str, Any]) -> dict[str, Any]:
    """Normalize only genuine watch states; never downgrade a surviving setup thesis."""
    normalized = dict(output)
    if not _watch_marked(normalized) or not _falseish(normalized.get("trade_ready")):
        return normalized
    setup = str(normalized.get("setup") or "").upper().strip()
    if setup not in WATCH_SETUPS and normalized.get("watch_only") is not True:
        return normalized
    direction = _direction(normalized.get("direction"), normalized.get("bias"), normalized.get("market_direction"), normalized.get("thesis_direction"), normalized.get("direction_thesis"))
    if direction not in {"BUY", "SELL"}:
        direction = "NEUTRAL"
    stage = str(normalized.get("stage") or normalized.get("opportunity_stage") or normalized.get("thesis_status") or "FORMING").strip().upper()
    stage_text = {"FORMING":"forming","CONTESTED":"contested","VALIDATING":"being validated","WATCHING":"being watched"}.get(stage, stage.lower().replace("_", " "))
    normalized["setup"] = "OPPORTUNITY_WATCH"
    normalized["candidate_type"] = "OPPORTUNITY_CANDIDATE"
    normalized["watch_only"] = True
    normalized["trade_ready"] = False
    normalized["gate_passed"] = False
    normalized["trade_permission"] = False
    normalized["finding"] = f"{direction} opportunity is {stage_text}; causal setup is not yet proven." if direction != "NEUTRAL" else f"Opportunity is {stage_text}; causal setup is not yet proven."
    normalized["runtime_authority"] = RUNTIME_AUTHORITY_VERSION
    normalized["runtime_semantic_boundary"] = "WATCH_STATE_MUST_NOT_EXPOSE_LEGACY_SETUP_CLAIM"
    normalized.setdefault("next_required_event", "NEXT_CLOSED_M5_CANDLE")
    return normalized


def _runtime_watch_or_original(result: EngineResult, upstream: dict[str, EngineResult], thesis_builder=None) -> EngineResult:
    """Apply the final E6 membrane after every legacy and enrichment path."""
    out = _out(result)
    if _watch_marked(out) and _falseish(out.get("trade_ready")):
        normalized = _normalize_watch_semantics(out)
        return EngineResult(result.engine_id, result.name, False, result.score, normalized, result.reason_codes)
    if not _has_no_setup(result):
        return result

    candidate = _fallback_opportunity(upstream)
    if candidate is None:
        print(f"[PRODUCTION V2] E6_RUNTIME_MEMBRANE version={RUNTIME_AUTHORITY_VERSION} action=NO_RESCUE candidate=NONE", flush=True)
        return result

    # A causal E1-E5 candidate is an E6 setup thesis, not a generic watch.
    # It remains non-trade-ready until E7 and E8 prove their own gates.
    if thesis_builder is not None:
        thesis = thesis_builder(result, candidate)
    else:
        thesis = _watch(result, candidate)
    thesis_out = _normalize_watch_semantics(dict(thesis.output or {}))
    thesis_out["runtime_rescue_reason"] = "CAUSAL_E1_E5_EVIDENCE_SURVIVES_LEGACY_NO_SETUP"
    thesis_out["runtime_direction_source"] = _direction(candidate.get("direction"))
    thesis_out["runtime_candidate_family"] = candidate.get("family")
    thesis_out["runtime_candidate_event_id"] = candidate.get("event_id")
    return EngineResult(thesis.engine_id, thesis.name, False, thesis.score, thesis_out, thesis.reason_codes)


def install(e6_module) -> None:
    if getattr(e6_module, "_E6_RUNTIME_AUTHORITY_INSTALLED", False):
        return
    original = e6_module.analyze_e6

    def runtime_authority(market_data, upstream):
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result
        return _runtime_watch_or_original(result, upstream, getattr(e6_module, "_watch_result", None))

    e6_module.analyze_e6 = runtime_authority
    e6_module._E6_RUNTIME_AUTHORITY_INSTALLED = True
