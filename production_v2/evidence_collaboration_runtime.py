from __future__ import annotations

from typing import Any


_PRE_THESIS_BRAINS = {"E1", "E2", "E3", "E4", "E5"}
_FINAL_BRAINS = {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"}


def _install_once(module: Any, marker: str, attr: str, wrapper_factory) -> None:
    if getattr(module, marker, False):
        return
    original = getattr(module, attr)
    setattr(module, attr, wrapper_factory(original))
    setattr(module, marker, True)


def _brain_output(value: Any, engine_id: str) -> dict[str, Any]:
    output = dict(getattr(value, "output", {}) or {})
    if engine_id == "E4" and "proof_state" not in output:
        finding = str(output.get("finding") or output.get("auction_state") or "").upper()
        if "PENDING" in finding:
            output["proof_state"] = "PENDING"
        elif any(token in finding for token in ("CONFIRMED", "ACCEPTED", "PROVEN")):
            output["proof_state"] = "PROVEN"
        elif any(token in finding for token in ("FAILED", "INVALID", "REJECTED")):
            output["proof_state"] = "FAILED"
        else:
            output["proof_state"] = "UNRESOLVED"
    return output


def build_evidence_ledger(upstream: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "EVIDENCE_LEDGER_V1",
        "phase": "PRE_THESIS_E1_E5",
        "brains": {key: _brain_output(value, key) for key, value in upstream.items() if key in _PRE_THESIS_BRAINS},
    }


def ledger_for_e9(upstream: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "EVIDENCE_LEDGER_V1",
        "phase": "FINAL_GOVERNANCE_E1_E8",
        "brains": {key: _brain_output(value, key) for key, value in upstream.items() if key in _FINAL_BRAINS},
    }


def preserve_e6_thesis_contract(e6: dict[str, Any], e9: dict[str, Any]) -> dict[str, Any]:
    output = dict(e9 or {})
    if e6:
        output.setdefault("thesis_source", "E6")
        output["e6_thesis"] = {key: e6.get(key) for key in ("setup", "setup_state", "opportunity_stage", "candidate_type", "direction", "thesis_status", "watch_only", "trade_ready") if key in e6}
    return output


def install(e6_module: Any, e9_module: Any) -> None:
    """Expose evidence context without changing specialist authority."""
    def e6_wrapper(original):
        def wrapped(market_data, upstream):
            # Some legacy/direct tests pass a list as market_data. Evidence
            # collaboration is observability only; never fail E6 because that
            # caller shape cannot carry an injected ledger.
            if isinstance(market_data, dict):
                market_data["evidence_ledger"] = build_evidence_ledger(upstream)
            return original(market_data, upstream)
        return wrapped

    def e9_wrapper(original):
        def wrapped(snapshot, upstream):
            if isinstance(snapshot, dict):
                snapshot["evidence_ledger"] = ledger_for_e9(upstream)
            result = original(snapshot, upstream)
            e6 = dict(getattr(upstream.get("E6"), "output", {}) or {})
            output = preserve_e6_thesis_contract(e6, dict(getattr(result, "output", {}) or {}))
            return type(result)(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)
        return wrapped

    _install_once(e6_module, "_EVIDENCE_COLLABORATION_E6_INSTALLED", "analyze_e6", e6_wrapper)
    _install_once(e9_module, "_EVIDENCE_COLLABORATION_E9_INSTALLED", "analyze_e9", e9_wrapper)
