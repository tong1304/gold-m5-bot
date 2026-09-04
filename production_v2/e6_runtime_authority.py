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


def _sync_professional_reasoning(output: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(output or {})
    setup = str(normalized.get("setup") or normalized.get("setup_family") or "").upper().strip()
    direction = _direction(normalized.get("direction"), normalized.get("bias"), normalized.get("market_direction"), normalized.get("thesis_direction"), normalized.get("direction_thesis"))
    state = str(normalized.get("setup_state") or normalized.get("state") or normalized.get("opportunity_stage") or "").upper().strip()
    thesis_status = str(normalized.get("thesis_status") or normalized.get("maturity") or "").upper().strip()
    candidate_type = str(normalized.get("candidate_type") or "").upper().strip()
    concrete = bool(
        setup
        and setup not in {"NO_SETUP", "NONE", "UNKNOWN"}
        and not setup.startswith(tuple(f"{x}" for x in WATCH_SETUPS))
        and direction in {"BUY", "SELL"}
        and normalized.get("watch_only") is not True
        and (normalized.get("setup_exists") is True or candidate_type == "SETUP_CANDIDATE" or state in {"SETUP_THESIS", "THESIS_CONTESTED", "FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY", "VALIDATED"})
        and thesis_status not in {"ABSENT", "INVALIDATED", "REJECTED", "NO_SETUP"}
    )
    watch = _watch_marked(normalized) and _falseish(normalized.get("trade_ready")) and not concrete
    finding = str(normalized.get("finding") or normalized.get("thesis") or "").strip()
    thesis = str(normalized.get("thesis") or normalized.get("candidate_setup_thesis") or "").strip()
    missing = list(dict.fromkeys(str(x) for x in (normalized.get("missing_proof") or normalized.get("missing_evidence") or normalized.get("reason_codes") or []) if str(x).strip()))
    next_event = normalized.get("next_required_event") or (missing[0] if missing else None)
    if concrete:
        conclusion = finding or thesis or f"{direction} {setup} thesis is active; downstream confirmation and economics remain pending."
        hypothesis = thesis or finding
        role = "SETUP_ANALYST"
    elif watch:
        conclusion = finding or f"{direction} opportunity is forming; causal setup is not yet proven."
        hypothesis = thesis
        role = "OPPORTUNITY_WATCH_ANALYST"
    else:
        conclusion = finding or "No surviving causal opportunity thesis from E1-E5."
        hypothesis = thesis
        role = "SETUP_ANALYST"
    reasoning = dict(normalized.get("professional_reasoning") or {})
    reasoning.update({"conclusion": conclusion, "hypothesis": hypothesis, "missing_evidence": missing, "next_required_event": next_event, "role": role, "source_of_truth": "E6_AUTHORITATIVE_SETUP_STATE"})
    normalized["professional_reasoning"] = reasoning
    return normalized


def _normalize_watch_semantics(output: dict[str, Any]) -> dict[str, Any]:
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
    out = _out(result)
    if _watch_marked(out) and _falseish(out.get("trade_ready")):
        normalized = _normalize_watch_semantics(out)
        normalized = _sync_professional_reasoning(normalized)
        return EngineResult(result.engine_id, result.name, False, result.score, normalized, result.reason_codes)
    if not _has_no_setup(result):
        normalized = _sync_professional_reasoning(out)
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, normalized, result.reason_codes)
    candidate = _fallback_opportunity(upstream)
    if candidate is None:
        normalized = _sync_professional_reasoning(out)
        print(f"[PRODUCTION V2] E6_RUNTIME_MEMBRANE version={RUNTIME_AUTHORITY_VERSION} action=NO_RESCUE candidate=NONE", flush=True)
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, normalized, result.reason_codes)
    if thesis_builder is not None:
        thesis = thesis_builder(result, candidate)
    else:
        thesis = _watch(result, candidate)
    # IMPORTANT: rescue output is authoritative E6 thesis formation. Do not pass
    # it through the watch normalizer: that would erase a real setup thesis and
    # collapse SETUP_THESIS back into OPPORTUNITY_WATCH.
    thesis_out = dict(thesis.output or {})
    thesis_out["runtime_rescue_reason"] = "CAUSAL_E1_E5_EVIDENCE_SURVIVES_LEGACY_NO_SETUP"
    thesis_out["runtime_direction_source"] = _direction(candidate.get("direction"))
    thesis_out["runtime_candidate_family"] = candidate.get("family")
    thesis_out["runtime_candidate_event_id"] = candidate.get("event_id")
    thesis_out = _sync_professional_reasoning(thesis_out)
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
