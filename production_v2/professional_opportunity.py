from __future__ import annotations

"""Cross-engine professional opportunity radar.

This module describes opportunity quality separately from execution. It may
rank and preserve conditional opportunities, but E9 remains the only trade
authority.
"""

from typing import Any

DIRECTIONS = {"BUY", "SELL"}
ENGINES = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
ENGINE_SCOPES = {
    "E1": "MARKET_STATE", "E2": "OPPORTUNITY_REGIME", "E3": "MARKET_STRUCTURE",
    "E4": "LIQUIDITY_AUCTION", "E5": "LOCATION_VALUE", "E6": "SETUP_FORMATION",
    "E7": "CONFIRMATION", "E8": "TRADE_ECONOMICS", "E9": "MARKET_CONTROL",
}
NEXT_EVENT = {
    "E1": "NEXT_CLOSED_CANDLE_REGIME_UPDATE", "E2": "AUCTION_ACCEPTANCE_OR_FOLLOW_THROUGH",
    "E3": "BOS_CHOCH_OR_PROTECTED_LEVEL_REACTION", "E4": "AUCTION_FOLLOW_THROUGH_OR_REJECTION",
    "E5": "PRICE_RESPONSE_AT_VALUE_OR_TARGET_SPACE_OPENING", "E6": "SETUP_SPECIFIC_CONFIRMATION",
    "E7": "VALID_CLOSED_CANDLE_TRIGGER_OR_INVALIDATION", "E8": "SURVIVABLE_GEOMETRY_AND_REALISTIC_TARGET",
    "E9": "ALL_CONTROL_GATES_PASS",
}


def _text(value: Any) -> str:
    if isinstance(value, dict): return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)): return " ".join(_text(v) for v in value)
    return str(value if value is not None else "").upper().strip()


