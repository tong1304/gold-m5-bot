from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Who controls the auction, where is liquidity, and should this trade be taken after reconciling all evidence?"
ARCHITECTURE = "E9_MASTER_DECISION_MARKET_CONTROL_V58"
VERSION = "58.0"
DIRECTIONS = {"BUY", "SELL"}
CONFIRMATION_PROVEN = {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"}
MATURITY_READY = {"MATURE", "TRADE_READY", "VALIDATED", "CONFIRMED"}
RISK_READY_STATES = {"READY", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY", "VALIDATED", "PASS", "PASSED", "COMPLETE"}
TERMINAL_AUCTION = {"CONFIRMED", "TERMINALLY_CONFIRMED", "RECLAIMED"}
ECONOMIC_BLOCKERS = {"INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID", "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET", "RISK_QUALITY_BELOW_DECISION_THRESHOLD"}
HARD_CONFLICT_CODES = {"THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT", "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED", "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED", "E3_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED"}
BLOCKER_PRIORITY = ("THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED", "E3_STRUCTURE_INVALIDATED", "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT", "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT", "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID", "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET", "ENTRY_CONFIRMATION_NOT_PROVEN", "SETUP_NOT_MATURE", "RISK_NOT_READY", "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "DIRECTION_UNRESOLVED")


def _out(engine: EngineResult | None) -> dict[str, Any]:
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _text(value)
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _codes(output: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("reason_codes", "reasons", "counter_evidence", "blockers", "risk_blockers", "economic_blockers", "conflicts", "invalidations"):
        value = output.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif isinstance(value, dict):
            for name, flag in value.items():
                if flag is True:
                    values.append(name)
                elif flag not in (None, "", False):
                    values.append(name if isinstance(flag, bool) else flag)
    return _dedupe(values)


def _engine_codes(engine: EngineResult | None) -> list[str]:
    return _dedupe(_codes(_out(engine)) + list(engine.reason_codes or ()) if engine else [])


def _direction(*values: Any) -> str:
    for value in values:
        x = _text(value)
        if x in DIRECTIONS:
            return x
        if x.startswith(("BUY ", "BUY_", "BUY:")):
            return "BUY"
        if x.startswith(("SELL ", "SELL_", "SELL:")):
            return "SELL"
        if x in {"UP", "BULLISH"} or any(k in x for k in ("LONG", "BUYERS", "TREND_UP")):
            return "BUY"
        if x in {"DOWN", "BEARISH"} or any(k in x for k in ("SHORT", "SELLERS", "TREND_DOWN")):
            return "SELL"
    return "NEUTRAL"


def _clean_setup(value: Any) -> str:
    text = _text(value)
    return "" if text in {"", "UNKNOWN", "NONE", "NO_SETUP", "NO SETUP", "UNRESOLVED"} else text


def _e6_has_surviving_setup(e6: dict[str, Any]) -> bool:
    finding = _text(e6.get("finding"))
    codes = set(_codes(e6))
    if "NO PLAUSIBLE SETUP SURVIVES" in finding or "NO SURVIVING SETUP" in finding:
        return False
    if {"DIRECTIONAL_EVIDENCE_CONFLICT", "SPACE_CONFLICT"}.issubset(codes):
        return False
    if any(code in codes for code in ("NO_SURVIVING_SETUP", "NO_ELIGIBLE_SETUP", "SETUP_REJECTED", "SETUP_INVALIDATED")):
        return False
    explicit = e6.get("setup") or e6.get("setup_family") or e6.get("candidate_setup") or e6.get("candidate_setup_thesis") or e6.get("setup_type") or e6.get("thesis_setup") or e6.get("selected_hypothesis")
    return bool(_clean_setup(explicit))


def _e6_identity(e6: dict[str, Any]) -> tuple[str, str, str]:
    # E6 is the sole authority for trade-thesis identity. A market bias is not a setup.
    if not _e6_has_surviving_setup(e6):
        return "NEUTRAL", "UNKNOWN", "UNRESOLVED"
    finding = str(e6.get("finding") or "").strip()
    direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("thesis_direction"), e6.get("selected_direction"), finding)
    setup = ""
    for key in ("setup", "setup_family", "candidate_setup", "candidate_setup_thesis", "setup_type", "thesis_setup", "selected_hypothesis"):
        setup = _clean_setup(e6.get(key))
        if setup:
            break
    if not setup and finding:
        head = finding.split(" is validating", 1)[0].strip()
        if direction in DIRECTIONS and _text(head).startswith(direction + " "):
            head = head[len(direction):].strip()
        setup = _clean_setup(head)
    thesis = str(e6.get("thesis") or e6.get("candidate_setup_thesis") or e6.get("selected_hypothesis") or finding or "UNRESOLVED").strip()
    return direction, setup or "UNKNOWN", thesis or "UNRESOLVED"


def _state(output: dict[str, Any], keys: tuple[str, ...], default: str = "UNRESOLVED") -> str:
    for key in keys:
        if output.get(key) not in (None, ""):
            return _text(output[key])
    return default


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _walk(child)


def _e8_boundary(e8: EngineResult | None) -> tuple[dict[str, Any], dict[str, Any]]:
    merged: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    for candidate in _walk(_out(e8)):
        nested = candidate.get("trade_plan")
        if isinstance(nested, dict):
            plan.update(nested)
        for key in ("risk_gate", "risk_state", "economic_state", "decision_state", "plan_status", "direction", "risk_quality", "verified", "trade_plan_verified"):
            if key in candidate:
                merged[key] = candidate[key]
    return merged, plan


def _confirmation_state(e7: dict[str, Any]) -> str:
    codes = set(_codes(e7))
    if codes & {"E7_CONFIRMATION_INVALIDATED", "CONFIRMATION_INVALIDATED"}:
        return "INVALIDATED"
    if codes & {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"}:
        return "PROVEN"
    if codes & {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"}:
        return "PENDING"
    return _state(e7, ("confirmation_state", "confirmation", "proof_state", "trigger_state"))


def _trigger_observed(e7: dict[str, Any]) -> bool:
    if any(e7.get(k) is True for k in ("trigger_observed", "valid_trigger", "closed_candle_trigger")):
        return True
    return _state(e7, ("trigger_state", "trigger", "entry_trigger")) in CONFIRMATION_PROVEN or bool(set(_codes(e7)) & {"VALID_CLOSED_CANDLE_TRIGGER", "TRIGGER_CONFIRMED", "CONFIRMATION_PROVEN"})


def _plan_valid(plan: dict[str, Any], direction: str) -> bool:
    if direction not in DIRECTIONS:
        return False
    try:
        entry = float(plan["entry"]); stop = float(plan["stop_loss"]); target = float(plan.get("take_profit_2", plan.get("take_profit", plan.get("tp2"))))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(v == v for v in (entry, stop, target)):
        return False
    if direction == "BUY" and not stop < entry < target:
        return False
    if direction == "SELL" and not target < entry < stop:
        return False
    rr = plan.get("rr_tp2", plan.get("rr"))
    if rr not in (None, ""):
        try:
            if float(rr) < 1.50:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _hard_conflicts(upstream: dict[str, EngineResult]) -> list[str]:
    found: list[str] = []
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id)
        for code in _engine_codes(engine):
            if code in HARD_CONFLICT_CODES:
                found.append(code)
        output = _out(engine)
        for key in ("state", "finding", "lifecycle", "invalidation", "structure_state", "thesis_state"):
            value = _text(output.get(key))
            if value in HARD_CONFLICT_CODES or value.endswith("_INVALIDATED") or "THESIS_INVALIDATED" in value:
                found.append(value)
    return _dedupe(found)


def _economic_blockers(e8: EngineResult | None) -> list[str]:
    found: list[str] = []
    for candidate in _walk(_out(e8)):
        found.extend(code for code in _codes(candidate) if code in ECONOMIC_BLOCKERS)
    return _dedupe(found)


def _resolve(direction: str, setup: str, thesis: str, e6: dict[str, Any], e7: dict[str, Any], e8: EngineResult | None, upstream: dict[str, EngineResult]) -> dict[str, Any]:
    maturity = _state(e6, ("maturity", "setup_maturity", "setup_stage", "stage", "formation_stage", "lifecycle"))
    confirmation = _confirmation_state(e7)
    trigger = _trigger_observed(e7)
    boundary, plan = _e8_boundary(e8)
    economic = _economic_blockers(e8)
    conflicts = _hard_conflicts(upstream)
    direction_ready = direction in DIRECTIONS
    setup_known = bool(_clean_setup(setup))
    setup_ready = direction_ready and setup_known and maturity in MATURITY_READY
    confirmation_ready = confirmation in CONFIRMATION_PROVEN and trigger
    risk_state = _text(boundary.get("risk_gate") or boundary.get("risk_state") or boundary.get("economic_state") or boundary.get("plan_status") or "")
    risk_ready = not economic and risk_state in RISK_READY_STATES and _plan_valid(plan, direction)
    blockers = _dedupe(conflicts + economic)
    if not direction_ready: blockers.append("DIRECTION_UNRESOLVED")
    if not setup_ready: blockers.append("SETUP_NOT_MATURE")
    if not confirmation_ready: blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not risk_ready: blockers.append("RISK_NOT_READY")
    blockers = _dedupe(blockers)
    primary = next((c for c in BLOCKER_PRIORITY if c in blockers), "NONE")
    all_pass = direction_ready and setup_ready and confirmation_ready and risk_ready and not conflicts and not economic
    if all_pass:
        decision, decision_state, master_state = direction, "EXECUTE", "EXECUTE"
        thesis_state, setup_state = "ESTABLISHED", "TRADE_READY"
        confirmation_final, risk_final, execution_state = "PROVEN", "READY", "READY"
    elif conflicts:
        decision, decision_state, master_state = "NO_TRADE", "REJECT", "REJECTED_HARD_CONFLICT"
        thesis_state = "INVALIDATED" if any("INVALIDAT" in c for c in conflicts) else "CONFLICTED"
        setup_state = confirmation_final = risk_final = execution_state = "BLOCKED"
    else:
        decision, decision_state, master_state = "NO_TRADE", "WAIT_FOR_PROOF", "WAIT_FOR_PROOF"
        # Critical invariant: without a surviving E6 setup, E9 never promotes a directional market bias to a thesis.
        thesis_state = "ESTABLISHED" if direction_ready and setup_known else "UNRESOLVED"
        setup_state = "TRADE_READY" if setup_ready else (maturity if setup_known and maturity not in {"", "UNKNOWN", "UNRESOLVED", "NONE"} else "FORMING") if setup_known else "UNRESOLVED"
        confirmation_final = "PROVEN" if confirmation_ready else "PENDING"
        risk_final = "READY" if risk_ready else "BLOCKED"
        execution_state = "BLOCKED"
    if not all_pass and not conflicts:
        next_required_event = {
            "DIRECTION_UNRESOLVED": "E6_MUST_ESTABLISH_A_DIRECTIONAL_THESIS_AND_SETUP",
            "SETUP_NOT_MATURE": "E6_SETUP_MUST_REACH_MATURE_OR_TRADE_READY",
            "ENTRY_CONFIRMATION_NOT_PROVEN": "E7_MUST_PROVE_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION",
            "RISK_NOT_READY": "E8_MUST_PROVE_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS",
        }.get(primary, "NEW_CLOSED_CANDLE_MUST_PROVIDE_DECISIVE_EVIDENCE")
    else:
        next_required_event = "NONE" if all_pass else "NEW_CLOSED_CANDLE_MUST_RESOLVE_THE_DECISIVE_CONFLICT"
    lifecycle = {"state": "NONE", "event": "NO_SURVIVING_SETUP" if not setup_known else "SETUP_FORMING", "active": False, "recovery": "E6_MUST_REBUILD_A_VALID_SETUP_FROM_NEW_CLOSED_CANDLE_EVIDENCE"} if not setup_known else {"state": "NONE", "event": "THESIS_ACTIVE" if setup_ready else "SETUP_FORMING", "active": False, "recovery": "E6_SETUP_MUST_MATURE"}
    return {"decision": decision, "decision_state": decision_state, "master_state": master_state, "thesis_state": thesis_state, "setup_state": setup_state, "confirmation_state": confirmation_final, "risk_state": risk_final, "execution_state": execution_state, "primary_blocker": primary, "secondary_blockers": [c for c in blockers if c != primary], "next_required_event": next_required_event, "all_gates_pass": all_pass, "hard_conflict": bool(conflicts), "resolved_conflicts": conflicts, "counter_evidence": [], "direction": direction, "setup": setup, "thesis": thesis, "e6_maturity": maturity, "e6_identity_resolved": direction_ready and setup_known, "e6_maturity_known": maturity not in {"", "UNKNOWN", "UNRESOLVED", "NONE"}, "e7_confirmation": confirmation, "e7_trigger_observed": trigger, "e8_risk_state": risk_state, "e8_plan_valid": _plan_valid(plan, direction), "e8_economic_blockers": economic, "trade_plan": plan if _plan_valid(plan, direction) else {}, "invalidation_lifecycle": lifecycle, "authority": {"thesis": "E6", "confirmation": "E7", "economics_risk": "E8", "market_control": "E9", "final_decision": "E9"}, "resolution_order": ["THESIS_IDENTITY", "MARKET_CONTROL", "HARD_CONFLICT", "SETUP_MATURITY", "CONFIRMATION", "RISK_ECONOMICS", "EXECUTION"]}


def _market_control(upstream: dict[str, EngineResult], e6: dict[str, Any]) -> dict[str, Any]:
    e1, e3, e4, e5, e7, e8 = (_out(upstream.get(x)) for x in ("E1", "E3", "E4", "E5", "E7", "E8"))
    event = e4.get("event", e4.get("auction_event", e4.get("liquidity_event", "NONE")))
    taker = e4.get("liquidity_taker", e4.get("taker", "UNKNOWN")); responder = e4.get("response_actor", e4.get("responder", "UNKNOWN"))
    auction_state = _text(e4.get("auction_state", e4.get("state", "UNKNOWN")))
    setup_direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("selected_direction")) if _e6_has_surviving_setup(e6) else "NEUTRAL"
    market_direction = _direction(e1.get("market_state"), e1.get("trend_state"), e1.get("pressure"), e1.get("structure"), e1.get("finding"))
    structure_direction = _direction(e3.get("structure_direction"), e3.get("external_state"), e3.get("internal_state"), e3.get("finding"))
    votes = [x for x in (market_direction, structure_direction, setup_direction) if x in DIRECTIONS]
    buy, sell = votes.count("BUY"), votes.count("SELL")
    dominant = "UNKNOWN" if not votes else "CONFLICTED" if buy == sell else "BUY" if buy > sell else "SELL"
    consensus = round(max(buy, sell) / len(votes) * 100.0, 2) if votes else 0.0
    taker_side, responder_side = _direction(taker), _direction(responder)
    controlled = responder_side if taker_side in DIRECTIONS and responder_side in DIRECTIONS and taker_side != responder_side else "UNKNOWN"
    confirmation = _confirmation_state(e7)
    control_state = "CONFIRMED" if auction_state in TERMINAL_AUCTION and controlled in DIRECTIONS else "PENDING" if event not in (None, "", "UNKNOWN", "NONE") else "UNRESOLVED"
    reasons = ["E9_MARKET_CONTROL_SYNTHESIS", "UPSTREAM_EVIDENCE_ONLY", "NO_INVENTED_AUCTION"]
    if auction_state not in TERMINAL_AUCTION: reasons.append("AUCTION_CONFIRMATION_PENDING")
    if confirmation != "PROVEN": reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if controlled == "UNKNOWN": reasons.append("CONTROL_OWNER_NOT_PROVEN")
    return {"market_intent": "AUCTION_CONFIRMED" if auction_state in TERMINAL_AUCTION else "LIQUIDITY_INTERACTION_PENDING" if taker_side in DIRECTIONS else "UNRESOLVED", "dominant_side": dominant, "controlled_side": controlled, "trapped_side": taker_side if controlled in DIRECTIONS else "UNKNOWN", "liquidity_target": e4.get("event_level", e4.get("liquidity_level")), "liquidity_type": e4.get("liquidity_type", "UNKNOWN"), "liquidity_taker": taker, "response_actor": responder, "auction_event": event, "auction_state": auction_state, "auction_quality": e4.get("auction_quality"), "liquidity_quality": e4.get("liquidity_quality"), "repricing_direction": _text(e5.get("repricing_direction", "UNKNOWN")), "repricing_state": e5.get("repricing_state", e5.get("value_response", "UNKNOWN")), "market_direction": market_direction, "structure_direction": structure_direction, "setup_direction": setup_direction, "direction_consensus": consensus, "control_strength": consensus, "control_state": control_state, "confirmation_state": confirmation, "evidence_count": len(votes), "evidence_sources": ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"], "authority": "E9", "authority_scope": "MARKET_CONTROL_SYNTHESIS_AND_FINAL_DECISION", "reason_codes": reasons}


def _opportunity_map(result: EngineResult) -> dict[str, Any]:
    o = result.output or {}; direction = _text(o.get("direction")); setup = _clean_setup(o.get("setup")); execution_ready = bool(o.get("all_gates_pass"))
    state = "EXECUTABLE" if execution_ready else "NO_EDGE" if not direction in DIRECTIONS or not setup else "WATCH"
    required = []
    if direction not in DIRECTIONS: required.append("DIRECTIONAL_THESIS")
    if not setup: required.append("SURVIVING_SETUP")
    if o.get("confirmation_state") != "PROVEN": required.append("CLOSED_CANDLE_CONFIRMATION")
    if o.get("risk_state") != "READY": required.append("SURVIVABLE_RISK_GEOMETRY")
    return {"state": state, "direction": direction, "score": 0.0 if state == "NO_EDGE" else 100.0 if execution_ready else 50.0, "thesis_aligned": bool(direction in DIRECTIONS and setup), "execution_ready": execution_ready, "do_not_execute": not execution_ready, "required_events": required, "opportunity_logic": "WATCH_ONLY_UNTIL_ALL_EXECUTION_GATES_PASS", "profit_source": "E6_THESIS_PLUS_E4_AUCTION_CONTROL_PLUS_E5_LOCATION", "risk_source": "E8_ONLY", "confirmation_source": "E7_ONLY", "market_control_source": "E9_SYNTHESIS"}


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    del snapshot
    e6, e7, e8 = _out(upstream.get("E6")), _out(upstream.get("E7")), upstream.get("E8")
    direction, setup, thesis = _e6_identity(e6)
    resolved = _resolve(direction, setup, thesis, e6, e7, e8, upstream)
    market_control = _market_control(upstream, e6)
    readiness_score = round(sum((25.0 if direction in DIRECTIONS else 0.0, 25.0 if resolved["setup_state"] == "TRADE_READY" else 0.0, 25.0 if resolved["confirmation_state"] == "PROVEN" else 0.0, 25.0 if resolved["risk_state"] == "READY" else 0.0)), 2)
    evidence_summary = {}
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id); output = _out(engine)
        evidence_summary[engine_id] = {"finding": _text(output.get("finding", output.get("state", "UNRESOLVED"))), "gate_passed": engine.gate_passed if engine else None, "reason_codes": _engine_codes(engine)}
    reasons = _dedupe(([resolved["primary_blocker"]] if resolved["primary_blocker"] != "NONE" else ["MASTER_GATES_PASSED"]) + resolved["secondary_blockers"] + market_control["reason_codes"])
    output = {**resolved, **market_control, "market_control": market_control, "master_resolution": "EXECUTE" if resolved["all_gates_pass"] else "REJECT" if resolved["decision_state"] == "REJECT" else "WAIT_FOR_PROOF", "readiness_score": readiness_score, "evidence_summary": evidence_summary, "opportunity": {}, "decision_contract": {"BUY_SELL_requires_all_gates": True, "NO_TRADE_on_missing_confirmation": True, "NO_EXECUTION_on_invalid_geometry": True, "NO_EXECUTION_on_hard_conflict": True, "E9_preserves_E6_thesis_identity": True, "E9_does_not_create_thesis": True, "E9_does_not_create_entry": True, "E9_does_not_create_target": True, "E9_does_not_override_E8_economics": True, "E9_does_not_invent_liquidity_events": True, "closed_candle_only": True, "no_surviving_E6_setup_cannot_be_promoted_to_thesis": True, "market_bias_is_not_trade_thesis": True}}
    result = EngineResult("E9", NAME, bool(resolved["all_gates_pass"]), readiness_score, output, tuple(reasons))
    opportunity = _opportunity_map(result)
    enriched = dict(result.output); enriched["opportunity"] = opportunity; enriched["opportunity_state"] = opportunity["state"]; enriched["opportunity_score"] = opportunity["score"]; enriched["opportunity_required_events"] = opportunity["required_events"]
    return EngineResult("E9", NAME, result.gate_passed, result.score, enriched, result.reason_codes)
