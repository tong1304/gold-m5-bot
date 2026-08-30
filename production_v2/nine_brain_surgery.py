from __future__ import annotations

"""Production-v2 nine-brain professional governance hardening.

This layer does not manufacture trading evidence and does not loosen any gate.
It fixes the boundary between *current evidence* and *future invalidation rules*,
then exposes an explicit lifecycle/next-event contract for every brain.
"""

from typing import Any

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")

OWNERS = {
    "E1": "MARKET_STATE",
    "E2": "OPPORTUNITY_REGIME",
    "E3": "MARKET_STRUCTURE",
    "E4": "LIQUIDITY_AUCTION",
    "E5": "LOCATION_VALUE",
    "E6": "SETUP_FORMATION",
    "E7": "CONFIRMATION",
    "E8": "TRADE_ECONOMICS_RISK",
    "E9": "FINAL_MARKET_CONTROL",
}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _active_codes(output: dict[str, Any]) -> list[str]:
    """Return only present-tense reason evidence.

    `invalidations` is intentionally excluded: those are conditions to watch for,
    not proof that the condition is occurring on the current closed candle.
    """
    values = []
    for key in ("reason_codes", "reasons", "blockers", "risk_blockers", "economic_blockers", "conflicts"):
        values.extend(_list(output.get(key)))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        token = _text(value)
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _future_invalidations(output: dict[str, Any]) -> list[str]:
    values = _list(output.get("invalidations"))
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _text(value)
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _explicit_active_invalidations(output: dict[str, Any]) -> list[str]:
    value = output.get("active_invalidations")
    if isinstance(value, dict):
        return [_text(k) for k, v in value.items() if v]
    return [_text(v) for v in _list(value) if _text(v)]


def _next_event(engine_id: str, output: dict[str, Any]) -> str:
    missing = _list(output.get("missing_evidence"))
    if missing:
        return _text(missing[0])
    for key in ("next_required_event", "opportunity_next_event", "confirmation_required", "required_confirmation", "required_evidence"):
        value = output.get(key)
        if isinstance(value, (list, tuple, set)) and value:
            return _text(list(value)[0])
        if value not in (None, ""):
            return _text(value)
    defaults = {
        "E1": "NEXT_CLOSED_M5_CANDLE_REVALIDATES_MARKET_STATE",
        "E2": "DIRECTIONAL_CONVERGENCE_AND_AUCTION_ACCEPTANCE",
        "E3": "NEXT_CAUSAL_STRUCTURE_EVENT_OR_PROTECTED_LEVEL_TEST",
        "E4": "CLOSED_CANDLE_FOLLOW_THROUGH_OR_REJECTION_RECLAIM",
        "E5": "ADVANTAGEOUS_LOCATION_WITH_SUFFICIENT_OPPOSING_SPACE",
        "E6": "SETUP_SPECIFIC_FORMATION_EVIDENCE",
        "E7": "VALID_CLOSED_CANDLE_CONFIRMATION",
        "E8": "VALID_TRADE_GEOMETRY_AND_RISK_ACCEPTANCE",
        "E9": "ALL_REQUIRED_GATES_PROVEN_WITH_NO_VETO",
    }
    return defaults[engine_id]


def _lifecycle(engine_id: str, output: dict[str, Any]) -> str:
    if _explicit_active_invalidations(output):
        return "INVALIDATED"
    if engine_id == "E1":
        return _text(output.get("analysis_status")) or "UNRESOLVED"
    if engine_id == "E2":
        return _text(output.get("opportunity_maturity")) or _text(output.get("opportunity_state")) or "UNRESOLVED"
    if engine_id == "E3":
        return _text(output.get("lifecycle")) or _text(output.get("structure_state")) or "UNRESOLVED"
    if engine_id == "E4":
        return _text(output.get("auction_state")) or _text(output.get("state")) or "UNRESOLVED"
    if engine_id == "E5":
        return _text(output.get("repricing_state")) or _text(output.get("location_state")) or "UNRESOLVED"
    if engine_id == "E6":
        return _text(output.get("setup_state")) or _text(output.get("state")) or "UNRESOLVED"
    if engine_id == "E7":
        return _text(output.get("confirmation_state")) or _text(output.get("proof_state")) or "UNRESOLVED"
    if engine_id == "E8":
        return _text(output.get("risk_state")) or _text(output.get("economic_state")) or "UNRESOLVED"
    return _text(output.get("decision")) or "UNRESOLVED"


def harden_engine(engine_id: str, raw_output: dict[str, Any]) -> dict[str, Any]:
    """Apply non-invasive professional boundary hardening to one engine output."""
    output = dict(raw_output or {})
    active = _active_codes(output)
    future = _future_invalidations(output)
    active_invalidations = _explicit_active_invalidations(output)

    # A plain list named `invalidations` is a catalogue of future failure rules.
    # Only an explicit `active_invalidations` field can assert present invalidation.
    output["future_invalidation_conditions"] = future
    output["active_invalidations"] = active_invalidations
    output["active_reason_codes"] = active
    output["surgery_boundary"] = "PRESENT_EVIDENCE_SEPARATED_FROM_FUTURE_INVALIDATION_RULES"
    output["professional_contract"] = {
        "engine": engine_id,
        "owner": OWNERS[engine_id],
        "decision_authority": "E9_ONLY",
        "can_create_thesis": engine_id in {"E2", "E6"},
        "can_authorize_entry": False,
        "closed_candle_only": True,
        "lifecycle": _lifecycle(engine_id, output),
        "next_required_event": _next_event(engine_id, output),
        "active_invalidated": bool(active_invalidations),
    }

    # Preserve a useful distinction for downstream brains.
    if engine_id == "E1" and _text(output.get("analysis_status")) == "COMPLETE":
        output["data_integrity_current"] = "VALIDATED"
        output["data_integrity_future_failures"] = [x for x in future if "DATA" in x]
    elif engine_id == "E3" and _text(output.get("lifecycle")) == "TRANSITION":
        output["transition_is_not_invalidation"] = True
    elif engine_id == "E4":
        state = _text(output.get("auction_state"))
        output["auction_confirmation_proven"] = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "RECLAIMED"}
        if state == "PENDING":
            output["auction_confirmation_pending"] = True
    elif engine_id == "E6":
        output["setup_authorization"] = "NONE"
    elif engine_id == "E7":
        output["confirmation_authorization"] = "PROOF_ONLY"
    elif engine_id == "E8":
        output["execution_authorization"] = "NONE"
    elif engine_id == "E9":
        output["master_authority"] = "SOLE_FINAL_AUTHORITY"
        output["upstream_evidence_only"] = True

    return output


def harden_all(outputs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {engine_id: harden_engine(engine_id, outputs.get(engine_id, {})) for engine_id in ENGINE_ORDER if engine_id in outputs}
