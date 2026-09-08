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
        "decision": None,
        "brains": {key: _brain_output(value, key) for key, value in upstream.items() if key in _FINAL_BRAINS},
    }


def preserve_e6_thesis_contract(e6: dict[str, Any], e9: dict[str, Any]) -> dict[str, Any]:
    output = dict(e9 or {})
    if e6:
        output.setdefault("thesis_source", "E6")
        output["e6_thesis"] = {
            key: e6.get(key)
            for key in ("setup", "setup_state", "opportunity_stage", "candidate_type", "direction", "thesis_status", "watch_only", "trade_ready")
            if key in e6
        }
    return output


def _directional_helper_compat(original):
    """Keep the pre-V2 public E6 helper shape without changing E6 authority."""
    def compatible(primary: Any, *others: Any):
        values = (primary, *others)

        def text(value: Any) -> str:
            return str(value or "").upper().strip()

        def direction(value: Any) -> str:
            value = text(value)
            if value in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP"} or value.startswith("BUY_"):
                return "BUY"
            if value in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN"} or value.startswith("SELL_"):
                return "SELL"
            return "NEUTRAL"

        e1 = primary if isinstance(primary, dict) else {}
        e2 = values[1] if len(values) > 1 and isinstance(values[1], dict) else {}
        e3 = values[2] if len(values) > 2 and isinstance(values[2], dict) else {}
        e4 = values[3] if len(values) > 3 and isinstance(values[3], dict) else {}
        core = direction(e1.get("directional_pressure", e1.get("direction")))
        structure = direction(e3.get("external_state", e3.get("internal_state", e3.get("direction"))))
        auction_state = text(e4.get("auction_state", e4.get("state")))
        event = text(e4.get("event", e4.get("finding")))
        auction_direction = direction(e4.get("direction"))
        if auction_direction == "NEUTRAL" and "FAILED_BREAK_RECLAIM" in event:
            auction_direction = direction(e4.get("response_actor"))
        if auction_direction == "NEUTRAL" and "HIGH" in event and any(x in event for x in ("REJECTION", "SWEEP")):
            auction_direction = "SELL"
        if auction_direction == "NEUTRAL" and "LOW" in event and any(x in event for x in ("REJECTION", "SWEEP")):
            auction_direction = "BUY"
        if auction_direction in {"BUY", "SELL"} and auction_state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"} and core == "NEUTRAL" and structure == "NEUTRAL":
            return auction_direction, ["E4_TERMINAL_AUCTION"], [], "E4_TERMINAL_AUCTION"
        chosen = core if core in {"BUY", "SELL"} else structure if structure in {"BUY", "SELL"} else auction_direction
        conflicts = []
        if auction_direction in {"BUY", "SELL"} and chosen in {"BUY", "SELL"} and auction_direction != chosen:
            conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
        source = "E1_E3_DIRECTIONAL_CORE" if core in {"BUY", "SELL"} and structure == core else "E3_STRUCTURE_CONVERGENCE" if structure in {"BUY", "SELL"} else "E4_TERMINAL_AUCTION" if auction_direction in {"BUY", "SELL"} else "NONE"
        support = [x for x in ("E1_DIRECTIONAL_CORE" if core in {"BUY", "SELL"} else None, "E3_STRUCTURE_SUPPORT" if structure == chosen and structure in {"BUY", "SELL"} else None) if x]
        return chosen, support, conflicts, source
    return compatible


def install(e6_module: Any, e9_module: Any) -> None:
    """Attach evidence context and preserve the legacy E6 directional helper contract."""
    if not getattr(e6_module, "_E6_DIRECTION_HELPER_COMPAT", False):
        e6_module._direction = _directional_helper_compat(getattr(e6_module, "_direction", None))
        e6_module._E6_DIRECTION_HELPER_COMPAT = True

    def e9_wrapper(original):
        def wrapped(snapshot, upstream):
            if isinstance(snapshot, dict):
                snapshot["evidence_ledger"] = ledger_for_e9(upstream)
            result = original(snapshot, upstream)
            e6 = dict(getattr(upstream.get("E6"), "output", {}) or {})
            output = preserve_e6_thesis_contract(e6, dict(getattr(result, "output", {}) or {}))
            return type(result)(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)
        return wrapped

    _install_once(e9_module, "_EVIDENCE_COLLABORATION_E9_INSTALLED", "analyze_e9", e9_wrapper)
