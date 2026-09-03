from __future__ import annotations

from typing import Any

from .contracts import EngineResult

WATCH_PREFIXES = ("OPPORTUNITY_WATCH", "AUCTION_WATCH", "REGIME_WATCH")
NO_SETUP = {"", "NONE", "UNKNOWN", "NO_SETUP", "NO_PLAUSIBLE_SETUP", "UNRESOLVED"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _is_opportunity_watch(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family"))
    candidate_type = _text(e6.get("candidate_type"))
    return bool(
        e6.get("watch_only") is True
        or candidate_type == "OPPORTUNITY_CANDIDATE"
        or setup.startswith(WATCH_PREFIXES)
    )


def enforce_e6_thesis_boundary(original_e7, snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Prevent E7 from turning an opportunity watch into a confirmed setup.

    E6 owns the causal setup thesis. An opportunity watch is evidence worth
    carrying to the next closed candle, but it is not a setup family that E7
    may confirm. This boundary is intentionally conservative: it only rewrites
    the E7 result when E6 explicitly marks the candidate as watch-only.
    """
    result = original_e7(snapshot, upstream)
    e6 = upstream.get("E6")
    if not e6 or not isinstance(result, EngineResult):
        return result
    e6o = dict(e6.output or {})
    if not _is_opportunity_watch(e6o):
        return result

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


def install(pipeline_module) -> None:
    """Install the E6->E7 boundary exactly once on the production pipeline."""
    if getattr(pipeline_module, "_E7_THESIS_BOUNDARY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e7

    def wrapped(snapshot, upstream):
        return enforce_e6_thesis_boundary(original, snapshot, upstream)

    pipeline_module.analyze_e7 = wrapped
    pipeline_module._E7_THESIS_BOUNDARY_INSTALLED = True
