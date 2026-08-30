from __future__ import annotations

"""Bounded opportunity intelligence shared by the nine brains.

This layer does not create entries or override an engine's thesis. It converts
an engine's own evidence into an opportunity map: what the engine sees, what
would strengthen it, what invalidates it, and what opportunity stage it is in.
E9 remains the only final-decision authority.
"""

from typing import Any

DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value or "").upper().strip()


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
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "conflicts", "invalidations"):
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


def _space_score(output: dict[str, Any]) -> float:
    vals = _numeric(output, "available_space_atr_long", "available_space_atr_short", "effective_space_atr", "space_atr")
    if not vals:
        return 0.5
    return max(0.0, min(1.0, min(vals) / 2.0))


def _stage(direction: str, codes: list[str], output: dict[str, Any]) -> str:
    text = " ".join(codes)
    state = _text(output.get("state") or output.get("finding") or output.get("lifecycle"))
    if any(x in text for x in ("INVALIDATED", "HARD_VETO", "RISK_BLOCKED")) or "INVALIDATED" in state:
        return "INVALIDATED"
    if any(x in text for x in ("CONFIRMED", "PROVEN", "TRADE_READY", "VALIDATED")):
        return "CONFIRMED"
    if direction in DIRECTIONS:
        return "DEVELOPING"
    return "OBSERVATION"


def enrich_opportunity(engine_id: str, output: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add bounded opportunity intelligence without changing engine authority."""
    out = dict(output or {})
    ctx = context or {}
    direction = _direction(
        out.get("direction"), out.get("structure_direction"), out.get("pressure"),
        out.get("market_direction"), out.get("finding"), out.get("market_state"),
    )
    codes = _codes(out)
    stage = _stage(direction, codes, out)
    space = _space_score(out)
    evidence_strength = out.get("confidence", out.get("evidence_strength", out.get("quality", 0.0)))
    try:
        evidence = max(0.0, min(1.0, float(evidence_strength)))
    except (TypeError, ValueError):
        evidence = 0.0

    if engine_id == "E1":
        opportunity_types = []
        state = _text(out.get("market_state") or out.get("state"))
        if direction in DIRECTIONS and state in {"TREND_UP", "TREND_DOWN", "EXPANSION"}:
            opportunity_types.append("CONTINUATION")
        if state in {"TRANSITION", "RANGE"}:
            opportunity_types.extend(["REVERSAL", "BREAKOUT_WATCH"])
        if state == "COMPRESSION":
            opportunity_types.append("EXPANSION_WATCH")
        next_event = "CLOSED_CANDLE_FOLLOW_THROUGH" if direction in DIRECTIONS else "DIRECTIONAL_REPRICING"
    elif engine_id == "E2":
        opportunity_types = list(out.get("opportunity_types") or out.get("candidate_setups") or [])
        if not opportunity_types:
            opportunity_types = ["CONDITIONAL_DIRECTIONAL_PLAY"] if direction in DIRECTIONS else ["NO_DIRECTIONAL_EDGE"]
        next_event = "REGIME_ACCEPTANCE_AND_FOLLOW_THROUGH"
    elif engine_id == "E3":
        opportunity_types = ["STRUCTURAL_CONTINUATION" if direction in DIRECTIONS else "STRUCTURAL_REVERSAL_WATCH"]
        next_event = "BOS_OR_PROTECTED_LEVEL_REACTION"
    elif engine_id == "E4":
        event = _text(out.get("event") or out.get("auction_event") or out.get("liquidity_event"))
        opportunity_types = ["LIQUIDITY_REVERSAL"] if "SWEEP" in event or "FAILED_BREAK" in event else ["LIQUIDITY_INTERACTION_WATCH"]
        next_event = "RECLAIM_OR_ACCEPTANCE"
    elif engine_id == "E5":
        opportunity_types = ["LOCATION_CONTINUATION" if direction in DIRECTIONS else "LOCATION_REVERSAL_WATCH"]
        next_event = "PRICE_RESPONSE_AT_VALUE_OR_STRUCTURE"
    elif engine_id == "E6":
        opportunity_types = [_text(out.get("setup") or out.get("setup_family") or out.get("finding")) or "SETUP_CANDIDATE"]
        next_event = "SETUP_SPECIFIC_CONFIRMATION"
    elif engine_id == "E7":
        opportunity_types = ["ENTRY_CONFIRMATION" if direction in DIRECTIONS else "CONFIRMATION_WATCH"]
        next_event = "FOLLOW_THROUGH" if _text(out.get("confirmation_state")) in {"PROVEN", "CONFIRMED"} else "VALID_CLOSED_CANDLE_TRIGGER"
    elif engine_id == "E8":
        opportunity_types = ["ECONOMICALLY_ATTRACTIVE" if not any("BLOCK" in c or "INVALID" in c for c in codes) else "ECONOMICALLY_CONSTRAINED"]
        next_event = "SURVIVABLE_GEOMETRY_AND_TARGET"
    else:
        opportunity_types = ["MASTER_MARKET_CONTROL"]
        next_event = "NONE"

    # A bounded score: evidence + room, penalized by explicit counter evidence.
    counter = len(out.get("counter_evidence") or []) if isinstance(out.get("counter_evidence"), (list, tuple)) else 0
    counter_penalty = min(0.35, counter * 0.07)
    opportunity_score = round(max(0.0, min(100.0, 100.0 * (0.65 * evidence + 0.35 * space - counter_penalty))), 2)

    out["opportunity"] = {
        "engine": engine_id,
        "direction": direction,
        "types": opportunity_types,
        "stage": stage,
        "score": opportunity_score,
        "evidence_quality": round(evidence * 100.0, 2),
        "space_quality": round(space * 100.0, 2),
        "observed_evidence": codes,
        "counter_evidence": list(out.get("counter_evidence") or []) if isinstance(out.get("counter_evidence"), (list, tuple)) else [],
        "next_required_event": next_event,
        "invalidation": out.get("invalidation") or out.get("invalidations") or None,
        "authority_boundary": f"{engine_id}_OWN_SCOPE_ONLY",
    }
    out["opportunity_score"] = opportunity_score
    out["opportunity_direction"] = direction
    out["opportunity_stage"] = stage
    out["opportunity_next_event"] = next_event
    out["opportunity_authority"] = engine_id
    out["opportunity_context"] = {k: _text(v) for k, v in ctx.items() if k in {"symbol", "timeframe"}}
    return out


def recover_e9(upstream: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed E9 recovery used only when the legacy E9 raises unexpectedly."""
    outputs = {k: dict(v.output or {}) for k, v in upstream.items()}
    directions = [_direction(outputs[k].get("direction"), outputs[k].get("finding"), outputs[k].get("structure_direction"), outputs[k].get("pressure")) for k in outputs]
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
