from __future__ import annotations

"""Nine-brain profit-opportunity synthesis.

This layer makes economic opportunity visible without weakening any execution
veto. E1-E7 describe directional/structural evidence, E8 owns trade
 economics, and E9 owns execution authority.
"""

from typing import Any

ENGINES = tuple(f"E{i}" for i in range(1, 10))
DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value if value is not None else "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    candidates = (
        output.get("direction"),
        output.get("opportunity_direction"),
        output.get("market_direction"),
        output.get("structure_direction"),
        output.get("pressure"),
        output.get("decision"),
        output.get("finding"),
        output.get("market_state"),
    )
    for value in candidates:
        text = _text(value)
        if text in DIRECTIONS or text in {"UP", "BULLISH", "TREND_UP"} or text.startswith(("BUY ", "BUY_")):
            return "BUY"
        if text in {"DOWN", "BEARISH", "TREND_DOWN"} or text.startswith(("SELL ", "SELL_")):
            return "SELL"
    return "NEUTRAL"


def _number(output: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(output.get(key))
        except (TypeError, ValueError):
            continue
        if value == value and abs(value) != float("inf"):
            return value
    return None


def _codes(output: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in ("reasons", "reason_codes", "blockers", "vetoes", "hard_veto", "conflicts", "invalidations"):
        value = output.get(key)
        if isinstance(value, str):
            found.append(_text(value))
        elif isinstance(value, dict):
            found.extend(_text(k) for k, v in value.items() if v)
        elif isinstance(value, (list, tuple, set)):
            found.extend(_text(v) for v in value if v)
    return list(dict.fromkeys(x for x in found if x))


def _has_code(codes: list[str], *needles: str) -> bool:
    return any(any(needle in code for needle in needles) for code in codes)


def synthesize_profit_opportunity(results: dict[str, Any]) -> dict[str, Any]:
    """Synthesize a conditional profit path while preserving E8/E9 authority.

    An opportunity is visible when directional, structural and auction/value
    evidence converge. It becomes execution-ready only when E8 economics and
    E9 authority explicitly pass. This prevents the opportunity layer from
    becoming a hidden signal generator.
    """
    outputs: dict[str, dict[str, Any]] = {}
    for engine in ENGINES:
        result = results.get(engine)
        output = result.output if hasattr(result, "output") else result
        if isinstance(output, dict):
            outputs[engine] = output

    directions = [_direction(outputs[e]) for e in ENGINES if e in outputs]
    buy_votes = directions.count("BUY")
    sell_votes = directions.count("SELL")
    if buy_votes == sell_votes:
        direction = "NEUTRAL"
    else:
        direction = "BUY" if buy_votes > sell_votes else "SELL"

    evidence: list[str] = []
    for engine in ENGINES:
        if engine not in outputs:
            continue
        d = _direction(outputs[engine])
        if d == direction:
            evidence.append(engine)

    e1 = outputs.get("E1", {})
    e2 = outputs.get("E2", {})
    e3 = outputs.get("E3", {})
    e4 = outputs.get("E4", {})
    e5 = outputs.get("E5", {})
    e6 = outputs.get("E6", {})
    e7 = outputs.get("E7", {})
    e8 = outputs.get("E8", {})
    e9 = outputs.get("E9", {})

    directional_context = _direction(e1) == direction or _direction(e2) == direction
    structure_context = _direction(e3) == direction or _text(e3.get("structure_lifecycle") or e3.get("lifecycle")) in {"ESTABLISHED", "CONFIRMED"}
    auction_context = _direction(e4) == direction or _text(e4.get("auction_state") or e4.get("auction_phase")) in {"ACCEPTED", "CONFIRMED", "RECLAIMED", "REJECTED", "TERMINALLY_CONFIRMED"}
    space = _number(e5, "available_space_atr_long" if direction == "BUY" else "available_space_atr_short", "effective_space_atr", "space_atr")
    space_ok = space is not None and space >= 1.0
    setup_context = _direction(e6) == direction
    confirmation_context = _text(e7.get("confirmation_state")) in {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"}

    opportunity = direction in DIRECTIONS and directional_context and (structure_context or auction_context) and (space_ok or setup_context)

    e8_plan = e8.get("trade_plan")
    e8_valid = isinstance(e8_plan, dict) and bool(e8_plan.get("valid"))
    e8_rr = _number(e8, "real_rr", "rr", "risk_reward")
    e8_blockers = _codes(e8)
    economics_blocked = (not e8_valid) or _has_code(e8_blockers, "REAL_RR_BELOW_MINIMUM", "INVALID_TRADE_GEOMETRY", "NO_USABLE_STRUCTURAL_TARGET", "STOP_TOO_WIDE", "TARGET_REALISM_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY")

    e9_decision = _text(e9.get("decision"))
    e9_gate = bool(e9.get("gate_passed"))
    e9_execution = _text(e9.get("execution"))
    execution_ready = bool(opportunity and e8_valid and not economics_blocked and e9_gate and e9_decision == direction and e9_execution == "APPROVED")

    if not opportunity:
        edge_stage = "NO_CONVERGENT_OPPORTUNITY"
    elif economics_blocked:
        edge_stage = "ECONOMICS_BLOCKED"
    elif not confirmation_context:
        edge_stage = "WAITING_CONFIRMATION"
    elif not execution_ready:
        edge_stage = "CONTROLLED_WAIT"
    else:
        edge_stage = "EXECUTABLE"

    missing: list[str] = []
    if not directional_context:
        missing.append("DIRECTIONAL_CONTROL")
    if not structure_context and not auction_context:
        missing.append("STRUCTURE_OR_AUCTION_PROOF")
    if not space_ok and not setup_context:
        missing.append("PROFIT_SPACE")
    if opportunity and not confirmation_context:
        missing.append("CLOSED_CANDLE_CONFIRMATION")
    if economics_blocked:
        missing.append("E8_TRADE_ECONOMICS")
    if not execution_ready:
        missing.append("E9_EXECUTION_AUTHORITY")

    return {
        "opportunity": bool(opportunity),
        "direction": direction,
        "edge_stage": edge_stage,
        "execution_ready": execution_ready,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "directional_votes": {"BUY": buy_votes, "SELL": sell_votes},
        "space_atr": space,
        "real_rr": e8_rr,
        "confirmation": confirmation_context,
        "economics_valid": e8_valid and not economics_blocked,
        "blockers": e8_blockers,
        "missing": list(dict.fromkeys(missing)),
        "profit_path": (
            f"{direction} only after closed-candle confirmation, survivable E8 geometry, and E9 authority"
            if direction in DIRECTIONS else "Wait for directional and structural/auction convergence"
        ),
        "authority": "E9_ONLY",
        "execution_separation": True,
    }
