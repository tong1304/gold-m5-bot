from __future__ import annotations

from typing import Any

from .contracts import EngineResult

NAME = "Master Decision Brain"
QUESTION = "Who controls the auction, where is liquidity, and should this trade be taken after reconciling all evidence?"
ARCHITECTURE = "E9_MASTER_DECISION_MARKET_CONTROL_V56"
VERSION = "56.0"
DIRECTIONS = {"BUY", "SELL"}

HARD_CONFLICT_CODES = {"THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT", "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED", "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED", "E3_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED"}
ECONOMIC_BLOCKERS = {"INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID", "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET", "RISK_QUALITY_BELOW_DECISION_THRESHOLD"}
BLOCKER_PRIORITY = ("THESIS_INVALIDATED", "E6_THESIS_INVALIDATED", "E7_CONFIRMATION_INVALIDATED", "E8_RISK_INVALIDATED", "E3_STRUCTURE_INVALIDATED", "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED", "E3_THESIS_INVALIDATED", "MARKET_STATE_CONFLICT", "STRUCTURE_THESIS_CONFLICT", "OPPOSING_LIQUIDITY_THESIS", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT", "INVALID_TRADE_GEOMETRY", "INVALID_RISK_GEOMETRY", "RISK_GEOMETRY_INVALID", "REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "STRESSED_PROBABILITY_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW", "PROBABILITY_EDGE_NOT_TRUSTWORTHY", "NO_USABLE_STRUCTURAL_TARGET", "ENTRY_CONFIRMATION_NOT_PROVEN", "SETUP_NOT_MATURE", "RISK_NOT_READY", "RISK_QUALITY_BELOW_DECISION_THRESHOLD", "DIRECTION_UNRESOLVED")
CONFIRMATION_PROVEN = {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"}
MATURITY_READY = {"MATURE", "TRADE_READY", "VALIDATED", "CONFIRMED"}
RISK_READY_STATES = {"READY", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY", "VALIDATED", "PASS", "PASSED", "COMPLETE"}
TERMINAL_AUCTION = {"CONFIRMED", "TERMINALLY_CONFIRMED", "RECLAIMED"}


def _out(engine: EngineResult | None) -> dict[str, Any]:
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
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
                elif isinstance(flag, (str, int, float)) and str(flag).strip():
                    values.append(flag)
    return _dedupe(values)


def _engine_codes(engine: EngineResult | None) -> list[str]:
    if not engine:
        return []
    return _dedupe(_codes(_out(engine)) + [_text(v) for v in (engine.reason_codes or ()) if v])


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


def _e6_identity(e6: dict[str, Any]) -> tuple[str, str, str]:
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
        value = output.get(key)
        if value not in (None, ""):
            return _text(value)
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


def _trigger_observed(e7: dict[str, Any]) -> bool:
    for key in ("trigger_observed", "valid_trigger", "closed_candle_trigger"):
        if e7.get(key) is True:
            return True
    state = _state(e7, ("trigger_state", "trigger", "entry_trigger"))
    if state in {"VALID", "VALIDATED", "CONFIRMED", "PROVEN", "TRADE_READY"}:
        return True
    return any(code in {"VALID_CLOSED_CANDLE_TRIGGER", "TRIGGER_CONFIRMED", "CONFIRMATION_PROVEN"} for code in _codes(e7))


def _confirmation_state(e7: dict[str, Any]) -> str:
    codes = _codes(e7)
    if any(code in {"E7_CONFIRMATION_INVALIDATED", "CONFIRMATION_INVALIDATED"} for code in codes):
        return "INVALIDATED"
    if any(code in {"CONFIRMATION_PROVEN", "CAUSAL_FOLLOW_THROUGH_PROVEN"} for code in codes):
        return "PROVEN"
    if any(code in {"PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING", "TRIGGER_OBSERVED_NOT_AUTOMATIC_CONFIRMATION", "LIQUIDITY_RECLAIM_LEVEL_REQUIRED"} for code in codes):
        return "PENDING"
    return _state(e7, ("confirmation_state", "confirmation", "proof_state", "trigger_state"))


def _plan_valid(plan: dict[str, Any], direction: str) -> bool:
    if direction not in DIRECTIONS or not isinstance(plan, dict):
        return False
    try:
        entry = float(plan["entry"]); stop = float(plan["stop_loss"]); target = float(plan.get("take_profit_2", plan.get("take_profit", plan.get("tp2"))))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(value == value for value in (entry, stop, target)):
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
        engine = upstream.get(engine_id); output = _out(engine); codes = _engine_codes(engine)
        found.extend(c for c in codes if c in HARD_CONFLICT_CODES)
        for key in ("state", "finding", "lifecycle", "invalidation", "structure_state", "thesis_state"):
            value = _text(output.get(key))
            if value in HARD_CONFLICT_CODES or value.endswith("_INVALIDATED") or "THESIS_INVALIDATED" in value:
                if value: found.append(value)
        invalidations = output.get("invalidations")
        if isinstance(invalidations, dict):
            for key, value in invalidations.items():
                if value is True and ("STRUCTURE" in _text(key) or "THESIS" in _text(key) or "INVALIDAT" in _text(key)):
                    found.append(_text(key))
        if engine_id == "E3":
            finding = _text(output.get("finding")); lifecycle = _text(output.get("lifecycle"))
            if "_INVALIDATED" in finding or lifecycle == "INVALIDATED": found.append("E3_STRUCTURE_INVALIDATED")
    return _dedupe(found)


def _economic_blockers(e8: EngineResult | None) -> list[str]:
    found: list[str] = []
    for candidate in _walk(_out(e8)):
        found.extend(c for c in _codes(candidate) if c in ECONOMIC_BLOCKERS)
    return _dedupe(found)


def _first(output: dict[str, Any], keys: tuple[str, ...], default: Any = "UNKNOWN") -> Any:
    for key in keys:
        value = output.get(key)
        if value not in (None, "", [], {}): return value
    return default


def _market_control(upstream: dict[str, EngineResult], e6: dict[str, Any]) -> dict[str, Any]:
    e1 = _out(upstream.get("E1")); e2 = _out(upstream.get("E2")); e3 = _out(upstream.get("E3")); e4 = _out(upstream.get("E4")); e5 = _out(upstream.get("E5")); e7 = _out(upstream.get("E7")); e8 = _out(upstream.get("E8"))
    event = _first(e4, ("event", "auction_event", "liquidity_event"), "NONE")
    taker = _first(e4, ("liquidity_taker", "taker", "auction_taker"), "UNKNOWN")
    responder = _first(e4, ("response_actor", "responder", "auction_responder"), "UNKNOWN")
    auction_state = _text(_first(e4, ("auction_state", "state"), "UNKNOWN"))
    liquidity_type = _first(e4, ("liquidity_type",), "UNKNOWN"); level = _first(e4, ("event_level", "liquidity_level", "level"), None)
    liquidity_quality = _first(e4, ("liquidity_quality",), None); auction_quality = _first(e4, ("auction_quality",), None)
    repricing_state = _first(e5, ("repricing_state", "repricing_direction", "value_response"), "UNKNOWN")
    market_direction = _direction(e1.get("market_state"), e1.get("trend_state"), e1.get("pressure"), e1.get("structure"), e1.get("finding"))
    structure_direction = _direction(e3.get("structure_direction"), e3.get("external_state"), e3.get("internal_state"), e3.get("finding")); setup_direction = _direction(e6.get("direction"), e6.get("direction_thesis"), e6.get("selected_direction"), e6.get("finding"))
    votes = [x for x in (market_direction, structure_direction, setup_direction) if x in DIRECTIONS]; buy_votes = votes.count("BUY"); sell_votes = votes.count("SELL")
    dominant_side = "UNKNOWN" if not votes else "CONFLICTED" if buy_votes == sell_votes else "BUY" if buy_votes > sell_votes else "SELL"
    consensus = round(max(buy_votes, sell_votes) / len(votes) * 100.0, 2) if votes else 0.0
    taker_side = _direction(taker); responder_side = _direction(responder); controlled_side = responder_side if taker_side in DIRECTIONS and responder_side in DIRECTIONS and taker_side != responder_side else "UNKNOWN"; trapped_side = taker_side if controlled_side in DIRECTIONS else "UNKNOWN"
    if "FAILED_BREAK" in _text(event) and responder_side in DIRECTIONS: intent = "LIQUIDITY_HUNT_REJECTED" if auction_state in TERMINAL_AUCTION else "LIQUIDITY_TEST_PENDING"
    elif auction_state in TERMINAL_AUCTION and taker_side in DIRECTIONS: intent = "AUCTION_CONFIRMED"
    elif taker_side in DIRECTIONS: intent = "LIQUIDITY_INTERACTION_PENDING"
    else: intent = "UNRESOLVED"
    r = _text(repricing_state); repricing_direction = "UP" if r in {"ACCEPTANCE_ABOVE_VALUE", "ABOVE_VALUE", "UP", "BULLISH"} else "DOWN" if r in {"ACCEPTANCE_BELOW_VALUE", "BELOW_VALUE", "DOWN", "BEARISH"} else "UNKNOWN"
    confirmation = _confirmation_state(e7); control_state = "CONFIRMED" if auction_state in TERMINAL_AUCTION and controlled_side in DIRECTIONS else "PENDING" if event not in {None, "", "UNKNOWN", "NONE"} or taker_side in DIRECTIONS else "UNRESOLVED"
    evidence_count = sum(x not in (None, "", "UNKNOWN", "NONE") for x in (event, taker, responder, repricing_state, market_direction, structure_direction)); numeric = [float(x) for x in (liquidity_quality, auction_quality) if isinstance(x, (int, float))]; control_strength = round((consensus + sum(numeric)) / (1 + len(numeric)), 2) if evidence_count else 0.0
    reasons = ["E9_MARKET_CONTROL_SYNTHESIS", "UPSTREAM_EVIDENCE_ONLY", "NO_INVENTED_AUCTION"]
    if auction_state not in TERMINAL_AUCTION: reasons.append("AUCTION_CONFIRMATION_PENDING")
    if confirmation != "PROVEN": reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if dominant_side == "CONFLICTED": reasons.append("DIRECTIONAL_CONTROL_CONFLICT")
    if controlled_side == "UNKNOWN": reasons.append("CONTROL_OWNER_NOT_PROVEN")
    return {"market_intent": intent, "dominant_side": dominant_side, "controlled_side": controlled_side, "trapped_side": trapped_side, "liquidity_target": level, "liquidity_type": liquidity_type, "liquidity_taker": taker, "response_actor": responder, "auction_event": event, "auction_state": auction_state, "auction_quality": auction_quality, "liquidity_quality": liquidity_quality, "repricing_direction": repricing_direction, "repricing_state": repricing_state, "market_direction": market_direction, "structure_direction": structure_direction, "setup_direction": setup_direction, "direction_consensus": consensus, "control_strength": control_strength, "control_state": control_state, "confirmation_state": confirmation, "evidence_count": evidence_count, "evidence_sources": ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"], "evidence_basis": {"E1": market_direction, "E2": _first(e2, ("finding", "regime", "opportunity"), "UNKNOWN"), "E3": structure_direction, "E4": event, "E5": repricing_state, "E6": setup_direction, "E7": confirmation, "E8": _first(e8, ("risk_state", "economic_state"), "UNKNOWN")}, "reason_codes": reasons, "authority": "E9", "authority_scope": "MARKET_CONTROL_SYNTHESIS_AND_FINAL_DECISION"}


def _invalidation_lifecycle(conflicts: list[str], confirmation: str, economic: list[str], maturity: str) -> dict[str, Any]:
    if conflicts: return {"state": "INVALIDATED" if any("INVALIDAT" in c for c in conflicts) else "CONFLICTED", "event": "HARD_INVALIDATION" if any("INVALIDAT" in c for c in conflicts) else "HARD_CONFLICT", "active": True, "recovery": "NEW_CLOSED_CANDLE_MUST_RESOLVE_THE_DECISIVE_CONFLICT"}
    if confirmation == "INVALIDATED": return {"state": "INVALIDATED", "event": "CONFIRMATION_INVALIDATED", "active": True, "recovery": "E7_MUST_REBUILD_AND_REPROVE_SETUP_CONFIRMATION"}
    if economic: return {"state": "RISK_BLOCKED", "event": "ECONOMIC_VETO_ACTIVE", "active": False, "recovery": "E8_MUST_REESTABLISH_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS"}
    if maturity in MATURITY_READY: return {"state": "NONE", "event": "THESIS_ACTIVE", "active": False, "recovery": "E7_CONFIRMATION_REQUIRED"}
    return {"state": "NONE", "event": "SETUP_FORMING", "active": False, "recovery": "E6_SETUP_MUST_MATURE"}


def _resolve(direction: str, setup: str, thesis: str, e6: dict[str, Any], e7: dict[str, Any], e8: EngineResult | None, upstream: dict[str, EngineResult]) -> dict[str, Any]:
    maturity = _state(e6, ("maturity", "setup_maturity", "setup_stage", "stage", "formation_stage", "lifecycle")); confirmation = _confirmation_state(e7); trigger = _trigger_observed(e7); boundary, plan = _e8_boundary(e8); economic = _economic_blockers(e8); conflicts = _hard_conflicts(upstream)
    direction_ready = direction in DIRECTIONS; setup_known = bool(_clean_setup(setup)); setup_ready = direction_ready and setup_known and maturity in MATURITY_READY; confirmation_ready = confirmation in CONFIRMATION_PROVEN and trigger
    risk_state = _text(boundary.get("risk_gate") or boundary.get("risk_state") or boundary.get("economic_state") or boundary.get("plan_status") or ""); risk_ready = not economic and risk_state in RISK_READY_STATES and _plan_valid(plan, direction)
    blockers = _dedupe(conflicts + economic)
    if not direction_ready: blockers.append("DIRECTION_UNRESOLVED")
    if not setup_ready: blockers.append("SETUP_NOT_MATURE")
    if not confirmation_ready: blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not risk_ready: blockers.append("RISK_NOT_READY")
    blockers = _dedupe(blockers); primary = next((c for c in BLOCKER_PRIORITY if c in blockers), "NONE"); lifecycle = _invalidation_lifecycle(conflicts, confirmation, economic, maturity); all_pass = direction_ready and setup_ready and confirmation_ready and risk_ready and not conflicts and not economic
    if all_pass: decision, decision_state, master_state = direction, "EXECUTE", "EXECUTE"; thesis_state, setup_state = "ESTABLISHED", "TRADE_READY"; confirmation_final, risk_final, execution_state = "PROVEN", "READY", "READY"; next_event = "NONE"
    elif conflicts: decision, decision_state, master_state = "NO_TRADE", "REJECT", "REJECTED_HARD_CONFLICT"; thesis_state = "INVALIDATED" if any("INVALIDAT" in c for c in conflicts) else "CONFLICTED"; setup_state = confirmation_final = risk_final = execution_state = "BLOCKED"; next_event = lifecycle["recovery"]
    else:
        decision, decision_state, master_state = "NO_TRADE", "WAIT_FOR_PROOF", "WAIT_FOR_PROOF"; thesis_state = "ESTABLISHED" if direction_ready and setup_known else "UNRESOLVED"; setup_state = "TRADE_READY" if setup_ready else (maturity if maturity not in {"", "UNKNOWN", "UNRESOLVED", "NONE"} else "FORMING") if setup_known else "UNRESOLVED"; confirmation_final = "PROVEN" if confirmation_ready else "PENDING"; risk_final = "READY" if risk_ready else "BLOCKED"; execution_state = "BLOCKED"; next_event = {"DIRECTION_UNRESOLVED": "E6_MUST_ESTABLISH_A_DIRECTIONAL_THESIS_AND_SETUP", "SETUP_NOT_MATURE": "E6_SETUP_MUST_REACH_MATURE_OR_TRADE_READY", "ENTRY_CONFIRMATION_NOT_PROVEN": "E7_MUST_PROVE_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION", "RISK_NOT_READY": "E8_MUST_PROVE_SURVIVABLE_TRADE_GEOMETRY_AND_ECONOMICS"}.get(primary, lifecycle["recovery"]); next_event = lifecycle["recovery"] if confirmation == "INVALIDATED" else next_event
    return {"decision": decision, "decision_state": decision_state, "master_state": master_state, "thesis_state": thesis_state, "setup_state": setup_state, "confirmation_state": confirmation_final, "risk_state": risk_final, "execution_state": execution_state, "primary_blocker": primary, "secondary_blockers": [c for c in blockers if c != primary], "next_required_event": next_event, "all_gates_pass": all_pass, "hard_conflict": bool(conflicts), "resolved_conflicts": conflicts, "counter_evidence": [], "direction": direction, "setup": setup, "thesis": thesis, "e6_maturity": maturity, "e6_identity_resolved": direction_ready and setup_known, "e6_maturity_known": maturity not in {"", "UNKNOWN", "UNRESOLVED", "NONE"}, "e7_confirmation": confirmation, "e7_trigger_observed": trigger, "e8_risk_state": risk_state, "e8_plan_valid": _plan_valid(plan, direction), "e8_economic_blockers": economic, "trade_plan": plan if _plan_valid(plan, direction) else {}, "invalidation_lifecycle": lifecycle, "authority": {"thesis": "E6", "confirmation": "E7", "economics_risk": "E8", "market_control": "E9", "final_decision": "E9"}, "resolution_order": ["THESIS_IDENTITY", "MARKET_CONTROL", "HARD_CONFLICT", "SETUP_MATURITY", "CONFIRMATION", "RISK_ECONOMICS", "EXECUTION"]}


def _opportunity_map(result: EngineResult) -> dict[str, Any]:
    """Classify latent opportunity without creating an executable trade."""
    o = result.output or {}
    mc = o.get("market_control") or {}
    direction = _text(o.get("direction"))
    blockers = set(str(x) for x in (o.get("secondary_blockers") or []))
    primary = _text(o.get("primary_blocker"))
    maturity = _text(o.get("e6_maturity"))
    confirmation = _text(o.get("confirmation_state"))
    risk = _text(o.get("risk_state"))
    dominant = _text(mc.get("dominant_side"))
    controlled = _text(mc.get("controlled_side"))
    auction = _text(mc.get("auction_state"))
    consensus = float(mc.get("direction_consensus") or 0.0)
    control_strength = float(mc.get("control_strength") or 0.0)

    thesis_aligned = direction in DIRECTIONS and dominant == direction
    control_confirmed = controlled == direction
    auction_confirmed = auction in TERMINAL_AUCTION
    hard_stop = bool(o.get("hard_conflict"))
    execution_ready = bool(o.get("all_gates_pass"))

    score = 0.0
    if direction in DIRECTIONS: score += 20.0
    if thesis_aligned: score += 20.0
    if consensus >= 66.0: score += 15.0
    if control_confirmed: score += 15.0
    elif controlled == "UNKNOWN" and consensus >= 66.0: score += 5.0
    if auction_confirmed: score += 10.0
    if maturity in MATURITY_READY: score += 10.0
    elif maturity in {"FORMING", "VALIDATING", "ESTABLISHED"}: score += 5.0
    if confirmation == "PROVEN": score += 5.0
    if risk == "READY": score += 5.0
    score = round(min(score, 100.0), 2)

    if execution_ready:
        state = "EXECUTABLE"
    elif hard_stop:
        state = "INVALIDATED"
    elif direction in DIRECTIONS and thesis_aligned and (score >= 55.0 or control_strength >= 60.0):
        state = "WATCH"
    else:
        state = "NO_EDGE"

    required: list[str] = []
    if not thesis_aligned: required.append("DIRECTIONAL_CONSENSUS")
    if not control_confirmed: required.append("LIQUIDITY_CONTROL_CONFIRMATION")
    if not auction_confirmed: required.append("AUCTION_TERMINAL_CONFIRMATION")
    if maturity not in MATURITY_READY: required.append("SETUP_MATURITY")
    if confirmation != "PROVEN": required.append("CLOSED_CANDLE_CONFIRMATION")
    if risk != "READY": required.append("SURVIVABLE_RISK_GEOMETRY")
    if primary and primary not in required: required.append(primary)

    return {
        "state": state,
        "direction": direction,
        "score": score,
        "thesis_aligned": thesis_aligned,
        "control_confirmed": control_confirmed,
        "auction_confirmed": auction_confirmed,
        "execution_ready": execution_ready,
        "do_not_execute": not execution_ready,
        "required_events": required,
        "opportunity_logic": "WATCH_ONLY_UNTIL_ALL_EXECUTION_GATES_PASS",
        "profit_source": "E6_THESIS_PLUS_E4_AUCTION_CONTROL_PLUS_E5_LOCATION",
        "risk_source": "E8_ONLY",
        "confirmation_source": "E7_ONLY",
        "market_control_source": "E9_SYNTHESIS",
        "economic_blockers": list(o.get("e8_economic_blockers") or []),
        "secondary_blockers": sorted(blockers),
    }


def analyze_e9(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    del snapshot
    e6 = _out(upstream.get("E6")); e7 = _out(upstream.get("E7")); e8 = upstream.get("E8"); direction, setup, thesis = _e6_identity(e6); resolved = _resolve(direction, setup, thesis, e6, e7, e8, upstream); market_control = _market_control(upstream, e6)
    readiness_score = round(sum((25.0 if direction in DIRECTIONS else 0.0, 25.0 if resolved["setup_state"] == "TRADE_READY" else 12.5 if resolved["setup_state"] in {"FORMING", "VALIDATING", "MATURE"} else 0.0, 25.0 if resolved["confirmation_state"] == "PROVEN" else 12.5 if resolved["confirmation_state"] == "PENDING" else 0.0, 25.0 if resolved["risk_state"] == "READY" else 0.0)), 2)
    evidence_summary = {}
    for engine_id in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
        engine = upstream.get(engine_id); output = _out(engine); evidence_summary[engine_id] = {"finding": _text(output.get("finding", output.get("state", "UNRESOLVED"))), "gate_passed": engine.gate_passed if engine else None, "reason_codes": _engine_codes(engine)}
    lifecycle = resolved["invalidation_lifecycle"]
    professional_reasoning = {"primary_thesis": {"direction": direction, "setup": setup, "state": resolved["thesis_state"], "text": thesis}, "market_control": market_control, "master": {"state": resolved["master_state"], "decision_state": resolved["decision_state"], "readiness_score": readiness_score}, "setup": {"direction": direction, "state": resolved["setup_state"], "name": setup, "maturity": resolved["e6_maturity"]}, "execution": {"state": resolved["execution_state"], "decision_state": resolved["decision_state"]}, "confirmation": {"state": resolved["confirmation_state"], "trigger_observed": resolved["e7_trigger_observed"]}, "risk": {"state": resolved["risk_state"], "economic_blockers": resolved["e8_economic_blockers"]}, "invalidation": lifecycle, "conflicts": resolved["resolved_conflicts"], "hard_invalidations": [c for c in resolved["resolved_conflicts"] if "INVALIDAT" in c], "primary_blocker": resolved["primary_blocker"], "next_required_event": resolved["next_required_event"], "closed_candle_only": True, "no_lookahead": True, "authority": resolved["authority"]}
    reason_codes = _dedupe(([resolved["primary_blocker"]] if resolved["primary_blocker"] != "NONE" else ["MASTER_GATES_PASSED"]) + resolved["secondary_blockers"] + resolved["resolved_conflicts"] + market_control["reason_codes"] + (["E9_HARD_CONFLICT"] if resolved["hard_conflict"] else []))
    report_fields = {"market_intent": market_control["market_intent"], "dominant_side": market_control["dominant_side"], "controlled_side": market_control["controlled_side"], "trapped_side": market_control["trapped_side"], "liquidity_target": market_control["liquidity_target"], "repricing_direction": market_control["repricing_direction"], "repricing_state": market_control["repricing_state"], "control_strength": market_control["control_strength"], "control_state": market_control["control_state"], "liquidity_taker": market_control["liquidity_taker"], "response_actor": market_control["response_actor"], "auction_event": market_control["auction_event"], "auction_state": market_control["auction_state"], "liquidity_type": market_control["liquidity_type"], "auction_quality": market_control["auction_quality"], "liquidity_quality": market_control["liquidity_quality"], "direction_consensus": market_control["direction_consensus"]}
    output = {**resolved, **report_fields, "market_control": market_control, "master_resolution": "EXECUTE" if resolved["all_gates_pass"] else "REJECT" if resolved["decision_state"] == "REJECT" else "WAIT_FOR_PROOF", "readiness_score": readiness_score, "evidence_summary": evidence_summary, "professional_reasoning": professional_reasoning, "decision_contract": {"BUY_SELL_requires_all_gates": True, "NO_TRADE_on_missing_confirmation": True, "NO_EXECUTION_on_invalid_geometry": True, "NO_EXECUTION_on_hard_conflict": True, "E9_preserves_E6_thesis_identity": True, "E9_does_not_create_thesis": True, "E9_does_not_create_entry": True, "E9_does_not_create_target": True, "E9_does_not_override_E8_economics": True, "E9_synthesizes_market_control_from_upstream_only": True, "E9_does_not_invent_liquidity_events": True, "E9_market_control_is_reportable_at_top_level": True, "closed_candle_only": True, "counter_evidence_does_not_equal_hard_conflict": True, "master_state_machine": True, "invalidation_lifecycle_explicit": True, "next_required_event_explicit": True, "structure_invalidation_is_hard_conflict": True, "hard_conflict_detects_state_and_finding": True, "set_membership_is_type_safe": True}}
    result = EngineResult("E9", NAME, bool(resolved["all_gates_pass"]), readiness_score, output, tuple(reason_codes))
    opportunity = _opportunity_map(result)
    enriched = dict(result.output)
    enriched["opportunity"] = opportunity
    enriched["opportunity_state"] = opportunity["state"]
    enriched["opportunity_score"] = opportunity["score"]
    enriched["opportunity_required_events"] = opportunity["required_events"]
    enriched["decision_contract"] = {**enriched["decision_contract"], "E9_can_identify_watch_opportunities_without_execution": True, "E9_cannot_bypass_E8": True}
    return EngineResult("E9", NAME, result.gate_passed, result.score, enriched, result.reason_codes)
