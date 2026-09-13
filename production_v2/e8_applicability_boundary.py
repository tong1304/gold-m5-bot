from __future__ import annotations

"""E6 -> E8 applicability boundary.

E8 owns trade economics, not thesis formation. A concrete E6 setup thesis
must reach E8. Early opportunity candidates are also eligible for a
NON-TRADEABLE economic screen so the system can measure whether confirmation
would be worth waiting for. Only explicit watch/no-setup/invalidation states
without an early candidate make E8 inapplicable.
"""

from typing import Any

from .contracts import EngineResult

_WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
_NO_SETUP = {"", "UNKNOWN", "NO_SETUP", "NONE", "NO_PLAUSIBLE_SETUP", "UNRESOLVED"}
_EARLY_CANDIDATES = {"EARLY_OPPORTUNITY_CANDIDATE", "OPPORTUNITY_CANDIDATE"}
_INVALIDATION_CODES = {"THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "SETUP_INVALIDATED", "SETUP_REJECTED"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _output(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _is_early_candidate(e6: dict[str, Any]) -> bool:
    candidate_type = _text(e6.get("candidate_type"))
    return candidate_type in _EARLY_CANDIDATES or bool(e6.get("early_candidate"))


def _has_surviving_thesis(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_type") or e6.get("setup_family"))
    direction = _text(e6.get("direction") or e6.get("thesis_direction"))
    status = _text(e6.get("thesis_status") or e6.get("setup_state") or e6.get("state"))

    if setup in _WATCH_SETUPS or setup in _NO_SETUP:
        return False
    if direction not in {"BUY", "SELL"}:
        return False
    if e6.get("watch_only") is True:
        return False
    if status in {"INVALIDATED", "REJECTED", "NO_SETUP", "UNKNOWN", "NONE"}:
        return False

    reasons = e6.get("reason_codes") or e6.get("reasons") or ()
    if isinstance(reasons, str):
        reasons = (reasons,)
    reason_codes = {_text(x) for x in reasons}
    if reason_codes & _INVALIDATION_CODES:
        return False
    return True


def _not_applicable(_original: Any, e6: dict[str, Any]) -> EngineResult:
    direction = _text(e6.get("direction") or e6.get("thesis_direction")) or "NEUTRAL"
    setup = _text(e6.get("setup") or e6.get("setup_type") or e6.get("setup_family")) or "UNKNOWN"
    reasons = ["E6_THESIS_REQUIRED"]
    out = {
        "finding": "NOT_APPLICABLE",
        "direction": direction,
        "setup": setup,
        "confirmation": "NOT_APPLICABLE",
        "economic_state": "NOT_APPLICABLE",
        "risk_ready": False,
        "gate_passed": False,
        "trade_plan": {"valid": False, "direction": direction, "setup": setup},
        "reasons": reasons,
        "reason_codes": reasons,
        "primary_veto": "E6_THESIS_REQUIRED",
        "secondary_vetoes": [],
        "blocking_layers": ["THESIS_BOUNDARY"],
        "veto_class": "NOT_APPLICABLE",
        "next_required_event": "E6_CAUSAL_SETUP_PROOF",
        "next_required_events": ["E6_CAUSAL_SETUP_PROOF"],
        "veto_count": 1,
        "professional_rule": "E8_REQUIRES_SURVIVING_E6_THESIS;E8_DOES_NOT_CREATE_THESIS",
        "decision_authority": "E9",
        "applicability": "NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS",
    }
    return EngineResult("E8", "Trade Economics Brain", False, 0.0, out, tuple(reasons))


def _early_shadow(results: dict[str, EngineResult], e6: dict[str, Any]) -> dict[str, EngineResult]:
    """Make an E8-only provisional setup; never mutates the real E6 result."""
    e6_result = results.get("E6")
    if not e6_result:
        return results
    provisional = dict(e6)
    setup = _text(provisional.get("setup") or provisional.get("setup_family") or provisional.get("setup_type"))
    if setup in _WATCH_SETUPS or not setup:
        provisional["setup"] = "EARLY_OPPORTUNITY"
    provisional["watch_only"] = False
    provisional["economic_screen_only"] = True
    provisional["trade_ready"] = False
    provisional["thesis_status"] = _text(provisional.get("thesis_status")) or "FORMING"
    provisional["candidate_type"] = "EARLY_OPPORTUNITY_CANDIDATE"
    shadow = dict(results)
    shadow["E6"] = EngineResult(
        e6_result.engine_id,
        e6_result.name,
        e6_result.gate_passed,
        e6_result.score,
        provisional,
        e6_result.reason_codes,
    )
    return shadow


def install(e8_module) -> None:
    if getattr(e8_module, "_E8_APPLICABILITY_BOUNDARY_INSTALLED", False):
        return
    original = e8_module.analyze_e8

    def guarded(snapshot: dict[str, Any], results: dict[str, EngineResult]):
        e6_result = results.get("E6")
        e6 = _output(e6_result) if e6_result else {}

        # IMPORTANT: early candidates must be screened before the normal
        # applicability veto sees watch_only=True. This screen is economics
        # only and can never authorize a trade.
        if _is_early_candidate(e6):
            screened = original(snapshot, _early_shadow(results, e6))
            out = dict(screened.output or {})
            out["economic_stage"] = "EARLY_OPPORTUNITY_SCREEN"
            out["economic_screen_only"] = True
            out["trade_authorized"] = False
            out["confirmation_required_before_trade"] = True
            reasons = list(out.get("reason_codes") or out.get("reasons") or [])
            if "EARLY_OPPORTUNITY_ECONOMICS_SCREEN" not in reasons:
                reasons.append("EARLY_OPPORTUNITY_ECONOMICS_SCREEN")
            out["reason_codes"] = reasons
            out["reasons"] = reasons
            return EngineResult("E8", screened.name, False, screened.score, out, tuple(dict.fromkeys(reasons)))

        if not _has_surviving_thesis(e6):
            return _not_applicable(original, e6)
        return original(snapshot, results)

    e8_module.analyze_e8 = guarded
    e8_module._E8_APPLICABILITY_BOUNDARY_INSTALLED = True
