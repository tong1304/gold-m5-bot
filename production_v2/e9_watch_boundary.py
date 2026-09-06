from __future__ import annotations

from typing import Any

from .contracts import EngineResult

_WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
_DIRECTIONS = {"BUY", "SELL"}
_HARD_CONFLICTS = {
    "THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED",
    "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED",
    "E3_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED", "STRUCTURE_INTEGRITY_INVALID",
    "PROTECTED_LEVEL_GEOMETRY_INVALID", "EXECUTION_IMPOSSIBLE", "DATA_INTEGRITY_INVALID",
    "SHARED_MARKET_PICTURE_CONTRACT_BLOCKED",
}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _watch_state(e6: dict[str, Any]) -> tuple[str, str] | None:
    setup = _text(e6.get("setup") or e6.get("setup_type") or e6.get("setup_family"))
    direction = _text(e6.get("direction") or e6.get("thesis_direction") or e6.get("direction_thesis"))
    if setup not in _WATCH_SETUPS or direction not in _DIRECTIONS:
        return None
    if e6.get("watch_only") is not True or e6.get("trade_ready") is True or e6.get("gate_passed") is True:
        return None
    return direction, setup


def _has_hard_invalidation(upstream: dict[str, EngineResult]) -> bool:
    for key in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        output = _out(upstream.get(key))
        values = output.get("reason_codes") or output.get("reasons") or ()
        if isinstance(values, str):
            values = (values,)
        if any(_text(value) in _HARD_CONFLICTS for value in values):
            return True
        if any(_text(output.get(name)).endswith("_INVALIDATED") for name in ("invalidation", "state", "setup_state")):
            return True
    return False


def _watch_wait_events(e6: dict[str, Any]) -> list[str]:
    """Return events that can advance an opportunity watch into a real thesis.

    E7 is deliberately excluded here: confirmation belongs downstream of E6.
    The watch may continue across closed candles while upstream proof develops.
    """
    missing = e6.get("missing_proof") or e6.get("missing_evidence") or ()
    if isinstance(missing, str):
        missing = [missing]
    events = [str(value).strip().upper() for value in missing if str(value).strip()]
    events = [value for value in events if value not in {
        "E7_CONFIRMATION", "E7_VALID_CLOSED_CANDLE_TRIGGER_REQUIRED",
    }]
    events.extend(["E6_SETUP_THESIS_REQUIRED", "E7_TRIGGER_BLOCKED_UNTIL_E6_THESIS"])
    return list(dict.fromkeys(events))


def _watch_result(direction: str, setup: str, e6: dict[str, Any]) -> EngineResult:
    wait_events = _watch_wait_events(e6)
    reasons = ["E9_FINAL_GOVERNANCE", "E6_OPPORTUNITY_WATCH", "E6_SETUP_THESIS_REQUIRED", "E7_TRIGGER_BLOCKED_UNTIL_E6_THESIS"]
    output = {
        "decision": "NO_TRADE", "final_governance": "WATCH", "governance_decision": "WATCH",
        "governance_reason": "WAITING_FOR_E6_SETUP_THESIS",
        "governance_blockers": ["E6_SETUP_THESIS_REQUIRED"],
        "next_required_events": wait_events, "execution_state": "BLOCKED",
        "all_gates_pass": False, "direction": direction, "thesis_direction": direction, "setup": setup,
        "thesis": f"{direction} opportunity watch is active; E6 thesis proof is not complete. E7 confirmation is blocked until E6 establishes a surviving setup thesis.",
        "thesis_state": "HYPOTHESIS", "thesis_lifecycle_source": "E6", "setup_state": "FORMING",
        "confirmation_state": "NOT_APPLICABLE", "economic_state": "NOT_APPLICABLE", "economic_blockers": [],
        "economic_pending": [], "hard_conflicts": [],
        "proof_summary": {"core_thesis": False, "e6_thesis": "OPPORTUNITY_WATCH", "e7_trigger": "NOT_APPLICABLE", "e8_economics": "NOT_APPLICABLE"},
        "mandatory_gates": {"core_thesis": False, "closed_candle_trigger": False, "survivable_economics": False, "fatal_veto_clear": True},
        "opportunity_state": "WATCH", "opportunity": {"direction": direction, "setup": setup, "state": "WATCH", "do_not_execute": True},
        "reason_codes": reasons, "reasons": reasons, "reason_scope": "E6_WATCH_BOUNDARY_ONLY",
        "authority_contract": {"market_evidence_owner": "E1-E5", "trade_thesis_owner": "E6", "trigger_owner": "E7", "trade_economics_owner": "E8", "final_decision_owner": "E9", "e9_may_rewrite_e6_thesis": False, "e9_may_bypass_e7": False, "e9_may_bypass_e8": False},
        "architecture": "E9_FINAL_GOVERNANCE_THESIS_TRIGGER_ECONOMICS",
        "watch_boundary": "E6_WATCH_REQUIRES_E6_THESIS_BEFORE_E7_AND_E8",
        "governance_layers": {"market_control": "MARKET_CONTROL", "thesis_control": "E6_OWNER", "proof_control": "E7_CONFIRMATION_AND_E8_ECONOMICS", "final_governance": "E9_FINAL_AUTHORITY"},
    }
    return EngineResult("E9", "Master Decision Brain", False, 0.0, output, tuple(reasons))


def _restore_governance_layers(result: EngineResult) -> EngineResult:
    out = _out(result)
    layers = dict(out.get("governance_layers") or {})
    layers.update({
        "market_control": layers.get("market_control", "MARKET_CONTROL"),
        "thesis_control": layers.get("thesis_control", "E6_OWNER"),
        "proof_control": layers.get("proof_control", "E7_CONFIRMATION_AND_E8_ECONOMICS"),
        "final_governance": layers.get("final_governance", "E9_FINAL_AUTHORITY"),
    })
    out["governance_layers"] = layers
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, result.reason_codes)


def install(e9_module) -> None:
    if getattr(e9_module, "_E9_WATCH_BOUNDARY_INSTALLED", False):
        return
    original = e9_module.analyze_e9

    def guarded(snapshot: dict[str, Any], upstream: dict[str, EngineResult]):
        e6 = _out(upstream.get("E6")); watch = _watch_state(e6); e8 = _out(upstream.get("E8"))
        if watch and e8.get("applicability") == "NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS" and not _has_hard_invalidation(upstream):
            return _watch_result(watch[0], watch[1], e6)
        return _restore_governance_layers(original(snapshot, upstream))

    e9_module.analyze_e9 = guarded
    e9_module._E9_WATCH_BOUNDARY_INSTALLED = True
