from __future__ import annotations

from typing import Any

from .contracts import EngineResult

_BOOTSTRAP_REASON_CODES = {
    "HISTORICAL_SAMPLE_INSUFFICIENT",
    "PROFIT_EDGE_NOT_PROVEN",
    "PROFIT_EXPECTANCY_UNQUANTIFIED",
    "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
    "PROBABILITY_EDGE_NOT_STATISTICALLY_ROBUST",
    "PROFIT_EDGE_NOT_TRUSTED",
    "CONDITIONAL_SAMPLE_RELAXED",
}
_CAUSAL_SETUPS = {"LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION", "BREAKOUT_RETEST"}
_REJECTION_EVENTS = ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM", "HIGH_REJECTION", "LOW_REJECTION")
_ACCEPTANCE_EVENTS = ("ACCEPTANCE",)


def _bootstrap_probability() -> dict[str, Any]:
    return {
        "state": "BOOTSTRAP_UNCALIBRATED",
        "probability": 0.50,
        "quality": 70.0,
        "sample": 0,
        "wins": 0,
        "losses": 0,
        "source": "CONSERVATIVE_NEUTRAL_PRIOR",
        "source_engine": "BOOTSTRAP_SURGERY",
        "stress_probability": 0.47,
        "wilson_lower": None,
        "wilson_upper": None,
        "decision_probability": 0.50,
        "trusted": False,
        "minimum_probability": 0.50,
        "method": "UNCALIBRATED_NEUTRAL_PRIOR__NOT_HISTORICAL_EVIDENCE",
    }


def _bootstrap_eligible(g: dict[str, Any]) -> bool:
    return bool(
        g.get("confirmation") == "CONFIRMED"
        and g.get("target_valid")
        and g.get("side_valid")
        and 0.50 <= float(g.get("risk_atr", 0.0)) <= 3.50
        and float(g.get("real_rr", 0.0)) >= 1.75
        and g.get("space_ok")
        and g.get("survival") == "ROBUST"
        and g.get("execution_ok")
        and float(g.get("target_realism", 0.0)) >= 0.70
        and float(g.get("stop_quality", 0.0)) >= 75.0
        and g.get("sensitivity") == "ROBUST"
        and g.get("risk_class") in {"A", "B"}
        and not set(g.get("hard_reasons") or ())
    )


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _payload(upstream: dict[str, EngineResult], key: str) -> dict[str, Any]:
    result = upstream.get(key)
    return dict(result.output or {}) if result else {}


