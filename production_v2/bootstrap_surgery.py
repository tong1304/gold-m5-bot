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


def _promote_independent_e6(original, snapshot, upstream):
    result = original(snapshot, upstream)
    if not isinstance(result, EngineResult):
        return result
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
    result = original(snapshot, results)
    if not isinstance(result, EngineResult):
        return result
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

    # Recompute the probability-dependent economic/sensitivity checks with an
    # explicit neutral prior. This is not historical evidence and never claims
    # to be calibrated; it only prevents a brand-new system from being locked
    # forever before its first resolved trade outcomes exist.
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

    # Sensitivity is recomputed from the same 47% stressed prior.
    atr = float(out.get("atr14") or 0.0)
    entry = float(out.get("entry") or 0.0)
    stop = float((out.get("stop_plan") or {}).get("stop") or 0.0)
    target_level = float(target.get("level") or 0.0)
    direction = str(out.get("direction") or "").upper()
    if atr > 0 and entry > 0 and stop > 0 and target_level > 0:
        def ev(e: float, s: float, t: float) -> float:
            risk = abs(e - s) / atr
            reward = abs(t - e) / atr
            real_rr = max(0.0, reward - float(execution.get("cost_atr", 0.0) or 0.0)) / max(risk + float(execution.get("cost_atr", 0.0) or 0.0), 1e-9)
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
