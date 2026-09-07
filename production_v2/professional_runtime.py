from __future__ import annotations

from functools import wraps
from typing import Any

from .professional_opportunity_controller import canonical_event_clock


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "TREND_UP"} or text.startswith("BUY "):
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "TREND_DOWN"} or text.startswith("SELL "):
        return "SELL"
    return "NEUTRAL"


def _event_direction(e4: dict[str, Any]) -> str:
    direct = _direction(e4.get("direction") or e4.get("directional_implication") or e4.get("response_direction"))
    if direct != "NEUTRAL":
        return direct
    event = _text(e4.get("event") or e4.get("finding"))
    if any(token in event for token in ("HIGH_SWEEP_REJECTION", "HIGH_REJECTION", "HIGH_FAILED_BREAK", "HIGH_LIQUIDITY_REJECTION")):
        return "SELL"
    if any(token in event for token in ("LOW_SWEEP_REJECTION", "LOW_REJECTION", "LOW_FAILED_BREAK", "LOW_LIQUIDITY_REJECTION")):
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return "NEUTRAL"


def _favorable_location(e5: dict[str, Any]) -> bool:
    finding = _text(e5.get("finding"))
    value = _text(e5.get("value_state") or e5.get("value_position"))
    location = _text(e5.get("structural_location") or e5.get("location_state"))
    return "FAVORABLE_LOCATION" in finding or value in {"DISCOUNT", "PREMIUM", "EQUILIBRIUM"} or location in {"AT_SUPPORT", "AT_RESISTANCE"}