def _direction(v: Any) -> str:
    x = _text(v)
    if x in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}: return "BUY"
    if x in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _rescue_e6_causal_candidate(original: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    """Preserve a causal market event as an E6 thesis even when E2 is still developing.

    This does not authorize a trade. E7 still owns entry confirmation and E8/E9
    retain independent permission gates.
    """
    out = dict(original.output or {})
    if bool(out.get("setup_exists")):
        return original

    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    event = _text(e4.get("event", e4.get("finding")))
    event_direction = _direction(e4.get("direction"))
    pressure = _direction(e1.get("directional_pressure", e1.get("pressure")))
    direction = event_direction if event_direction != "NEUTRAL" else pressure
    e2_finding = _text(e2.get("finding", e2.get("state")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    invalid = bool(e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True or _text(e3.get("lifecycle")) == "INVALIDATED")
    location = _text(e5.get("finding"))
    structural_location = _text(e5.get("structural_location"))
    favorable = "FAVORABLE_LOCATION" in location or structural_location in {"AT_SUPPORT", "AT_RESISTANCE"}
    space_key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    space = _num(e5.get(space_key))
    rejection = any(token in event for token in _REJECTION_EVENTS)
    acceptance = any(token in event for token in _ACCEPTANCE_EVENTS)

    # Conservative rescue: the causal event itself plus directional pressure,
    # favorable location, and adequate space are enough to form a hypothesis.
    # E2 disagreement or E3 mixed structure prevents automatic maturation.
    if invalid or direction not in {"BUY", "SELL"} or event_direction != direction:
        return original
    if pressure != direction or not favorable or space < 0.75:
        return original
    if not (rejection or acceptance):
        return original

    setup = "LIQUIDITY_REVERSAL" if rejection else "AUCTION_ACCEPTANCE_CONTINUATION"
    quality = 68.0 if rejection else 64.0
    reasons = ["E4_CAUSAL_MARKET_EVENT", "E1_DIRECTIONAL_PRESSURE", "E5_FAVORABLE_LOCATION", "E5_ADEQUATE_SPACE"]
    if "OPPORTUNITY IS DEVELOPING" in e2_finding or "DEVELOPING" in e2_finding:
        reasons.append("E2_DEVELOPING_NOT_REQUIRED_FOR_THESIS_FORMATION")
    if "MIXED" in e3_finding:
        reasons.append("E3_MIXED_STRUCTURE_RETAINED_AS_COUNTER_EVIDENCE")

    out.update({
        "state": "FORMING",
        "setup_state": "FORMING",
        "setup": setup,
        "setup_family": setup,
        "candidate_setup": setup,
        "candidate_setup_thesis": f"{direction} {setup} is forming from a causal E4 event with directional pressure, favorable location, and adequate structural space.",
        "direction": direction,
        "direction_thesis": f"{direction} thesis is supported by E1 pressure and E4 causal event.",
        "stage": "FORMING",
        "formation_stage": "FORMING",
        "lifecycle": "FORMING",
        "maturity": "HYPOTHESIS",
        "finding": f"{direction} {setup} is forming: causal market event survives initial E6 screening.",
        "thesis": f"{direction} {setup} is forming: causal market event survives initial E6 screening.",
        "thesis_owner": "E6",
        "setup_exists": True,
        "trade_ready": False,
        "trade_permission": False,
        "trade_readiness": "AWAITING_E7_E8_PROOF",
        "setup_quality": quality,
        "confidence": 76.0,
        "supporting_evidence": reasons,
        "counter_evidence": ["E2_OPPORTUNITY_STILL_DEVELOPING"] if "DEVELOPING" in e2_finding else [],
        "missing_evidence": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
        "missing_proof": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
        "next_required_evidence": ["E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"],
        "next_required_event": "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION",
        "reason_codes": reasons,
        "primary_blocker": "E7_CONFIRMATION_REQUIRED",
        "secondary_blockers": ["E2_OPPORTUNITY_UNRESOLVED"] if "DEVELOPING" in e2_finding else [],
        "governance_blockers": ["E7_CONFIRMATION_REQUIRED"],
        "candidate_states": [{"name": setup, "direction": direction, "causal_score": quality, "stage": "FORMING"}],
        "selected_hypothesis": setup,
        "candidate_setups": [setup],
        "reasoning_trace": {
            "summary": "E4 causal event -> E6 thesis formation",
            "decision": "FORM_OPPORTUNITY_THESIS_NOT_TRADE",
            "candidate_discovery": "CAUSAL_EVENT_SURVIVAL",
            "e2_proof_pending": True,
            "e3_structure_counter_evidence": "MIXED" in e3_finding,
            "space_atr": space,
            "space_is_constraint_not_invalidation": True,
            "e6_owns_thesis": True,
            "e7_owns_confirmation": True,
            "e8_owns_trade_economics": True,
            "e9_owns_trade_decision": True,
        },
        "space_diagnostic": {
            "available_space_atr": space,
            "minimum_required_space_atr": 0.75,
            "space_sufficient": True,
            "source": "E5_DIRECTIONAL_SPACE",
        },
    })
    return EngineResult(original.engine_id, original.name, False, max(float(original.score or 0.0), quality), out, tuple(dict.fromkeys(reasons)))


def _gate_e8_applicability(original: EngineResult, results: dict[str, EngineResult]) -> EngineResult:
    """E8 must evaluate economics only when E6 owns a surviving thesis."""
    e6 = results.get("E6")
    e6_out = dict(e6.output or {}) if e6 else {}
    if bool(e6_out.get("setup_exists")):
        return original
    out = dict(original.output or {})
    out.update({
        "state": "NOT_APPLICABLE",
        "economic_state": "NOT_APPLICABLE",
        "risk_state": "NOT_APPLICABLE",
        "risk_ready": False,
        "verified": False,
        "trade_plan_verified": False,
        "gate_passed": False,
        "bootstrap_mode": False,
        "reasons": ["E6_THESIS_REQUIRED"],
        "reason_codes": ["E6_THESIS_REQUIRED"],
        "primary_blocker": "E6_THESIS_REQUIRED",
        "secondary_blockers": [],
        "trade_plan": {},
        "applicability": "BLOCKED_NO_SURVIVING_E6_THESIS",
        "next_required_event": "E6_SURVIVING_CAUSAL_SETUP_THESIS",
    })
    return EngineResult(original.engine_id, original.name, False, original.score, out, ("E6_THESIS_REQUIRED",))


def _promote_independent_e6(original, snapshot, upstream):
    result = original(snapshot, upstream)
    if not isinstance(result, EngineResult):
        return result
    result = _rescue_e6_causal_candidate(result, upstream)
    out = dict(result.output or {})
    state = str(out.get("setup_state") or out.get("state") or "").upper()
    setup = str(out.get("setup") or out.get("setup_family") or "").upper()
    e4 = dict((upstream.get("E4").output if upstream.get("E4") else {}) or {})
    auction_state = str(e4.get("auction_state") or e4.get("state") or "").upper()
    terminal = auction_state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED", "RECLAIMED"} or "TERMINAL" in auction_state
    space = dict(out.get("space_diagnostic") or {})
    space_ok = float(space.get("available_space_atr", 0.0) or 0.0) >= 0.75
    quality = float(out.get("setup_quality", 0.0) or 0.0)
    direction = str(out.get("direction") or "NEUTRAL").upper()
    invalid = any("INVALID" in str(x).upper() for x in (out.get("invalidation") or []))
    if state in {"FORMING", "VALIDATING"} and setup in _CAUSAL_SETUPS and direction in {"BUY", "SELL"} and terminal and space_ok and quality >= 60.0 and not invalid:
        out["state"] = "MATURE"
        out["setup_state"] = "MATURE"
        out["stage"] = "MATURE"
        out["formation_stage"] = "MATURE"
        out["maturity"] = "MATURE"
        out["trade_readiness"] = "AWAITING_E7_E8_PROOF"
        out["bootstrap_maturity_promotion"] = True
        out["bootstrap_maturity_reason"] = "CAUSAL_SETUP_PLUS_TERMINAL_AUCTION_PLUS_STRUCTURAL_SPACE"
        out["reason_codes"] = [x for x in (out.get("reason_codes") or ()) if x != "E2_OPPORTUNITY_UNRESOLVED"]
        return EngineResult(result.engine_id, result.name, False, result.score, out, tuple(out.get("reason_codes") or ()))
    return result


def _bootstrap_e8_result(original, snapshot, results):
    gated = _gate_e8_applicability(original(snapshot, results), results)
    if not isinstance(gated, EngineResult):
        return gated
    if str(gated.output.get("state")) == "NOT_APPLICABLE":
        return gated
    result = gated
    out = dict(result.output or {})
    probability = dict(out.get("probability") or {})
    sample = int(probability.get("sample", 0) or 0)
    if sample > 0:
        return result
    if str(out.get("confirmation") or "").upper() != "CONFIRMED":
        return result

    geometry = dict(out.get("geometry") or {})
    target = dict(out.get("target") or {})
    space = dict(out.get("space") or {})
    survival = dict(out.get("survival") or {})
    execution = dict(out.get("execution") or {})
    target_realism = dict(out.get("target_realism") or {})
    stop_quality = dict(out.get("stop_quality") or {})
    sensitivity = dict(out.get("sensitivity") or {})
    risk_quality = dict(out.get("risk_quality") or {})

    p = _bootstrap_probability()
    rr = float(geometry.get("real_rr", 0.0) or 0.0)
    stress_p = p["stress_probability"]
    breakeven = 1.0 / max(1.0 + rr, 1e-9)
    expected = stress_p * rr - (1.0 - stress_p)
    margin = stress_p - breakeven
    economics = {
        "state": "ECONOMICALLY_ACCEPTABLE" if expected >= 0.10 and margin >= 0.05 else "ECONOMICALLY_INVALID",
        "expected_value_r": expected,
        "economic_edge_r": expected,
        "rr_used": rr,
        "stress_probability": stress_p,
        "breakeven_probability": breakeven,
        "economic_margin": margin,
        "effective_reward_r": rr,
        "effective_risk_r": 1.0,
        "expected_win_r": stress_p * rr,
        "expected_loss_r": (1.0 - stress_p),
        "profit_factor_proxy": (stress_p * rr) / max(1.0 - stress_p, 1e-9),
        "edge_status": "POSITIVE" if expected >= 0.10 else "NOT_PROVEN",
        "reasons": [],
        "mode": "BOOTSTRAP_NEUTRAL_PRIOR",
    }

    atr = float(out.get("atr14") or 0.0)
    entry = float(out.get("entry") or 0.0)
    stop = float((out.get("stop_plan") or {}).get("stop") or 0.0)
    target_level = float(target.get("level") or 0.0)
    direction = str(out.get("direction") or "").upper()
    if atr > 0 and entry > 0 and stop > 0 and target_level > 0:
        def ev(e: float, s: float, t: float) -> float:
            risk = abs(e - s) / atr
            reward = abs(t - e) / atr
            cost = float(execution.get("cost_atr", 0.0) or 0.0)
            real_rr = max(0.0, reward - cost) / max(risk + cost, 1e-9)
            return stress_p * real_rr - (1.0 - stress_p)
        ew = entry + (0.20 * atr if direction == "BUY" else -0.20 * atr)
        sw = stop - (0.20 * atr if direction == "BUY" else -0.20 * atr)
        tw = target_level - (0.20 * atr if direction == "BUY" else -0.20 * atr)
        vals = [ev(ew, stop, target_level), ev(entry, sw, target_level), ev(entry, stop, tw)]
        sensitivity = {"state": "ROBUST" if min(vals) >= 0 else "FRAGILE", "base": ev(entry, stop, target_level), "entry_worse": vals[0], "stop_worse": vals[1], "target_worse": vals[2], "worst_case": min(vals), "mode": "BOOTSTRAP_NEUTRAL_PRIOR"}
    else:
        sensitivity = {"state": "UNQUANTIFIED", "mode": "BOOTSTRAP_NEUTRAL_PRIOR"}

    risk_class = str(risk_quality.get("class") or "NO_TRADE")
    gates = {
        "confirmation": str(out.get("confirmation") or "").upper(),
        "target_valid": bool(target.get("credible") and target.get("level") is not None),
        "side_valid": bool(geometry.get("side_valid")),
        "risk_atr": geometry.get("risk_atr", 0.0),
        "real_rr": rr,
        "space_ok": bool(space.get("space_ok")),
        "survival": survival.get("state"),
        "execution_ok": bool(execution.get("cost_ok")),
        "target_realism": target_realism.get("score", 0.0),
        "stop_quality": stop_quality.get("score", 0.0),
        "sensitivity": sensitivity.get("state"),
        "risk_class": risk_class,
        "hard_reasons": [x for x in (out.get("reasons") or ()) if str(x) in {"REAL_RR_BELOW_MINIMUM", "EXECUTION_COST_TOO_HIGH", "STRUCTURAL_SURVIVAL_NOT_PROVEN", "EFFECTIVE_SPACE_UNRELIABLE", "EFFECTIVE_SPACE_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW", "STOP_QUALITY_TOO_LOW"}],
    }
    if not _bootstrap_eligible(gates):
        return result

    trade_plan = dict(out.get("trade_plan") or {})
    trade_plan.update({
        "valid": True,
        "direction": direction,
        "setup": out.get("setup"),
        "entry": entry,
        "stop": stop,
        "target": target_level,
        "risk_price": geometry.get("risk_price"),
        "risk_atr": geometry.get("risk_atr"),
        "reward_price": geometry.get("reward_price"),
        "rr": rr,
        "real_rr": rr,
        "target_source": target.get("source"),
        "stop_source": (out.get("stop_plan") or {}).get("source"),
        "economic_state": "ECONOMICALLY_ACCEPTABLE",
        "expected_value_r": expected,
        "economic_margin": margin,
        "robustness": sensitivity.get("state"),
        "target_realism": target_realism.get("score"),
        "stop_quality": stop_quality.get("score"),
        "risk_class": risk_class,
    })
    out["probability"] = p
    out["economics"] = economics
    out["economic_state"] = "ECONOMICALLY_ACCEPTABLE"
    out["risk_state"] = "READY"
    out["risk_ready"] = True
    out["verified"] = True
    out["trade_plan_verified"] = True
    out["gate_passed"] = True
    out["trade_plan"] = trade_plan
    out["sensitivity"] = sensitivity
    out["bootstrap_mode"] = True
    out["bootstrap_warning"] = "UNCALIBRATED_NEUTRAL_PRIOR__HISTORICAL_PROBABILITY_NOT_AVAILABLE"
    out["bootstrap_gates"] = gates
    reasons = [x for x in (out.get("reasons") or ()) if str(x) not in _BOOTSTRAP_REASON_CODES]
    reasons.append("BOOTSTRAP_UNCALIBRATED_ECONOMICS")
    out["reasons"] = list(dict.fromkeys(reasons))
    out["reason_codes"] = out["reasons"]
    return EngineResult(result.engine_id, result.name, True, max(result.score, 70.0), out, tuple(out["reason_codes"]))


def _attach_profit_edge_surgery(original, results, snapshot):
    original(results, snapshot)
    e8 = results.get("E8")
    if not e8 or not e8.output.get("bootstrap_mode"):
        return
    out = dict(e8.output)
    edge = dict(out.get("profit_edge") or {})
    edge["state"] = "BOOTSTRAP_ADVISORY"
    edge["trusted"] = False
    edge["calibration_state"] = "NO_CALIBRATION_DATA"
    edge["blockers"] = ["HISTORICAL_CALIBRATION_PENDING"]
    edge["method"] = "ADVISORY_ONLY_DURING_BOOTSTRAP"
    out["profit_edge"] = edge
    out["economic_evidence"] = {**dict(out.get("economic_evidence") or {}), "profit_edge_state": "BOOTSTRAP_ADVISORY", "calibration_pending": True}
    out["reasons"] = [x for x in (out.get("reasons") or ()) if str(x) not in _BOOTSTRAP_REASON_CODES]
    out["reason_codes"] = list(dict.fromkeys(out["reasons"]))
    results["E8"] = EngineResult(e8.engine_id, e8.name, True, e8.score, out, tuple(out["reason_codes"]))


def install(pipeline_module) -> None:
    if getattr(pipeline_module, "_BOOTSTRAP_SURGERY_INSTALLED", False):
        return
    original_e6 = pipeline_module.analyze_e6
    original_e8 = pipeline_module.analyze_e8
    original_attach = pipeline_module._attach_profit_edge

    def analyze_e6_wrapper(snapshot, upstream):
        return _promote_independent_e6(original_e6, snapshot, upstream)

    def analyze_e8_wrapper(snapshot, results):
        return _bootstrap_e8_result(original_e8, snapshot, results)

    def attach_wrapper(results, snapshot):
        return _attach_profit_edge_surgery(original_attach, results, snapshot)

    pipeline_module.analyze_e6 = analyze_e6_wrapper
    pipeline_module.analyze_e8 = analyze_e8_wrapper
    pipeline_module._attach_profit_edge = attach_wrapper
    pipeline_module._BOOTSTRAP_SURGERY_INSTALLED = True
