from __future__ import annotations

"""Professional opportunity synthesis for production-v2.

This layer is deliberately non-authoritative: it makes conditional profit
opportunities visible without manufacturing a BUY/SELL decision. E9 remains
the sole execution authority.
"""

from typing import Any

from .contracts import DecisionResult, EngineResult


DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    for key in ("direction", "opportunity_direction", "direction_thesis", "thesis_direction"):
        value = _text(output.get(key))
        if value in DIRECTIONS:
            return value
        if value in {"UP", "BULLISH", "TREND_UP"}:
            return "BUY"
        if value in {"DOWN", "BEARISH", "TREND_DOWN"}:
            return "SELL"
    finding = _text(output.get("finding"))
    if finding.startswith(("BUY ", "BUY_")):
        return "BUY"
    if finding.startswith(("SELL ", "SELL_")):
        return "SELL"
    return "NEUTRAL"


def _codes(output: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "missing_evidence", "blockers", "conflicts", "invalidations"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(_text(value))
        elif isinstance(value, (list, tuple, set)):
            values.extend(_text(x) for x in value if x)
        elif isinstance(value, dict):
            values.extend(_text(k) for k, v in value.items() if v)
    return list(dict.fromkeys(x for x in values if x))


def _has(output: dict[str, Any], *needles: str) -> bool:
    haystack = " ".join([_text(output.get("finding")), _text(output.get("state")), *_codes(output)])
    return any(n in haystack for n in needles)


def _space(output: dict[str, Any], direction: str) -> float | None:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short" if direction == "SELL" else "effective_space_atr"
    try:
        value = float(output.get(key))
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def _brain(results: tuple[EngineResult, ...], engine_id: str) -> dict[str, Any]:
    for result in results:
        if result.engine_id == engine_id:
            return dict(result.output or {})
    return {}


def synthesize(engines: tuple[EngineResult, ...]) -> dict[str, Any]:
    """Build a conditional opportunity map from the already completed brains."""
    e1 = _brain(engines, "E1")
    e2 = _brain(engines, "E2")
    e3 = _brain(engines, "E3")
    e4 = _brain(engines, "E4")
    e5 = _brain(engines, "E5")
    e6 = _brain(engines, "E6")
    e7 = _brain(engines, "E7")
    e8 = _brain(engines, "E8")
    e9 = _brain(engines, "E9")

    directions = [_direction(x) for x in (e1, e2, e3, e4, e5, e6)]
    counts = {d: directions.count(d) for d in DIRECTIONS}
    dominant = max(counts, key=counts.get) if max(counts.values(), default=0) else "NEUTRAL"
    agreement = counts.get(dominant, 0) / 6.0 if dominant in DIRECTIONS else 0.0

    setup = _text(e6.get("setup") or e6.get("setup_family") or e6.get("setup_type"))
    setup_state = _text(e6.get("setup_state") or e6.get("opportunity_stage") or e6.get("state"))
    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("state"))
    economics = _text(e8.get("economic_state") or e8.get("risk_state") or (e8.get("profit_edge") or {}).get("state"))

    support: list[str] = []
    counter: list[str] = []
    missing: list[str] = []

    if dominant in DIRECTIONS:
        support.append(f"DIRECTIONAL_CONSENSUS={counts[dominant]}/6")
    if _has(e3, "BOS_UP", "BULLISH_STRUCTURE") and dominant == "BUY":
        support.append("BULLISH_STRUCTURE_SUPPORT")
    if _has(e3, "BOS_DOWN", "BEARISH_STRUCTURE") and dominant == "SELL":
        support.append("BEARISH_STRUCTURE_SUPPORT")
    if _has(e4, "SWEEP_REJECTION", "FAILED_BREAK_RECLAIM", "ACCEPTANCE"):
        support.append("LIQUIDITY_OR_AUCTION_EVENT_PRESENT")
    if _has(e5, "FAVORABLE_LOCATION", "LOCATION_ACTIONABLE"):
        support.append("LOCATION_SUPPORT")

    for output in (e2, e4, e5, e7, e8):
        for code in _codes(output):
            if any(x in code for x in ("CONFLICT", "PENDING", "INSUFFICIENT", "NOT_PROVEN", "NOT_TRUSTWORTHY", "CONSTRAINED", "INVALID", "BELOW_MINIMUM")):
                counter.append(code)

    if not _has(e4, "CONFIRMED", "ACCEPTED", "RECLAIMED", "TERMINAL"):
        missing.append("setup_specific_closed_candle_auction_or_liquidity_proof")
    if confirmation not in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY", "PASS"}:
        missing.append("valid_closed_candle_trigger_confirmation")
    if economics not in {"VALID", "VALIDATED", "TRADE_READY", "PASS", "POSITIVE"}:
        missing.append("survivable_trade_geometry_and_positive_profit_edge")

    space = _space(e5, dominant)
    if space is not None and space < 0.75:
        counter.append("STRUCTURAL_SPACE_CONSTRAINED")
        missing.append("adequate_opposing_space")

    hard_blockers = []
    for output in (e6, e7, e8, e9):
        for code in _codes(output):
            if any(x in code for x in ("INVALID_TRADE_GEOMETRY", "NO_USABLE_STRUCTURAL_TARGET", "REAL_RR_BELOW_MINIMUM", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "HARD_VETO")):
                hard_blockers.append(code)

    if dominant not in DIRECTIONS:
        state = "NO_DIRECTIONAL_EDGE"
    elif hard_blockers:
        state = "OPPORTUNITY_BLOCKED"
    elif setup and setup not in {"NONE", "UNKNOWN", "NO_SETUP"}:
        state = "OPPORTUNITY_FORMING" if missing else "OPPORTUNITY_READY_FOR_FINAL_AUTHORITY"
    else:
        state = "OPPORTUNITY_WATCH"

    if agreement < 0.50:
        state = "DIRECTIONAL_CONFLICT" if dominant in DIRECTIONS else state

    return {
        "architecture": "PROFESSIONAL_OPPORTUNITY_SYNTHESIS_V1",
        "authority": "OBSERVATIONAL_ONLY",
        "execution_authority": "E9_ONLY",
        "state": state,
        "direction": dominant,
        "directional_consensus": round(agreement, 3),
        "supporting_evidence": list(dict.fromkeys(support)),
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "hard_blockers": list(dict.fromkeys(hard_blockers)),
        "setup": setup or "UNKNOWN",
        "setup_state": setup_state or "UNKNOWN",
        "confirmation_state": confirmation or "UNKNOWN",
        "economic_state": economics or "UNKNOWN",
        "space_atr": space,
        "next_required_event": (missing[0] if missing else "E9_FINAL_AUTHORITY_CHECK"),
        "professional_rule": "SEE_OPPORTUNITY_FIRST_PROVE_IT_SECOND_EXECUTE_LAST",
        "trade_authorized": False,
    }


def enrich_decision(result: DecisionResult) -> DecisionResult:
    """Attach the opportunity radar without changing E9's decision authority."""
    radar = synthesize(result.engines)
    engines: list[EngineResult] = []
    for engine in result.engines:
        output = dict(engine.output or {})
        output["opportunity_radar"] = radar
        engines.append(EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes))

    risk = dict(result.risk or {})
    risk["opportunity_radar"] = radar
    risk["opportunity_authority"] = "E9_ONLY"

    # Never mutate decision, gate_passed, or score here. The wrapper is strictly
    # observational and cannot turn a NO_TRADE into BUY/SELL.
    return DecisionResult(
        symbol=result.symbol,
        timeframe=result.timeframe,
        decision=result.decision,
        gate_passed=result.gate_passed,
        score=result.score,
        engines=tuple(engines),
        risk=risk,
        reason_codes=result.reason_codes,
    )