def _space(e5: dict[str, Any], direction: str) -> float:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        return max(0.0, float(e5.get(key, 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _setup_family(e4: dict[str, Any]) -> str:
    event = _text(e4.get("event") or e4.get("finding"))
    if any(token in event for token in ("SWEEP", "REJECTION", "FAILED_BREAK", "RECLAIM")):
        return "LIQUIDITY_REVERSAL"
    if "ACCEPTANCE" in event:
        return "AUCTION_ACCEPTANCE_CONTINUATION"
    if "BREAK" in event:
        return "BREAKOUT"
    return "CAUSAL_AUCTION_RESPONSE"


def _promote_e6(result: Any, e4: dict[str, Any], e5: dict[str, Any], candle: Any) -> Any:
    output = dict(getattr(result, "output", {}) or {})
    if not output:
        return result
    event_direction = _event_direction(e4)
    current_direction = _direction(output.get("direction") or output.get("direction_thesis") or output.get("thesis_direction"))
    if event_direction not in {"BUY", "SELL"}:
        event_direction = current_direction
    if event_direction in {"BUY", "SELL"} and current_direction != event_direction:
        output["original_direction_before_event_reconciliation"] = current_direction
        output["direction"] = event_direction
        output["direction_thesis"] = event_direction
        output["thesis_direction"] = event_direction
        counter = list(output.get("counter_evidence") or [])
        if current_direction in {"BUY", "SELL"}:
            counter.append("E6_DIRECTION_OVERRIDDEN_BY_E4_CAUSAL_EVENT")
        output["counter_evidence"] = list(dict.fromkeys(counter))
        output["direction_authority"] = "E4_CAUSAL_EVENT"

    invalidated = bool(output.get("invalidated")) or _text(output.get("state")) == "INVALIDATED"
    event = _text(e4.get("event") or e4.get("finding"))
    has_event = bool(event and not any(token in event for token in ("NONE", "NO_LIQUIDITY", "NO_CONFIRMED")))
    direction = _direction(output.get("direction"))
    if not invalidated and direction in {"BUY", "SELL"} and has_event and _favorable_location(e5):
        # Promote an actionable causal hypothesis even when E6's legacy gate was
        # blocked by space or unresolved background trend context. Space is kept
        # as an economic constraint, never as evidence that the opportunity does not exist.
        setup = _setup_family(e4)
        space = _space(e5, direction)
        output.update({
            "state": "SETUP_THESIS",
            "setup_state": "SETUP_THESIS",
            "opportunity_stage": "SETUP_THESIS",
            "setup": setup,
            "setup_family": setup,
            "candidate_type": "SETUP_CANDIDATE",
            "direction": direction,
            "direction_thesis": direction,
            "thesis_direction": direction,
            "thesis_status": "FORMING",
            "setup_exists": True,
            "watch_only": False,
            "trade_ready": False,
            "trade_permission": False,
            "e6_causal_gate": "PASSED",
            "e6_thesis_proven": True,
            "available_space_atr": space,
            "tradeability": "CONSTRAINED" if space < 0.75 else "GOOD",
            "structural_space_is_economic_gate": True,
            "missing_proof": ["E7_SETUP_SPECIFIC_CONFIRMATION"],
            "next_required_event": "E7_SETUP_SPECIFIC_CONFIRMATION",
            "wait_for": "E7_SETUP_SPECIFIC_CONFIRMATION",
            "finding": f"{direction} causal setup thesis formed from E4 event + E5 location; E7 confirmation pending.",
            "lifecycle_state": "SETUP_THESIS",
            "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or output.get("event_id") or ""),
            "causal_event_clock": canonical_event_clock(e4, candle),
        })
        reasons = list(output.get("reason_codes") or [])
        reasons = [x for x in reasons if x != "STRUCTURAL_SPACE_INSUFFICIENT"]
        reasons.append("STRUCTURAL_SPACE_MOVED_TO_E8_ECONOMICS")
        output["reason_codes"] = list(dict.fromkeys(reasons))
    output["causal_event_clock"] = canonical_event_clock(e4, candle)
    output["causal_event_id"] = output["causal_event_clock"].get("event_id")
    return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)


def _pre_economics(e4: dict[str, Any], e5: dict[str, Any], e6: dict[str, Any], e7: dict[str, Any], e8: dict[str, Any]) -> dict[str, Any]:
    direction = _direction(e6.get("direction") or _event_direction(e4))
    space = _space(e5, direction)
    atr = 0.0
    try:
        atr = float(e8.get("atr", 0.0) or 0.0)
    except (TypeError, ValueError):
        atr = 0.0
    plan = e8.get("trade_plan") if isinstance(e8.get("trade_plan"), dict) else {}
    entry = plan.get("entry")
    stop = plan.get("stop_loss")
    try:
        risk_price = abs(float(entry) - float(stop)) if entry is not None and stop is not None else 0.0
    except (TypeError, ValueError):
        risk_price = 0.0
    risk_atr = risk_price / atr if atr > 0 else 0.0
    estimated_rr = space / risk_atr if risk_atr > 0 else 0.0
    confirmation = _text(e7.get("confirmation_state") or e7.get("confirmation"))
    tradeable = space >= 0.75 and (estimated_rr >= 1.2 or risk_atr == 0.0)
    blockers = []
    if space < 0.75:
        blockers.append("STRUCTURAL_SPACE_CONSTRAINED")
    if estimated_rr and estimated_rr < 1.2:
        blockers.append("PRE_RR_BELOW_TARGET")
    return {
        "schema": "E8_PRE_ECONOMICS_V1",
        "direction": direction,
        "space_atr": round(space, 4),
        "risk_atr": round(risk_atr, 4),
        "estimated_rr": round(estimated_rr, 4),
        "confirmation_state": confirmation or "PENDING",
        "tradeable": tradeable,
        "blockers": blockers,
        "execution_authorized": False,
        "stage": "PRE_CONFIRMATION",
        "closed_candle_only": True,
    }


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_PROFESSIONAL_RUNTIME_V1", False):
        return

    original_e4 = pipeline_module.analyze_e4
    original_e6 = pipeline_module.analyze_e6
    original_e7 = pipeline_module.analyze_e7
    original_e8 = pipeline_module.analyze_e8
    original_lifecycle = pipeline_module.advance_opportunity_directions

    @wraps(original_e4)
    def analyze_e4(*args: Any, **kwargs: Any):
        result = original_e4(*args, **kwargs)
        output = dict(getattr(result, "output", {}) or {})
        snapshot = args[0] if args and isinstance(args[0], dict) else {}
        candle = snapshot.get("candle_close_timestamp") or snapshot.get("candle")
        output["canonical_event_clock"] = canonical_event_clock(output, candle)
        return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)

    @wraps(original_e6)
    def analyze_e6(*args: Any, **kwargs: Any):
        result = original_e6(*args, **kwargs)
        snapshot = args[0] if args and isinstance(args[0], dict) else {}
        upstream = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        e4 = dict(getattr(upstream.get("E4"), "output", {}) or {})
        e5 = dict(getattr(upstream.get("E5"), "output", {}) or {})
        candle = snapshot.get("candle_close_timestamp") or snapshot.get("candle")
        return _promote_e6(result, e4, e5, candle)

    @wraps(original_e7)
    def analyze_e7(*args: Any, **kwargs: Any):
        result = original_e7(*args, **kwargs)
        snapshot = args[0] if args and isinstance(args[0], dict) else {}
        upstream = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        e4 = dict(getattr(upstream.get("E4"), "output", {}) or {})
        output = dict(getattr(result, "output", {}) or {})
        output["causal_event_clock"] = canonical_event_clock(e4, snapshot.get("candle_close_timestamp") or snapshot.get("candle"))
        return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)

    @wraps(original_e8)
    def analyze_e8(*args: Any, **kwargs: Any):
        result = original_e8(*args, **kwargs)
        snapshot = args[0] if args and isinstance(args[0], dict) else {}
        upstream = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        e4 = dict(getattr(upstream.get("E4"), "output", {}) or {})
        e5 = dict(getattr(upstream.get("E5"), "output", {}) or {})
        e6 = dict(getattr(upstream.get("E6"), "output", {}) or {})
        e7 = dict(getattr(upstream.get("E7"), "output", {}) or {})
        output = dict(getattr(result, "output", {}) or {})
        output["pre_economics"] = _pre_economics(e4, e5, e6, e7, output)
        output["causal_event_clock"] = canonical_event_clock(e4, snapshot.get("candle_close_timestamp") or snapshot.get("candle"))
        if _text(output.get("finding")) == "NOT_APPLICABLE" and e6.get("e6_thesis_proven"):
            output["finding"] = "PRE_ECONOMICS_READY"
            output["economic_state"] = "PRECHECK_PASS" if output["pre_economics"]["tradeable"] else "PRECHECK_CONSTRAINED"
            output["applicability"] = "PRE_ECONOMICS_APPLICABLE"
        return result.__class__(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)

    @wraps(original_lifecycle)
    def advance_opportunity_directions(previous: Any, current_by_direction: Any, **kwargs: Any):
        result = original_lifecycle(previous, current_by_direction, **kwargs)
        opportunities = result.get("opportunities") if isinstance(result, dict) else None
        if not isinstance(opportunities, dict):
            return result
        for item in opportunities.values():
            if not isinstance(item, dict):
                continue
            if _text(item.get("state")) == "WAITING" and bool(item.get("thesis_proven")):
                item["state"] = "ARMED"
                item["lifecycle_state"] = "ARMED"
                item["opportunity_phase"] = "ARMED"
                item["continuity"] = "THESIS_ARMED_WAITING_FOR_CONFIRMATION"
                item["trade_authorized"] = False
                item["wait_for"] = "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"
                item["execution_authority"] = "E9"
        leader = result.get("leader") if isinstance(result, dict) else None
        if leader in opportunities:
            leader_item = opportunities[leader]
            result["state"] = leader_item.get("state", result.get("state"))
            result["lifecycle_state"] = leader_item.get("lifecycle_state", result.get("lifecycle_state"))
            result["opportunity_phase"] = leader_item.get("opportunity_phase", result.get("opportunity_phase"))
            result["trade_authorized"] = False
            result["wait_for"] = leader_item.get("wait_for")
        result["professional_lifecycle_schema"] = "PROFESSIONAL_OPPORTUNITY_LIFECYCLE_V1"
        return result

    pipeline_module.analyze_e4 = analyze_e4
    pipeline_module.analyze_e6 = analyze_e6
    pipeline_module.analyze_e7 = analyze_e7
    pipeline_module.analyze_e8 = analyze_e8
    pipeline_module.advance_opportunity_directions = advance_opportunity_directions
    pipeline_module._PROFESSIONAL_RUNTIME_V1 = True
