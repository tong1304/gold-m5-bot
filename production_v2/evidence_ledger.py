from __future__ import annotations

from typing import Any

from .contracts import EngineResult

ROLE = {
    "E1": "MARKET_STATE",
    "E2": "OPPORTUNITY_REGIME",
    "E3": "MARKET_STRUCTURE",
    "E4": "LIQUIDITY_AUCTION",
    "E5": "LOCATION_VALUE",
    "E6": "SETUP_FORMATION",
    "E7": "CONFIRMATION",
    "E8": "TRADE_ECONOMICS_RISK",
}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def classify_conflict(code: str, *, confirmed: bool = False, invalidating: bool = False) -> str:
    """Classify specialist tension without making a trade decision."""
    if invalidating and confirmed:
        return "HARD"
    if confirmed:
        return "CONFIRMED"
    return "SOFT"


def _brain_record(engine_id: str, engine: EngineResult) -> dict[str, Any]:
    output = dict(engine.output or {})
    direction = (
        output.get("direction")
        or output.get("direction_thesis")
        or output.get("thesis_direction")
        or output.get("opportunity_direction")
    )
    invalidations = _list(output.get("active_invalidations") or output.get("invalidations"))
    counter = _list(output.get("counter_evidence") or output.get("counter_evidence_codes"))
    missing = _list(output.get("missing_evidence") or output.get("missing_proof") or output.get("next_required_events"))
    proof = output.get("confirmation_state") or output.get("proof_state") or output.get("thesis_state") or output.get("state")
    return {
        "role": ROLE.get(engine_id, "SPECIALIST"),
        "direction": direction,
        "interpretation": output.get("finding"),
        "supporting_evidence": _list(output.get("observations") or output.get("evidence")),
        "counter_evidence": counter,
        "missing_evidence": missing,
        "proof_state": proof,
        "invalidations": invalidations,
        "reason_codes": _list(output.get("reason_codes") or output.get("reasons")),
        "gate_passed": engine.gate_passed,
    }


def build_evidence_ledger(results: dict[str, EngineResult]) -> dict[str, Any]:
    """Build a non-authoritative collaboration view from E1-E8 outputs."""
    brains: dict[str, Any] = {}
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = results.get(engine_id)
        if isinstance(engine, EngineResult):
            brains[engine_id] = _brain_record(engine_id, engine)
    return {
        "schema": "EVIDENCE_LEDGER_V1",
        "authority": "NON_AUTHORITATIVE",
        "decision_authority": "E9_ONLY",
        "principle": "SPECIALISTS_SHARE_EVIDENCE;_E9_RECONCILES_DECISION",
        "brains": brains,
    }


def ledger_for_e9(results: dict[str, EngineResult]) -> dict[str, Any]:
    ledger = build_evidence_ledger(results)
    ledger["decision"] = None
    ledger["decision_write_authority"] = "E9_ONLY"
    return ledger
