from __future__ import annotations

from typing import Any

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")

# Governance is a read-only contract. It never creates market evidence and never
# grants trade authority to E1-E8.
HARD_BLOCKER_KEYS = (
    "hard_veto",
    "hard_vetoes",
    "vetoes",
    "blocking_reasons",
)


def _output(results: dict[str, Any], engine: str) -> dict[str, Any]:
    value = results.get(engine)
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    value = getattr(value, "output", None)
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        return [str(k) for k, v in value.items() if v]
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value if x]
    return [str(value)]


def _first(output: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in output and output[key] not in (None, "", [], {}, ()):
            return output[key]
    return None


def _engine_blockers(engine: str, output: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key in HARD_BLOCKER_KEYS:
        blockers.extend(_items(output.get(key)))

    status = str(_first(output, "status", "analysis_status", "state") or "").upper()
    if status in {"UNAVAILABLE", "INCOMPLETE", "INSUFFICIENT_DATA", "ERROR"}:
        blockers.append(f"{engine}_{status}")

    gate = output.get("gate_passed")
    if gate is False:
        blockers.append(f"{engine}_GATE_FAILED")

    return list(dict.fromkeys(blockers))


def _missing(output: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("missing_evidence", "confirmation_required", "next_required_event"):
        values.extend(_items(output.get(key)))
    return list(dict.fromkeys(values))


def _direction(output: dict[str, Any]) -> str:
    value = _first(output, "direction", "opportunity_direction", "trend_state")
    raw = str(value or "NEUTRAL").upper().strip()
    if raw in {"UP", "BUY", "BULLISH", "LONG", "BUYERS", "TREND_UP"}:
        return "UP"
    if raw in {"DOWN", "SELL", "BEARISH", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "DOWN"
    return "NEUTRAL"


def _maturity(output: dict[str, Any]) -> str:
    value = _first(output, "opportunity_maturity", "maturity", "setup_stage", "opportunity_stage", "state")
    return str(value or "UNRESOLVED").upper()


def _auction_state(output: dict[str, Any]) -> str:
    return str(_first(output, "auction_state", "auction_phase", "liquidity_state") or "UNKNOWN").upper()


def _confirmation(output: dict[str, Any]) -> bool:
    for key in ("confirmation_passed", "confirmed", "closed_candle_confirmed", "trigger_confirmed"):
        if output.get(key) is True:
            return True
    value = str(_first(output, "confirmation_state", "confirmation", "state") or "").upper()
    return value in {"CONFIRMED", "VALID", "PASSED"}


def _economics_valid(output: dict[str, Any]) -> bool:
    for key in ("trade_economics_valid", "economics_valid", "trade_ready", "risk_ready"):
        if key in output and output[key] is False:
            return False
    plan = output.get("trade_plan")
    if isinstance(plan, dict) and plan.get("valid") is False:
        return False
    return True


def audit_engines(results: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic, read-only audit of the nine-engine evidence chain."""
    per_engine: dict[str, dict[str, Any]] = {}
    all_missing: list[str] = []
    all_blockers: list[str] = []
    directions: dict[str, str] = {}

    for engine in ENGINE_ORDER:
        output = _output(results, engine)
        blockers = _engine_blockers(engine, output)
        missing = _missing(output)
        direction = _direction(output)
        maturity = _maturity(output)
        directions[engine] = direction
        all_blockers.extend(f"{engine}:{x}" for x in blockers)
        all_missing.extend(f"{engine}:{x}" for x in missing)
        per_engine[engine] = {
            "present": bool(output),
            "direction": direction,
            "maturity": maturity,
            "auction_state": _auction_state(output),
            "confirmation_passed": _confirmation(output),
            "economics_valid": _economics_valid(output),
            "hard_blockers": list(dict.fromkeys(blockers)),
            "missing_evidence": list(dict.fromkeys(missing)),
        }

    directional = {d for d in directions.values() if d in {"UP", "DOWN"}}
    if len(directional) > 1:
        all_blockers.append("DIRECTIONAL_EVIDENCE_CONFLICT")

    e3 = per_engine["E3"]
    e4 = per_engine["E4"]
    e7 = per_engine["E7"]
    e8 = per_engine["E8"]

    e3_output = _output(results, "E3")
    lifecycle = str(_first(e3_output, "structure_lifecycle", "lifecycle") or "").upper()
    if "TRANSITION" in lifecycle or lifecycle == "INVALIDATED":
        all_blockers.append("STRUCTURE_NOT_RESOLVED")

    if e4["auction_state"] in {"PENDING", "UNKNOWN", "INITIATIVE", "UNRESOLVED"}:
        all_blockers.append("AUCTION_CONFIRMATION_PENDING")

    if not e7["confirmation_passed"]:
        all_blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")

    if not e8["economics_valid"]:
        all_blockers.append("TRADE_ECONOMICS_NOT_VALID")

    all_blockers = list(dict.fromkeys(all_blockers))
    all_missing = list(dict.fromkeys(all_missing))
    hard_veto = bool(all_blockers)

    next_event: list[str] = []
    for engine in ("E3", "E4", "E7", "E8"):
        next_event.extend(per_engine[engine]["missing_evidence"])
    if not next_event and hard_veto:
        next_event.append("resolve all hard blockers on a future closed candle")

    maturity = "BLOCKED" if hard_veto else "READY_FOR_E9_AUTHORITY_CHECK"
    return {
        "architecture": "NINE_BRAIN_PROFESSIONAL_GOVERNANCE_V1",
        "engine_order": list(ENGINE_ORDER),
        "hard_veto": hard_veto,
        "hard_vetoes": all_blockers,
        "missing_evidence": all_missing,
        "next_required_event": list(dict.fromkeys(next_event)),
        "maturity": maturity,
        "directional_conflict": "DIRECTIONAL_EVIDENCE_CONFLICT" in all_blockers,
        "per_engine": per_engine,
        "read_only": True,
        "e9_only_trade_authority": True,
    }


def enforce_final_authority(e9_output: dict[str, Any], audit: dict[str, Any]) -> tuple[str, bool, list[str]]:
    """Return the only final authorization allowed by the governance contract."""
    reasons = list(audit.get("hard_vetoes") or [])
    requested = str(e9_output.get("decision") or "NO_TRADE").upper()
    if audit.get("hard_veto"):
        reasons.append("NINE_BRAIN_GOVERNANCE_BLOCKED")
        return "NO_TRADE", False, list(dict.fromkeys(reasons))
    if requested not in {"BUY", "SELL"}:
        return "NO_TRADE", False, list(dict.fromkeys(reasons))
    return requested, True, list(dict.fromkeys(reasons))
