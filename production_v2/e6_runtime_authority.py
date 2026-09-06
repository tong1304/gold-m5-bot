from __future__ import annotations
from typing import Any
from .contracts import EngineResult
from .e6_opportunity_guard import _direction, _fallback_opportunity, _watch

WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
RUNTIME_AUTHORITY_VERSION = "E6_FINAL_OPPORTUNITY_MEMBRANE_V8"
PENDING_AUCTION_STATES = {"PENDING", "DEVELOPING", "FORMING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}


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
    candidate = str(output.get("candidate_type") or "").upper().strip()
    return setup in WATCH_SETUPS or candidate == "OPPORTUNITY_CANDIDATE" or output.get("watch_only") is True


def _has_no_setup(result: EngineResult) -> bool:
    out = _out(result)
    setup = str(out.get("setup") or "").upper().strip()
    finding = str(out.get("finding") or "").upper().strip()
    reasons = {str(x).upper().strip() for x in (*(out.get("reason_codes") or []), *(out.get("reasons") or []), *(result.reason_codes or ()))}
    if ("NO CAUSAL SETUP HYPOTHESIS" in finding or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding) and _falseish(out.get("trade_ready")) and _falseish(out.get("gate_passed")):
        return True
    return setup in {"", "NO_SETUP", "UNKNOWN", "NONE"} and "NO_CAUSAL_OPPORTUNITY" in reasons


def _sync_professional_reasoning(output: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(output or {})
    setup = str(normalized.get("setup") or normalized.get("setup_family") or "").upper().strip()
    direction = _direction(normalized.get("direction"), normalized.get("bias"), normalized.get("market_direction"), normalized.get("thesis_direction"), normalized.get("direction_thesis"))
    state = str(normalized.get("setup_state") or normalized.get("state") or normalized.get("opportunity_stage") or "").upper().strip()
    thesis_status = str(normalized.get("thesis_status") or normalized.get("maturity") or "").upper().strip()
    candidate_type = str(normalized.get("candidate_type") or "").upper().strip()
    concrete = bool(setup and setup not in {"NO_SETUP", "NONE", "UNKNOWN"} and not setup.startswith(tuple(f"{x}" for x in WATCH_SETUPS)) and direction in {"BUY", "SELL"} and normalized.get("watch_only") is not True and (normalized.get("setup_exists") is True or candidate_type == "SETUP_CANDIDATE" or state in {"SETUP_THESIS", "THESIS_CONTESTED", "FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY", "VALIDATED"}) and thesis_status not in {"ABSENT", "INVALIDATED", "REJECTED", "NO_SETUP"})
    watch = _watch_marked(normalized) and _falseish(normalized.get("trade_ready")) and not concrete
    finding = str(normalized.get("finding") or normalized.get("thesis") or "").strip()
    thesis = str(normalized.get("thesis") or normalized.get("candidate_setup_thesis") or "").strip()
    missing = list(dict.fromkeys(str(x) for x in (normalized.get("missing_proof") or normalized.get("missing_evidence") or normalized.get("reason_codes") or []) if str(x).strip()))
    next_event = normalized.get("next_required_event") or (missing[0] if missing else None)
    reasoning = dict(normalized.get("professional_reasoning") or {})
    reasoning.update({"conclusion": finding or (f"{direction} opportunity is forming; causal setup is not yet proven." if watch else "No surviving causal opportunity thesis from E1-E5."), "hypothesis": thesis or finding, "missing_evidence": missing, "next_required_event": next_event, "role": "SETUP_ANALYST" if concrete else "OPPORTUNITY_WATCH_ANALYST" if watch else "SETUP_ANALYST", "source_of_truth": "E6_AUTHORITATIVE_SETUP_STATE"})
    normalized["professional_reasoning"] = reasoning
    return normalized


def _normalize_watch_semantics(output: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(output)
    setup = str(normalized.get("setup") or "").upper().strip()
    if not _watch_marked(normalized) or not _falseish(normalized.get("trade_ready")):
        return normalized
    if setup not in WATCH_SETUPS and normalized.get("watch_only") is not True:
        return normalized
    direction = _direction(normalized.get("direction"), normalized.get("bias"), normalized.get("market_direction"), normalized.get("thesis_direction"), normalized.get("direction_thesis"))
    direction = direction if direction in {"BUY", "SELL"} else "NEUTRAL"
    stage = str(normalized.get("stage") or normalized.get("opportunity_stage") or normalized.get("thesis_status") or "FORMING").strip().upper()
    stage_text = {"FORMING": "forming", "CONTESTED": "contested", "VALIDATING": "being validated", "WATCHING": "being watched", "DEVELOPING": "developing"}.get(stage, stage.lower().replace("_", " "))
    normalized.update({"setup": "OPPORTUNITY_WATCH", "candidate_type": "OPPORTUNITY_CANDIDATE", "watch_only": True, "trade_ready": False, "gate_passed": False, "trade_permission": False, "finding": f"{direction} opportunity is {stage_text}; causal setup is not yet proven." if direction != "NEUTRAL" else f"Opportunity is {stage_text}; causal setup is not yet proven.", "runtime_authority": RUNTIME_AUTHORITY_VERSION, "runtime_semantic_boundary": "WATCH_STATE_MUST_NOT_EXPOSE_LEGACY_SETUP_CLAIM"})
    normalized.setdefault("next_required_event", "NEXT_CLOSED_M5_CANDLE")
    return normalized


def _pending_event_direction(event: str) -> str:
    event = str(event or "").upper().strip()
    if any(token in event for token in ("HIGH_SWEEP_REJECTION", "HIGH_REJECTION", "HIGH_ACCEPTANCE", "HIGH_BREAK")):
        return "SELL" if "REJECTION" in event or "SWEEP" in event else "BUY"
    if any(token in event for token in ("LOW_SWEEP_REJECTION", "LOW_REJECTION", "LOW_ACCEPTANCE", "LOW_BREAK")):
        return "BUY" if "REJECTION" in event or "SWEEP" in event else "SELL"
    return "NEUTRAL"


def _pending_event_rescue(result: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    """Preserve a live pending E4 event as an E6 watch when legacy E6 collapses it."""
    if not _has_no_setup(result):
        return result
    e4 = _out(upstream.get("E4"))
    auction = str(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state") or "").upper().strip()
    event = str(e4.get("event") or e4.get("finding") or "").upper().strip()
    if auction not in PENDING_AUCTION_STATES:
        return result
    if not any(token in event for token in ("ACCEPTANCE", "REJECTION", "SWEEP", "FAILED_BREAK", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION")):
        return result
    direction = _pending_event_direction(event)
    if direction not in {"BUY", "SELL"}:
        direction = _direction(e4.get("directional_implication"), e4.get("direction"), e4.get("response_actor"))
    if direction not in {"BUY", "SELL"}:
        return result
    event_id = str(e4.get("event_id") or e4.get("event_candle_id") or "")
    e5 = _out(upstream.get("E5"))
    space_key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        space = float(e5.get(space_key) or 0.0)
    except (TypeError, ValueError):
        space = 0.0
    out = _out(result)
    missing = ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]
    if space < 0.75:
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    out.update({
        "architecture": "E6_OPPORTUNITY_THESIS_LIFECYCLE_V10",
        "version": "10.0",
        "state": "FORMING_WATCH",
        "setup_state": "FORMING_WATCH",
        "opportunity_stage": "FORMING_WATCH",
        "setup": "OPPORTUNITY_WATCH",
        "setup_family": "LIQUIDITY_RESPONSE",
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "thesis_status": "FORMING",
        "setup_exists": False,
        "watch_only": True,
        "trade_ready": False,
        "trade_permission": False,
        "gate_passed": False,
        "e6_thesis_proven": False,
        "e6_causal_gate": "WATCH_ONLY",
        "finding": f"{direction} opportunity is forming from pending E4 {event}; causal follow-through is not yet proven.",
        "thesis": f"{direction} pending-event hypothesis from {event}; wait for closed-candle follow-through before E7 confirmation.",
        "supporting_evidence": ["E4_PENDING_DIRECTIONAL_EVENT"],
        "counter_evidence": ["E4_AUCTION_UNCONFIRMED"],
        "hard_conflicts": [],
        "missing_proof": missing,
        "missing_evidence": missing,
        "next_required_event": "NEXT_CLOSED_M5_CANDLE",
        "wait_for": ",".join(missing),
        "candidate_identity": f"OPPORTUNITY_WATCH:{direction}:LIQUIDITY_RESPONSE:{event_id}",
        "opportunity_id": f"{direction}|OPPORTUNITY_WATCH|{event_id}" if event_id else f"{direction}|OPPORTUNITY_WATCH",
        "event_id": event_id,
        "origin_event_id": event_id,
        "available_space_atr": space,
        "reason_codes": missing,
        "reasons": missing,
        "execution_authority": "E9",
        "invalidated": False,
        "upstream_evidence_lost": False,
        "causal_evidence_lost": False,
        "lifecycle_state": "OPPORTUNITY_WATCH",
        "pending_event_authority": RUNTIME_AUTHORITY_VERSION,
    })
    print(f"[PRODUCTION V2] E6_RUNTIME_MEMBRANE version={RUNTIME_AUTHORITY_VERSION} action=PRESERVE_PENDING_EVENT event={event} direction={direction} state=FORMING_WATCH", flush=True)
    return EngineResult("E6", result.name, False, result.score, out, tuple(missing))


def _pending_failed_break_watch(result: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    e4 = dict(getattr(upstream.get("E4"), "output", {}) or {})
    event = str(e4.get("event", e4.get("finding")) or "").upper().strip()
    auction = str(e4.get("auction_state", e4.get("state")) or "").upper().strip()
    if auction not in {"PENDING", "DEVELOPING", "FORMING"} or "FAILED_BREAK_RECLAIM" not in event:
        return result
    out = _out(result)
    if _watch_marked(out) and _falseish(out.get("trade_ready")):
        return result
    candidate = _fallback_opportunity(upstream)
    if candidate is None:
        return result
    return _watch(result, candidate)


def _runtime_watch_or_original(result: EngineResult, upstream: dict[str, EngineResult], thesis_builder=None) -> EngineResult:
    result = _pending_failed_break_watch(result, upstream)
    result = _pending_event_rescue(result, upstream)
    out = _out(result)
    if _watch_marked(out) and _falseish(out.get("trade_ready")):
        return EngineResult(result.engine_id, result.name, False, result.score, _sync_professional_reasoning(_normalize_watch_semantics(out)), result.reason_codes)
    if not _has_no_setup(result):
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, _sync_professional_reasoning(out), result.reason_codes)
    candidate = _fallback_opportunity(upstream)
    if candidate is None:
        normalized = _sync_professional_reasoning(out)
        print(f"[PRODUCTION V2] E6_RUNTIME_MEMBRANE version={RUNTIME_AUTHORITY_VERSION} action=NO_RESCUE candidate=NONE", flush=True)
        return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, normalized, result.reason_codes)
    thesis = thesis_builder(result, candidate) if thesis_builder is not None else _watch(result, candidate)
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
