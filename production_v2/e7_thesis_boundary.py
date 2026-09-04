from __future__ import annotations

from typing import Any

from .contracts import EngineResult

WATCH_PREFIXES = ("OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH")
NO_SETUP = {"", "NONE", "UNKNOWN", "NO_SETUP", "NO_PLAUSIBLE_SETUP", "UNRESOLVED"}
CONCRETE_SETUP_STATES = {"FORMING", "VALIDATING", "MATURE", "CONFIRMED", "TRADE_READY", "VALIDATED"}
EXPLICIT_THESIS_STATES = {"SETUP_THESIS", "THESIS_CONTESTED"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _is_concrete_surviving_setup(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family"))
    state = _text(e6.get("setup_state") or e6.get("state") or e6.get("opportunity_stage"))
    direction = _text(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction"))
    thesis_status = _text(e6.get("thesis_status") or e6.get("maturity"))
    explicit_candidate = (
        _text(e6.get("candidate_type")) == "SETUP_CANDIDATE"
        and e6.get("watch_only") is False
    )
    explicit_thesis = state in EXPLICIT_THESIS_STATES or thesis_status in EXPLICIT_THESIS_STATES
    return bool(
        setup
        and setup not in NO_SETUP
        and not setup.startswith(WATCH_PREFIXES)
        and direction in {"BUY", "SELL"}
        and not e6.get("watch_only") is True
        and (
            e6.get("setup_exists") is True
            or state in CONCRETE_SETUP_STATES
            or _text(e6.get("e6_causal_gate")) == "PASSED"
            or explicit_candidate
            or explicit_thesis
        )
        and thesis_status not in {"ABSENT", "INVALIDATED", "REJECTED", "NO_SETUP"}
    )


def _is_opportunity_watch(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family"))
    candidate_type = _text(e6.get("candidate_type"))
    if _is_concrete_surviving_setup(e6):
        return False
    return bool(
        e6.get("watch_only") is True
        or candidate_type == "OPPORTUNITY_CANDIDATE"
        or setup.startswith(WATCH_PREFIXES)
    )


def _preserve_concrete_thesis(result: EngineResult, e6o: dict[str, Any]) -> EngineResult:
    """Repair only the legacy E7 watch downgrade; never manufacture confirmation."""
    out = dict(result.output or {})
    e6_setup = _text(e6o.get("setup") or e6o.get("setup_family"))
    e6_direction = _text(e6o.get("direction") or e6o.get("direction_thesis") or e6o.get("thesis_direction"))
    thesis = str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or "")
    reason_codes = [str(x) for x in (out.get("reason_codes") or result.reason_codes or [])]
    if "E6_OPPORTUNITY_WATCH_NOT_SETUP" not in {_text(x) for x in reason_codes}:
        return result
    cleaned = [x for x in reason_codes if _text(x) not in {"E6_OPPORTUNITY_WATCH_NOT_SETUP", "E7_DID_NOT_CREATE_THESIS"}]
    cleaned = list(dict.fromkeys(cleaned + ["E6_THESIS_SURVIVES", "E7_EVALUATES_SETUP_CONFIRMATION"]))
    out.update({
        "state": "WAIT",
        "confirmation": "UNRESOLVED",
        "confirmation_state": "PENDING",
        "trigger_status": "NOT_OBSERVED",
        "trigger_observed": False,
        "confirmation_strength": "NONE",
        "confirmation_score": 0.0,
        "trade_decision_authority": False,
        "candidate_setup_thesis": thesis,
        "setup": e6_setup,
        "setup_family": e6_setup,
        "direction": e6_direction,
        "supporting_evidence": list(dict.fromkeys(list(out.get("supporting_evidence") or []) + ["E6_SURVIVING_SETUP_THESIS"])),
        "counter_evidence": list(out.get("counter_evidence") or []),
        "missing_evidence": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
        "next_required_evidence": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
        "next_required_event": "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION",
        "reason_codes": cleaned,
        "thesis_boundary": {
            "e6_owns_thesis": True,
            "e7_may_confirm_only_surviving_setup": True,
            "watch_is_not_setup": True,
            "legacy_watch_downgrade_repaired": True,
            "enforced": True,
        },
        "reasoning_trace": {
            **dict(out.get("reasoning_trace") or {}),
            "conclusion": "E6 owns a surviving setup thesis; E7 is evaluating confirmation and has not yet proven a trigger.",
            "why_not_confirmed": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
            "next_required_event": "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION",
        },
    })
    out["professional_reasoning"] = {
        **dict(out.get("professional_reasoning") or {}),
        "conclusion": out["reasoning_trace"]["conclusion"],
        "hypothesis": thesis,
        "missing_evidence": out["missing_evidence"],
        "next_required_event": out["next_required_event"],
    }
    return EngineResult(result.engine_id, result.name, False, result.score, out, tuple(cleaned))


def enforce_e6_thesis_boundary(original_e7, snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Prevent E7 from turning an opportunity watch into a confirmed setup.

    E6 owns the causal setup thesis. A concrete E6 setup remains eligible for
    E7 proof. Only an explicit watch/no-setup state is blocked from confirmation.
    If a legacy E7 implementation still emits the old watch downgrade, the
    membrane restores the E6-owned thesis and leaves confirmation pending.
    """
    e6 = upstream.get("E6")
    if not e6:
        return original_e7(snapshot, upstream)
    e6o = dict(e6.output or {})
    concrete = _is_concrete_surviving_setup(e6o)
    print(
        "[PRODUCTION V2] E7_THESIS_BOUNDARY "
        f"setup={_text(e6o.get('setup') or e6o.get('setup_family')) or 'NONE'} "
        f"direction={_text(e6o.get('direction') or e6o.get('direction_thesis')) or 'NEUTRAL'} "
        f"state={_text(e6o.get('state')) or 'NONE'} "
        f"thesis_status={_text(e6o.get('thesis_status')) or 'NONE'} "
        f"candidate_type={_text(e6o.get('candidate_type')) or 'NONE'} "
        f"watch_only={e6o.get('watch_only')} "
        f"concrete={concrete}",
        flush=True,
    )
    if _is_opportunity_watch(e6o):
        result = original_e7(snapshot, upstream)
        out = dict(result.output or {})
        out.update({
            "state": "WAIT",
            "confirmation": "UNRESOLVED",
            "confirmation_state": "NOT_APPLICABLE",
            "trigger_status": "NOT_ALLOWED",
            "trigger_observed": False,
            "confirmation_strength": "NONE",
            "confirmation_score": 0.0,
            "trade_decision_authority": False,
            "candidate_setup_thesis": "",
            "setup": "NONE",
            "setup_family": "NONE",
            "supporting_evidence": [],
            "counter_evidence": ["E6_OPPORTUNITY_WATCH_IS_NOT_A_SETUP_THESIS"],
            "missing_evidence": ["E6_SURVIVING_SETUP_THESIS", "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
            "next_required_evidence": ["E6_SURVIVING_SETUP_THESIS", "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
            "next_required_event": "E6_SURVIVING_SETUP_THESIS",
            "reason_codes": [
                "CONFIRMATION_NOT_APPLICABLE",
                "E7_DID_NOT_CREATE_THESIS",
                "E6_OPPORTUNITY_WATCH_NOT_SETUP",
            ],
            "confirmation_lifecycle": {
                "state": "WAIT",
                "trigger": "NOT_ALLOWED",
                "confirmation": "NOT_APPLICABLE",
                "follow_through": "NOT_APPLICABLE",
                "invalidation": "NONE",
                "next_required_event": "E6_SURVIVING_SETUP_THESIS",
            },
            "reasoning_trace": {
                "conclusion": "E6 is carrying an opportunity watch, not a surviving trade setup thesis; E7 cannot confirm it.",
                "why_not_confirmed": ["E6_OPPORTUNITY_WATCH_NOT_SETUP"],
                "next_required_event": "E6_SURVIVING_SETUP_THESIS",
            },
            "thesis_boundary": {
                "e6_owns_thesis": True,
                "e7_may_confirm_only_surviving_setup": True,
                "watch_is_not_setup": True,
                "enforced": True,
            },
        })
        out["professional_reasoning"] = {
            **dict(out.get("professional_reasoning") or {}),
            "conclusion": out["reasoning_trace"]["conclusion"],
            "hypothesis": "",
            "missing_evidence": out["missing_evidence"],
            "next_required_event": out["next_required_event"],
        }
        return EngineResult(result.engine_id, result.name, False, result.score, out, tuple(out["reason_codes"]))

    result = original_e7(snapshot, upstream)
    if concrete:
        return _preserve_concrete_thesis(result, e6o)
    return result


def install(pipeline_module) -> None:
    """Install the E6->E7 boundary exactly once on the production pipeline."""
    if getattr(pipeline_module, "_E7_THESIS_BOUNDARY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e7

    def wrapped(snapshot, upstream):
        return enforce_e6_thesis_boundary(original, snapshot, upstream)

    pipeline_module.analyze_e7 = wrapped
    pipeline_module._E7_THESIS_BOUNDARY_INSTALLED = True
