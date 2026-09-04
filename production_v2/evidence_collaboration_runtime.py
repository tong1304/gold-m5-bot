from __future__ import annotations

from typing import Any

from .evidence_ledger import build_evidence_ledger, ledger_for_e9

_WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
_NO_SETUP = {"", "NONE", "UNKNOWN", "NO_SETUP", "NO_PLAUSIBLE_SETUP", "UNRESOLVED"}
_INVALIDATION_CODES = {"THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "SETUP_INVALIDATED", "SETUP_REJECTED"}


def _install_once(module: Any, marker: str, function_name: str, wrapper_factory) -> None:
    if getattr(module, marker, False):
        return
    original = getattr(module, function_name)
    setattr(module, function_name, wrapper_factory(original))
    setattr(module, marker, True)


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _codes(output: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in ("reason_codes", "reasons", "blockers", "conflicts", "invalidations", "active_invalidations"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif isinstance(value, dict):
            values.extend(key for key, enabled in value.items() if enabled)
    return {_text(value) for value in values if _text(value)}


def _e6_has_concrete_thesis(output: dict[str, Any]) -> bool:
    setup = _text(output.get("setup") or output.get("setup_family") or output.get("setup_type"))
    direction = _text(output.get("direction") or output.get("direction_thesis") or output.get("thesis_direction"))
    state = _text(output.get("thesis_status") or output.get("thesis_state") or output.get("setup_state") or output.get("state"))
    if setup in _WATCH_SETUPS or setup in _NO_SETUP:
        return False
    if direction not in {"BUY", "SELL"} or output.get("watch_only") is True:
        return False
    if state in {"INVALIDATED", "REJECTED", "NO_SETUP", "UNKNOWN", "NONE"}:
        return False
    return not bool(_codes(output) & _INVALIDATION_CODES)


def preserve_e6_thesis_contract(e6_output: dict[str, Any], e9_output: dict[str, Any]) -> dict[str, Any]:
    """Keep E9's diagnostics consistent with a concrete E6 thesis.

    E9 remains the only decision authority. This membrane does not grant a
    trade; it only prevents a stale legacy `NO_SURVIVING_E6_THESIS` diagnostic
    from contradicting a concrete, non-invalidated E6 setup thesis.
    """
    e9 = dict(e9_output or {})
    if not _e6_has_concrete_thesis(e6_output):
        return e9
    codes = []
    for key in ("reason_codes", "reasons"):
        value = e9.get(key)
        if isinstance(value, str):
            codes.append(value)
        elif isinstance(value, (list, tuple, set)):
            codes.extend(value)
    stale = {_text(code) for code in codes}
    if "NO_SURVIVING_E6_THESIS" not in stale:
        return e9
    replacement = ["E6_THESIS_SURVIVES", "E9_EVALUATES_E7_AND_E8"]
    cleaned = [code for code in codes if _text(code) != "NO_SURVIVING_E6_THESIS"]
    merged = list(dict.fromkeys(cleaned + replacement))
    e9["reason_codes"] = merged
    e9["reasons"] = merged
    e9["thesis_contract"] = {
        "e6_thesis_survives": True,
        "e6_owns_thesis": True,
        "e9_owns_final_decision": True,
        "stale_no_thesis_diagnostic_removed": True,
    }
    e9.setdefault("thesis_source", "E6")
    return e9


def install(e6_module: Any, e9_module: Any) -> None:
    """Make the same specialist evidence ledger available to thesis and governance.

    E1-E5 evidence is frozen into the snapshot immediately before E6. The
    final E1-E8 ledger is refreshed immediately before E9. Neither ledger can
    make a decision; it is collaboration context only.
    """

    def e6_wrapper(original):
        def wrapped(market_data, upstream):
            market_data["evidence_ledger"] = build_evidence_ledger(upstream)
            market_data["evidence_ledger"]["phase"] = "PRE_THESIS_E1_E5"
            return original(market_data, upstream)
        return wrapped

    def e9_wrapper(original):
        def wrapped(snapshot, upstream):
            snapshot["evidence_ledger"] = ledger_for_e9(upstream)
            snapshot["evidence_ledger"]["phase"] = "FINAL_GOVERNANCE_E1_E8"
            result = original(snapshot, upstream)
            e6 = dict(getattr(upstream.get("E6"), "output", {}) or {})
            output = preserve_e6_thesis_contract(e6, dict(getattr(result, "output", {}) or {}))
            return type(result)(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)
        return wrapped

    _install_once(e6_module, "_EVIDENCE_COLLABORATION_E6_INSTALLED", "analyze_e6", e6_wrapper)
    _install_once(e9_module, "_EVIDENCE_COLLABORATION_E9_INSTALLED", "analyze_e9", e9_wrapper)
