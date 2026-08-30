from __future__ import annotations

"""Bounded opportunity intelligence for the nine professional brains.

Every engine may describe the opportunity visible inside its own domain.
This layer NEVER creates an entry, changes an engine thesis, or authorizes a
trade. E9 remains the only final BUY/SELL authority.
"""

from typing import Any

DIRECTIONS = {"BUY", "SELL"}
ENGINE_SCOPES = {
    "E1": "MARKET_STATE",
    "E2": "OPPORTUNITY_REGIME",
    "E3": "MARKET_STRUCTURE",
    "E4": "LIQUIDITY_AUCTION",
    "E5": "LOCATION_VALUE",
    "E6": "SETUP_FORMATION",
    "E7": "CONFIRMATION",
    "E8": "TRADE_ECONOMICS",
    "E9": "MARKET_CONTROL",
}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value if value is not None else "").upper().strip()


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS:
            return x
        if x.startswith(("BUY ", "BUY_", "BUY:")) or x in {"UP", "BULLISH", "TREND_UP"}:
            return "BUY"
        if x.startswith(("SELL ", "SELL_", "SELL:")) or x in {"DOWN", "BEARISH", "TREND_DOWN"}:
            return "SELL"
    return "NEUTRAL"


def _codes(output: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in (
        "reason_codes", "reasons", "counter_evidence", "blockers", "conflicts",
        "invalidations", "vetoes", "hard_veto", "secondary_blockers",
    ):
        value = output.get(key)
        if isinstance(value, str):
            found.append(_text(value))
        elif isinstance(value, dict):
            for k, v in value.items():
                if v is True:
                    found.append(_text(k))
                elif isinstance(v, (str, int, float)) and str(v).strip():
                    found.append(_text(v))
        elif isinstance(value, (list, tuple, set)):
            found.extend(_text(v) for v in value if v is not None)
    return list(dict.fromkeys(x for x in found if x))


def _numeric(output: dict[str, Any], *keys: str) -> list[float]:
    values: list[float] = []
    for key in keys:
        try:
            value = float(output.get(key))
        except (TypeError, ValueError):
            continue
        if value == value and abs(value) != float("inf"):
            values.append(value)
    return values


def _space_score(output: dict[str, Any], direction: str) -> float:
    if direction == "BUY":
        keys = ("available_space_atr_long", "long_space_atr", "effective_space_atr", "space_atr")
    elif direction == "SELL":
        keys = ("available_space_atr_short", "short_space_atr", "effective_space_atr", "space_atr")
    else:
        keys = ("effective_space_atr", "space_atr")
    vals = _numeric(output, *keys)
    if not vals:
        return 0.5
    return max(0.0, min(1.0, min(vals) / 2.0))


def _evidence_score(output: dict[str, Any]) -> float:
    for key in ("confidence", "evidence_strength", "quality", "opportunity_score"):
        value = output.get(key)
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if x == x and abs(x) != float("inf"):
            return max(0.0, min(1.0, x / 100.0 if x > 1.0 else x))
    return 0.0


def _hard_blocked(codes: list[str], output: dict[str, Any]) -> bool:
    text = " ".join(codes)
    state = _text(output.get("state") or output.get("decision_state") or output.get("execution_state"))
    return any(token in text for token in (
        "INVALIDATED", "HARD_VETO", "RISK_BLOCKED", "INVALID_TRADE_GEOMETRY",
        "NO_USABLE_STRUCTURAL_TARGET", "ENTRY_CONFIRMATION", "STOP_TOO_WIDE",
    )) or any(token in state for token in ("INVALIDATED", "BLOCKED", "UNRESOLVED"))


def _stage(engine_id: str, direction: str, codes: list[str], output: dict[str, Any]) -> str:
    """Classify opportunity maturity without confusing thesis validation with trade confirmation."""
    state = _text(output.get("state") or output.get("finding") or output.get("lifecycle"))
    text = " ".join(codes)
    if "INVALIDATED" in state or any(x in text for x in ("INVALIDATED", "HARD_VETO")):
        return "INVALIDATED"
    if engine_id == "E9":
        decision = _text(output.get("decision"))
        if decision in DIRECTIONS and bool(output.get("gate_passed")):
            return "EXECUTABLE"
        return "CONTROLLED_WAIT"
    if engine_id == "E8":
        if _hard_blocked(codes, output):
            return "ECONOMICALLY_BLOCKED"
        if any(x in text for x in ("TRADE_READY", "PROVEN", "CONFIRMED")):
            return "ECONOMICALLY_VALIDATED"
        return "ECONOMICALLY_ASSESSED"
    if engine_id == "E7":
        confirmation = _text(output.get("confirmation_state"))
        if confirmation in {"PROVEN", "CONFIRMED"}:
            return "CONFIRMED"
        return "WAITING_CONFIRMATION" if direction in DIRECTIONS else "CONFIRMATION_WATCH"
    if engine_id == "E6":
        if any(x in text for x in ("SETUP_INVALIDATED", "SETUP_NOT_TRADE_READY")):
            return "VALIDATING"
        if any(x in text for x in ("SETUP_CONFIRMED", "TRADE_READY")):
            return "MATURE"
        return "FORMING" if direction in DIRECTIONS else "NO_SETUP"
    if engine_id == "E4":
        auction = _text(output.get("auction_state") or output.get("auction_phase"))
        if auction in {"CONFIRMED", "ACCEPTED", "REJECTED"}:
            return "AUCTION_CONFIRMED"
        return "AUCTION_PENDING" if direction in DIRECTIONS else "LIQUIDITY_WATCH"
    if engine_id == "E3":
        lifecycle = _text(output.get("lifecycle") or output.get("structure_state"))
        if lifecycle in {"CONFIRMED", "ESTABLISHED"}:
            return "STRUCTURE_CONFIRMED"
        if direction in DIRECTIONS:
            return "STRUCTURE_FORMING"
        return "STRUCTURE_WATCH"
    if engine_id == "E2":
        maturity = _text(output.get("opportunity_maturity"))
        if maturity in {"ACTIONABLE", "CONFIRMED"}:
            return "REGIME_CONFIRMED"
        if direction in DIRECTIONS:
            return "REGIME_DEVELOPING"
        return "REGIME_UNRESOLVED"
    if engine_id == "E1":
        state = _text(output.get("market_state") or output.get("state"))
        if state in {"TREND_UP", "TREND_DOWN", "EXPANSION", "RANGE", "COMPRESSION", "TRANSITION"}:
            return "STATE_ESTABLISHED"
        return "STATE_UNCLEAR"
    return "OBSERVATION"


def _scope_opportunities(engine_id: str, output: dict[str, Any], direction: str) -> tuple[list[str], str]:
    state = _text(output.get("market_state") or output.get("state") or output.get("regime"))
    finding = _text(output.get("finding"))
    event = _text(output.get("event") or output.get("auction_event") or output.get("liquidity_event"))
    setup = _text(output.get("setup") or output.get("setup_family") or output.get("setup_type"))

    if engine_id == "E1":
        types = []
        if direction in DIRECTIONS and state in {"TREND_UP", "TREND_DOWN", "EXPANSION"}:
            types.append("DIRECTIONAL_CONTINUATION_CONTEXT")
        if state == "RANGE":
            types.append("RANGE_ROTATION_CONTEXT")
        if state == "COMPRESSION":
            types.append("BREAKOUT_EXPANSION_WATCH")
        if state == "TRANSITION":
            types.append("REGIME_TRANSITION_WATCH")
        return types or ["NO_CLEAR_MARKET_STATE_EDGE"], "NEXT_CLOSED_CANDLE_STATE_UPDATE"
    if engine_id == "E2":
        raw = output.get("candidate_hypotheses") or output.get("candidate_setups") or output.get("opportunity_types")
        types = [_text(x) for x in raw] if isinstance(raw, (list, tuple, set)) else []
        return types or (["CONDITIONAL_DIRECTIONAL_OPPORTUNITY"] if direction in DIRECTIONS else ["NO_DIRECTIONAL_OPPORTUNITY"]), "REGIME_ACCEPTANCE_AND_FOLLOW_THROUGH"
    if engine_id == "E3":
        return (["STRUCTURAL_CONTINUATION"] if direction in DIRECTIONS else ["STRUCTURAL_REVERSAL_WATCH"]), "BOS_CHOCH_OR_PROTECTED_LEVEL_REACTION"
    if engine_id == "E4":
        if "SWEEP" in event or "FAILED_BREAK" in event or "REJECTION" in event:
            return ["LIQUIDITY_REVERSAL_OPPORTUNITY"], "RECLAIM_AND_FOLLOW_THROUGH"
        if "ACCEPT" in event or "INITIATIVE" in event:
            return ["LIQUIDITY_ACCEPTANCE_CONTINUATION_WATCH"], "ACCEPTANCE_FOLLOW_THROUGH"
        return ["LIQUIDITY_INTERACTION_WATCH"], "RECLAIM_OR_ACCEPTANCE"
    if engine_id == "E5":
        location = _text(output.get("structural_location") or output.get("value_state") or output.get("location"))
        if "RESISTANCE" in location and direction == "SELL":
            return ["RESISTANCE_SELL_LOCATION"], "CLOSED_CANDLE_REJECTION_OR_ACCEPTANCE"
        if "SUPPORT" in location and direction == "BUY":
            return ["SUPPORT_BUY_LOCATION"], "CLOSED_CANDLE_REJECTION_OR_ACCEPTANCE"
        return (["LOCATION_CONTINUATION_WATCH"] if direction in DIRECTIONS else ["LOCATION_EDGE_UNCLEAR"]), "PRICE_RESPONSE_AT_VALUE_OR_STRUCTURE"
    if engine_id == "E6":
        return [setup or finding or "SETUP_CANDIDATE"], "SETUP_SPECIFIC_CONFIRMATION"
    if engine_id == "E7":
        return (["VALID_CLOSED_CANDLE_CONFIRMATION"] if direction in DIRECTIONS else ["CONFIRMATION_WATCH"]), "FOLLOW_THROUGH_OR_INVALIDATION"
    if engine_id == "E8":
        return (["TRADE_ECONOMICS_VIABLE"] if not _hard_blocked(_codes(output), output) else ["TRADE_ECONOMICS_CONSTRAINED"]), "SURVIVABLE_GEOMETRY_AND_REALISTIC_TARGET"
    return ["MASTER_MARKET_CONTROL"], "NONE"


def enrich_opportunity(engine_id: str, output: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose a professional opportunity map inside each engine's own boundary."""
    out = dict(output or {})
    ctx = context or {}
    direction = _direction(
        out.get("direction"), out.get("structure_direction"), out.get("pressure"),
        out.get("market_direction"), out.get("finding"), out.get("market_state"),
    )
    codes = _codes(out)
    evidence = _evidence_score(out)
    space = _space_score(out, direction)
    stage = _stage(engine_id, direction, codes, out)
    opportunity_types, next_event = _scope_opportunities(engine_id, out, direction)

    counter = out.get("counter_evidence")
    counter_count = len(counter) if isinstance(counter, (list, tuple, set)) else 0
    penalty = min(0.45, counter_count * 0.07)
    score = round(max(0.0, min(100.0, 100.0 * (0.70 * evidence + 0.30 * space - penalty))), 2)
    blocked = _hard_blocked(codes, out)

    # Opportunity and execution are deliberately separate concepts.
    opportunity_state = "NO_EDGE" if direction == "NEUTRAL" else "VISIBLE"
    if stage in {"INVALIDATED", "ECONOMICALLY_BLOCKED"} or blocked:
        opportunity_state = "VISIBLE_BUT_BLOCKED"
    elif stage in {"WAITING_CONFIRMATION", "AUCTION_PENDING", "VALIDATING", "REGIME_DEVELOPING"}:
        opportunity_state = "VISIBLE_PENDING_PROOF"

    out["opportunity"] = {
        "engine": engine_id,
        "scope": ENGINE_SCOPES.get(engine_id, engine_id),
        "direction": direction,
        "types": opportunity_types,
        "state": opportunity_state,
        "stage": stage,
        "score": score,
        "evidence_quality": round(evidence * 100.0, 2),
        "space_quality": round(space * 100.0, 2),
        "observed_evidence": codes,
        "counter_evidence": list(counter) if isinstance(counter, (list, tuple, set)) else [],
        "next_required_event": next_event,
        "invalidation": out.get("invalidation") or out.get("invalidations") or None,
        "trade_authorized": False if engine_id != "E9" else bool(out.get("gate_passed") and _text(out.get("decision")) in DIRECTIONS),
        "authority_boundary": f"{engine_id}_OWN_SCOPE_ONLY",
    }
    out["opportunity_score"] = score
    out["opportunity_direction"] = direction
    out["opportunity_stage"] = stage
    out["opportunity_state"] = opportunity_state
    out["opportunity_next_event"] = next_event
    out["opportunity_authority"] = engine_id
    out["opportunity_context"] = {k: _text(v) for k, v in ctx.items() if k in {"symbol", "timeframe"}}
    return out


def recover_e9(upstream: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if E9 raises: preserve upstream evidence and never invent a trade."""
    outputs = {k: dict(v.output or {}) for k, v in upstream.items()}
    directions = [
        _direction(outputs[k].get("direction"), outputs[k].get("finding"),
                   outputs[k].get("structure_direction"), outputs[k].get("pressure"))
        for k in outputs
    ]
    buy = directions.count("BUY")
    sell = directions.count("SELL")
    dominant = "BUY" if buy > sell else "SELL" if sell > buy else "CONFLICTED"
    reasons = ["E9_RECOVERY_MODE", "E9_MARKET_CONTROL_SYNTHESIS", "UPSTREAM_EVIDENCE_ONLY", "NO_INVENTED_TRADE"]
    if dominant == "CONFLICTED":
        reasons.append("DIRECTIONAL_CONTROL_CONFLICT")
    return {
        "decision": "NO_TRADE",
        "gate_passed": False,
        "decision_state": "WAIT_FOR_PROOF",
        "master_state": "WAIT_FOR_PROOF",
        "thesis_state": "UNRESOLVED",
        "setup_state": "BLOCKED",
        "confirmation_state": "PENDING",
        "risk_state": "BLOCKED",
        "execution_state": "BLOCKED",
        "primary_blocker": "E9_INTERNAL_ERROR",
        "secondary_blockers": reasons,
        "reason_codes": reasons + ["RISK_NOT_READY"],
        "market_control": {
            "dominant_side": dominant,
            "controlled_side": "UNKNOWN",
            "trapped_side": "UNKNOWN",
            "auction_state": "UNKNOWN",
            "repricing_direction": "UNKNOWN",
            "control_state": "UNRESOLVED",
            "authority": "E9",
            "authority_scope": "MARKET_CONTROL_SYNTHESIS_AND_FINAL_DECISION",
        },
        "trade_plan": {},
        "all_gates_pass": False,
        "authority": {"final_decision": "E9", "market_control": "E9"},
    }