def _direction(output: dict[str, Any]) -> str:
    book = output.get("opportunity_book")
    if isinstance(book, dict):
        leader = _text(book.get("leader") or output.get("opportunity_leader"))
        if leader in DIRECTIONS: return leader
    values = (
        output.get("direction"), output.get("opportunity_direction"), output.get("structure_direction"),
        output.get("market_direction"), output.get("pressure"), output.get("bos_direction"),
        output.get("finding"), output.get("market_state"),
        output.get("decision") if _text(output.get("decision")) in DIRECTIONS else None,
    )
    for value in values:
        x = _text(value)
        if x in DIRECTIONS or x.startswith(("BUY ", "BUY_", "BUY:")) or x in {"UP", "BULLISH", "TREND_UP"}: return "BUY"
        if x.startswith(("SELL ", "SELL_", "SELL:")) or x in {"DOWN", "BEARISH", "TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _codes(output: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "conflicts", "invalidations", "vetoes", "hard_veto", "secondary_blockers"):
        value = output.get(key)
        if isinstance(value, str): values.append(_text(value))
        elif isinstance(value, dict):
            for k, v in value.items():
                if v is True: values.append(_text(k))
                elif v not in (None, False, ""): values.append(_text(v))
        elif isinstance(value, (list, tuple, set)): values.extend(_text(v) for v in value if v is not None)
    return list(dict.fromkeys(v for v in values if v))


def _num(output: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try: x = float(output.get(key))
        except (TypeError, ValueError): continue
        if x == x and abs(x) != float("inf"): return x
    return None


def _confidence(output: dict[str, Any]) -> float:
    x = _num(output, "confidence", "evidence_strength", "quality", "opportunity_score")
    if x is None: return 0.0
    if x > 1.0: x /= 100.0
    return max(0.0, min(1.0, x))


def _space(output: dict[str, Any], direction: str) -> float | None:
    keys = (("available_space_atr_long", "long_space_atr", "effective_space_atr", "space_atr") if direction == "BUY" else ("available_space_atr_short", "short_space_atr", "effective_space_atr", "space_atr") if direction == "SELL" else ("effective_space_atr", "space_atr"))
    return _num(output, *keys)


def _space_quality(space: float | None) -> float | None:
    return None if space is None else max(0.0, min(100.0, space / 2.0 * 100.0))


def _hard_blocked(codes: list[str], output: dict[str, Any]) -> bool:
    text = " ".join(codes); state = _text(output.get("state") or output.get("decision_state") or output.get("execution_state"))
    return any(x in text for x in ("INVALIDATED", "HARD_VETO", "RISK_BLOCKED", "INVALID_TRADE_GEOMETRY", "NO_USABLE_STRUCTURAL_TARGET", "ENTRY_CONFIRMATION", "STOP_TOO_WIDE")) or any(x in state for x in ("INVALIDATED", "BLOCKED"))


def _stage(engine: str, direction: str, output: dict[str, Any], codes: list[str]) -> str:
    text = " ".join(codes); state = _text(output.get("state") or output.get("finding") or output.get("lifecycle"))
    if "INVALIDATED" in state or any(x in text for x in ("INVALIDATED", "HARD_VETO")): return "INVALIDATED"
    if engine == "E1":
        market_state = _text(output.get("market_state") or output.get("state")); return "STATE_ESTABLISHED" if market_state in {"TREND_UP", "TREND_DOWN", "EXPANSION", "RANGE", "COMPRESSION", "TRANSITION"} else "STATE_WATCH"
    if engine == "E2":
        maturity = _text(output.get("opportunity_maturity")); return "REGIME_CONFIRMED" if maturity in {"ACTIONABLE", "CONFIRMED"} else "REGIME_DEVELOPING" if direction in DIRECTIONS else "REGIME_UNRESOLVED"
    if engine == "E3":
        lifecycle = _text(output.get("lifecycle") or output.get("structure_lifecycle")); return "STRUCTURE_ESTABLISHED" if lifecycle in {"ESTABLISHED", "CONFIRMED", "BOS_UP", "BOS_DOWN", "CHOCH"} else "STRUCTURE_FORMING" if direction in DIRECTIONS else "STRUCTURE_WATCH"
    if engine == "E4":
        auction = _text(output.get("auction_state") or output.get("auction_phase")); return "AUCTION_CONFIRMED" if auction in {"CONFIRMED", "ACCEPTED", "REJECTED", "RECLAIMED", "TERMINALLY_CONFIRMED"} else "AUCTION_PENDING" if direction in DIRECTIONS else "AUCTION_WATCH"
    if engine == "E5": return "LOCATION_ACTIONABLE" if direction in DIRECTIONS and not any(x in text for x in ("SPACE_CONSTRAINED", "NO_REVERSAL_EDGE")) else "LOCATION_ASSESSED"
    if engine == "E6": return "SETUP_MATURE" if any(x in text for x in ("SETUP_CONFIRMED", "TRADE_READY")) else "SETUP_VALIDATING" if direction in DIRECTIONS else "SETUP_WATCH"
    if engine == "E7":
        confirmation = _text(output.get("confirmation_state")); return "CONFIRMED" if confirmation in {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"} else "WAITING_CONFIRMATION" if direction in DIRECTIONS else "CONFIRMATION_WATCH"
    if engine == "E8": return "ECONOMICALLY_BLOCKED" if _hard_blocked(codes, output) or any(x in text for x in ("REAL_RR_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY")) else "ECONOMICALLY_VALIDATED" if direction in DIRECTIONS else "ECONOMIC_WATCH"
    return "EXECUTABLE" if _text(output.get("decision")) in DIRECTIONS and bool(output.get("gate_passed")) else "CONTROLLED_WAIT"


def _conditional_paths(engine: str, direction: str, output: dict[str, Any], stage: str) -> list[str]:
    state = _text(output.get("market_state") or output.get("state") or output.get("regime")); event = _text(output.get("event") or output.get("auction_event") or output.get("liquidity_event")); location = _text(output.get("structural_location") or output.get("value_state") or output.get("location")); setup = _text(output.get("setup") or output.get("setup_family") or output.get("setup_type"))
    if engine == "E1":
        if state == "TREND_UP": return ["BUY_CONTINUATION_IF_PULLBACK_HOLDS_AND_PRESSURE_REMAINS_UP"]
        if state == "TREND_DOWN": return ["SELL_CONTINUATION_IF_PULLBACK_HOLDS_AND_PRESSURE_REMAINS_DOWN"]
        if state == "RANGE": return ["RANGE_ROTATION_IF_BOUNDARY_REJECTION_IS_CONFIRMED"]
        if state in {"COMPRESSION", "EXPANSION"}: return ["DIRECTIONAL_BREAKOUT_IF_CLOSED_CANDLE_ACCEPTANCE_CONFIRMS"]
        return ["REGIME_RESOLUTION_IF_STRUCTURE_AND_PRESSURE_ALIGN"]
    if engine == "E2": return ["BUY_CONTINUATION_IF_AUCTION_ACCEPTANCE_AND_FOLLOW_THROUGH_PROVE"] if direction == "BUY" else ["SELL_REVERSAL_OR_CONTINUATION_IF_REJECTION_AND_FOLLOW_THROUGH_PROVE"] if direction == "SELL" else ["WAIT_FOR_DIRECTIONAL_AUCTION_INTENT"]
    if engine == "E3": return ["BUY_STRUCTURE_IF_PROTECTED_LOW_HOLDS_AND_BOS_OR_HL_SEQUENCE_CONFIRMS"] if direction == "BUY" else ["SELL_STRUCTURE_IF_PROTECTED_HIGH_HOLDS_AND_BOS_OR_LH_SEQUENCE_CONFIRMS"] if direction == "SELL" else ["STRUCTURE_RESOLUTION_IF_PROTECTED_LEVEL_REACTS"]
    if engine == "E4":
        if any(x in event for x in ("SWEEP", "REJECTION", "FAILED_BREAK")): return ["LIQUIDITY_REVERSAL_IF_RECLAIM_HOLDS_AND_FOLLOW_THROUGH_CONFIRMS"]
        if any(x in event for x in ("ACCEPT", "INITIATIVE")): return ["LIQUIDITY_CONTINUATION_IF_ACCEPTANCE_PERSISTS"]
        return ["LIQUIDITY_OPPORTUNITY_IF_SWEEP_RECLAIM_OR_ACCEPTANCE_OCCURS"]
    if engine == "E5":
        if direction == "BUY" and "SUPPORT" in location: return ["BUY_FROM_SUPPORT_IF_REJECTION_OR_ACCEPTANCE_CREATES_SPACE"]
        if direction == "SELL" and "RESISTANCE" in location: return ["SELL_FROM_RESISTANCE_IF_REJECTION_OR_ACCEPTANCE_CREATES_SPACE"]
        return ["DIRECTIONAL_VALUE_OPPORTUNITY_IF_SPACE_OPENS"]
    if engine == "E6": return [f"{direction}_{setup or 'SETUP'}_IF_SETUP_SPECIFIC_PROOF_GATES_COMPLETE" if direction in DIRECTIONS else "SETUP_CANDIDATE_IF_CAUSAL_EVIDENCE_CONVERGES"]
    if engine == "E7": return [f"{direction}_CONFIRMATION_IF_CLOSED_CANDLE_TRIGGER_AND_FOLLOW_THROUGH_PROVE" if direction in DIRECTIONS else "CONFIRMATION_IF_SETUP_SPECIFIC_TRIGGER_APPEARS"]
    if engine == "E8": return [f"{direction}_ECONOMICS_IF_STRUCTURAL_TARGET_STOP_QUALITY_AND_REAL_RR_PASS" if direction in DIRECTIONS else "ECONOMICS_IF_TRADE_GEOMETRY_BECOMES_SURVIVABLE"]
    return [f"{direction}_EXECUTABLE_ONLY_WHEN_ALL_E9_CONTROL_GATES_REMAIN_TRUE" if stage == "EXECUTABLE" else "MASTER_CONTROL_IF_ALL_UPSTREAM_EVIDENCE_CONVERGES_AND_NO_VETO_REMAINS"]


def _failure_conditions(engine: str, direction: str, output: dict[str, Any], codes: list[str]) -> list[str]:
    conditions: list[str] = []
    if "INVALIDATED" in " ".join(codes) or "INVALIDATED" in _text(output.get("invalidation")): conditions.append("CURRENT_THESIS_INVALIDATED")
    if direction == "BUY": conditions.append("BUY_THESIS_FAILS_IF_PROTECTED_LOW_OR_REQUIRED_RECLAIM_LEVEL_BREAKS")
    if direction == "SELL": conditions.append("SELL_THESIS_FAILS_IF_PROTECTED_HIGH_OR_REQUIRED_RECLAIM_LEVEL_BREAKS")
    if engine == "E4": conditions.append("AUCTION_THESIS_FAILS_IF_NO_FOLLOW_THROUGH_AFTER_EVENT")
    if engine == "E8": conditions.append("ECONOMIC_THESIS_FAILS_IF_TARGET_SPACE_OR_STOP_SURVIVABILITY_DETERIORATES")
    if engine == "E9": conditions.append("MASTER_THESIS_FAILS_IF_ANY_HARD_CONTROL_GATE_FAILS")
    return list(dict.fromkeys(conditions))


def _price_geometry(output: dict[str, Any]) -> dict[str, Any]:
    price = _num(output, "price", "current_price", "last_price")
    support = _num(output, "next_support", "support", "protected_low")
    resistance = _num(output, "next_resistance", "resistance", "protected_high")
    long_space = _num(output, "available_space_atr_long", "long_space_atr")
    short_space = _num(output, "available_space_atr_short", "short_space_atr")
    return {
        "price": price,
        "BUY": {"entry_reference": price, "invalidation_reference": support, "target_reference": resistance, "available_space_atr": long_space},
        "SELL": {"entry_reference": price, "invalidation_reference": resistance, "target_reference": support, "available_space_atr": short_space},
        "source": "E5_EXPLICIT_GEOMETRY" if any(x is not None for x in (support, resistance, long_space, short_space)) else "NOT_EXPLICITLY_AVAILABLE",
    }


def _directional_radar(output: dict[str, Any]) -> dict[str, Any]:
    book = output.get("opportunity_book")
    if not isinstance(book, dict): return {}
    radar = {}
    for candidate in book.get("candidates", []):
        if not isinstance(candidate, dict): continue
        direction = _text(candidate.get("direction"))
        if direction not in DIRECTIONS: continue
        quality = candidate.get("quality", candidate.get("score", 0.0))
        try: quality = float(quality); quality = quality * 100.0 if quality <= 1.0 else quality
        except (TypeError, ValueError): quality = 0.0
        radar[direction] = {
            "state": candidate.get("state", "DEVELOPING"),
            "quality": round(max(0.0, min(100.0, quality)), 2),
            "wait_for": candidate.get("wait_for") or ["NEXT_CLOSED_M5_CANDLE"],
            "conditional": True,
        }
    return radar


def _conditional_thesis(engine: str, direction: str, output: dict[str, Any], stage: str) -> dict[str, Any]:
    paths = _conditional_paths(engine, direction, output, stage)
    invalidators = _failure_conditions(engine, direction, output, _codes(output))
    return {
        "direction": direction,
        "status": "UNPROVEN" if stage not in {"MATURE", "CONFIRMED", "EXECUTABLE"} else "PROVEN",
        "why_this_can_work": paths[0] if paths else "NO_CONDITIONAL_PATH",
        "proof_required": [NEXT_EVENT.get(engine, "NEXT_CLOSED_CANDLE_UPDATE")],
        "invalidators": invalidators,
    }


def _strength(engine: str, direction: str, confidence: float, space_quality: float | None, counter: list[str], stage: str, output: dict[str, Any]) -> float:
    evidence = confidence * 100.0
    space = 50.0 if space_quality is None else space_quality
    maturity_bonus = {"REGIME_CONFIRMED": 8.0, "STRUCTURE_ESTABLISHED": 8.0, "AUCTION_CONFIRMED": 10.0, "LOCATION_ACTIONABLE": 8.0, "SETUP_MATURE": 12.0, "CONFIRMED": 12.0, "ECONOMICALLY_VALIDATED": 8.0, "EXECUTABLE": 15.0}.get(stage, 0.0)
    penalty = min(35.0, len(counter) * 6.0)
    if direction == "NEUTRAL": return round(max(0.0, min(100.0, evidence * 0.55 + space * 0.15 - penalty)), 2)
    return round(max(0.0, min(100.0, evidence * 0.55 + space * 0.20 + maturity_bonus - penalty)), 2)


def _execution_quality(engine: str, stage: str, hard_block: bool, output: dict[str, Any]) -> str:
    if engine != "E9": return "NOT_READY"
    if hard_block: return "BLOCKED"
    if stage == "EXECUTABLE" and _text(output.get("decision")) in DIRECTIONS and bool(output.get("gate_passed")): return "READY"
    return "NOT_READY"


def _strength_trend(previous: dict[str, Any] | None, current: float) -> str:
    if not isinstance(previous, dict): return "UNAVAILABLE"
    old = previous.get("opportunity_strength")
    try: old = float(old)
    except (TypeError, ValueError): return "UNAVAILABLE"
    if current > old + 3.0: return "STRENGTHENING"
    if current < old - 3.0: return "DECAYING"
    return "STABLE"


def enrich_engine(engine: str, output: dict[str, Any], upstream: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    out = dict(output or {}); direction = _direction(out); codes = _codes(out); stage = _stage(engine, direction, out, codes); confidence = _confidence(out); space = _space(out, direction); space_quality = _space_quality(space); hard_block = _hard_blocked(codes, out)
    counter = [c for c in codes if any(x in c for x in ("CONFLICT", "MISSING", "PENDING", "BLOCK", "RISK", "CONSTRAINED", "UNRESOLVED"))]
    state = "NO_OPPORTUNITY" if direction == "NEUTRAL" and not _directional_radar(out) else "OPPORTUNITY_INVALIDATED" if stage == "INVALIDATED" else "OPPORTUNITY_EXECUTABLE" if stage == "EXECUTABLE" else "OPPORTUNITY_WAITING"
    score = confidence * 100.0
    if space_quality is not None: score = 0.65 * score + 0.35 * space_quality
    score = round(max(0.0, min(100.0, score - min(30.0, len(counter) * 5.0))), 2)
    authorized = engine == "E9" and stage == "EXECUTABLE" and _text(out.get("decision")) in DIRECTIONS and bool(out.get("gate_passed"))
    strength = _strength(engine, direction, confidence, space_quality, counter, stage, out)
    previous = (upstream or {}).get("previous_opportunity") if isinstance(upstream, dict) else None
    thesis = _conditional_thesis(engine, direction, out, stage)
    execution_quality = _execution_quality(engine, stage, hard_block, out)
    radar = _directional_radar(out)
    if radar:
        strongest = max(radar.values(), key=lambda x: x.get("quality", 0.0))
        strength = max(strength, float(strongest.get("quality", 0.0)))
    op = {
        "engine": engine, "scope": ENGINE_SCOPES.get(engine, engine), "authority": engine,
        "direction": direction, "state": state, "stage": stage, "score": score,
        "opportunity_strength": round(strength, 2), "strength_trend": _strength_trend(previous, strength),
        "evidence_quality": round(confidence * 100.0, 2), "space_atr": space, "space_quality": space_quality,
        "observed_evidence": codes, "counter_evidence": counter,
        "conditional_paths": _conditional_paths(engine, direction, out, stage),
        "conditional_thesis": thesis,
        "next_required_event": NEXT_EVENT.get(engine, "NEXT_CLOSED_CANDLE_UPDATE"),
        "wait_for": [NEXT_EVENT.get(engine, "NEXT_CLOSED_CANDLE_UPDATE")],
        "failure_conditions": _failure_conditions(engine, direction, out, codes),
        "price_geometry": _price_geometry(out) if engine == "E5" else None,
        "directional_opportunities": radar,
        "competition": out.get("opportunity_competition") or (out.get("opportunity_book") or {}).get("competition") if isinstance(out.get("opportunity_book"), dict) else None,
        "trade_authorized": authorized, "execution_authority": "E9_ONLY",
        "execution_quality": execution_quality,
        "authority_boundary": f"{engine}_OWN_SCOPE_ONLY", "execution_separation": True,
        "state_preservation": "OPPORTUNITY_ALIVE_UNLESS_EXPLICITLY_INVALIDATED",
        "hard_blocked": hard_block,
    }
    out["professional_opportunity"] = op
    out["opportunity_state"] = state; out["opportunity_stage"] = stage; out["opportunity_direction"] = direction; out["opportunity_next_event"] = NEXT_EVENT.get(engine, "NEXT_CLOSED_CANDLE_UPDATE"); out["opportunity_score"] = score; out["opportunity_authority"] = engine
    out["opportunity_strength"] = round(strength, 2)
    out["opportunity_execution_quality"] = execution_quality
    return out


def consolidate(results: dict[str, Any]) -> dict[str, Any]:
    radar: list[dict[str, Any]] = []
    for engine in ENGINES[:-1]:
        result = results.get(engine)
        if not result: continue
        output = result.output if hasattr(result, "output") else result
        op = output.get("professional_opportunity") or {}
        if op.get("state") in {"OPPORTUNITY_WAITING", "OPPORTUNITY_EXECUTABLE"}: radar.append(op)
    radar.sort(key=lambda x: float(x.get("opportunity_strength", x.get("score", 0.0))), reverse=True)
    return {"count": len(radar), "best": radar[0] if radar else None, "radar": radar}
