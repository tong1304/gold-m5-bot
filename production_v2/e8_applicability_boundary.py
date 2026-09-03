from __future__ import annotations

"""E6 -> E8 applicability boundary.

E8 owns trade economics, not thesis formation. When E6 has only an
opportunity watch / candidate (or no surviving setup), E8 must remain
NOT_APPLICABLE and must not execute economic analysis or manufacture
secondary probability/profit blockers.
"""

from typing import Any

from .contracts import EngineResult

_WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
_NO_SETUP = {"", "UNKNOWN", "NO_SETUP", "NONE"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _output(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _has_surviving_thesis(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_type") or e6.get("setup_family"))
    if setup in _WATCH_SETUPS or setup in _NO_SETUP:
        return False
    if e6.get("watch_only") is True or (e6.get("trade_ready") is False and setup in _WATCH_SETUPS):
        return False
    status = _text(e6.get("thesis_status") or e6.get("setup_state") or e6.get("state"))
    if status in {"NO_SETUP", "UNKNOWN", "NONE", "INVALIDATED", "CONTESTED_WATCH", "FORMING"} and setup in _NO_SETUP:
        return False
    reasons = e6.get("reason_codes") or e6.get("reasons") or ()
    if isinstance(reasons, str):
        reasons = (reasons,)
    reasons = {_text(x) for x in reasons}
    if "NO_CAUSAL_OPPORTUNITY" in reasons or "NO_SURVIVING_SETUP" in reasons:
        return False
    direction = _text(e6.get("direction") or e6.get("thesis_direction"))
    return direction in {"BUY", "SELL"} and setup not in _NO_SETUP and setup not in _WATCH_SETUPS


def _not_applicable(_original: Any, e6: dict[str, Any]) -> EngineResult:
    """Return a pure boundary result; the original E8 must not execute here."""
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


def install(e8_module) -> None:
    if getattr(e8_module, "_E8_APPLICABILITY_BOUNDARY_INSTALLED", False):
        return
    original = e8_module.analyze_e8

    def guarded(snapshot: dict[str, Any], results: dict[str, EngineResult]):
        e6_result = results.get("E6")
        e6 = _output(e6_result) if e6_result else {}
        if not _has_surviving_thesis(e6):
            return _not_applicable(original, e6)
        return original(snapshot, results)

    e8_module.analyze_e8 = guarded
    e8_module._E8_APPLICABILITY_BOUNDARY_INSTALLED = True
