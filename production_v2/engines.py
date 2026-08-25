from __future__ import annotations

import importlib
from statistics import mean
from typing import Any

from .contracts import EngineResult

ENGINE_NAMES = {
    "E1": "Market State Engine",
    "E2": "Market Regime Engine",
    "E3": "Market Structure Engine",
    "E4": "Liquidity Engine",
    "E5": "Location Engine",
    "E6": "Setup Engine",
    "E7": "Confirmation Engine",
    "E8": "Risk Engine",
    "E9": "Execution Decision Engine",
}

SUB_ENGINE_CODES = {
    "E1": ["1A","1B","1C","1D","1E","1F","1G"],
    "E2": ["2A","2B","2C","2D","2E","2F"],
    "E3": ["3A","3B","3C","3D","3E","3F"],
    "E4": ["4A","4B","4C","4D","4E","4F"],
    "E5": ["5A","5B","5C","5D","5E","5F"],
    "E6": ["6A","6B","6C","6D","6E","6F"],
    "E7": ["7A","7B","7C","7D","7E","7F"],
    "E8": ["8A","8B","8C","8D","8E","8F","8G"],
    "E9": ["9A","9B","9C","9D","9E","9F","9G","9H"],
}

SUFFIX = {
    '1A':'a_data_quality','1B':'b_volatility_state','1C':'c_trend_state','1D':'d_range_state','1E':'e_compression','1F':'f_expansion','1G':'g_transition',
    '2A':'a_trend_regime','2B':'b_range_regime','2C':'c_mean_reversion_behavior','2D':'d_breakout_regime','2E':'e_regime_phase','2F':'f_regime_transition',
    '3A':'a_swing_detection','3B':'b_structure_classification','3C':'c_break_of_structure','3D':'d_structural_failure','3E':'e_structure_strength','3F':'f_internal_external_structure',
    '4A':'a_liquidity_zone_detection','4B':'b_sweep_detection','4C':'c_reaction_rejection','4D':'d_acceptance','4E':'e_reclaim_failed_break','4F':'f_liquidity_strength_quality',
    '5A':'a_equilibrium_value','5B':'b_structural_location','5C':'c_liquidity_location','5D':'d_extension','5E':'e_available_space','5F':'f_location_quality',
    '6A':'a_setup_context','6B':'b_setup_archetype','6C':'c_setup_formation_state_machine','6D':'d_setup_invalidation','6E':'e_setup_quality','6F':'f_setup_maturity',
    '7A':'a_trigger_detection','7B':'b_trigger_quality','7C':'c_follow_through','7D':'d_failure_invalidation','7E':'e_execution_conditions','7F':'f_confirmation_quality',
    '8A':'a_invalidation_model','8B':'b_stop_placement','8C':'c_target_liquidity_objective','8D':'d_r_multiple','8E':'e_position_size','8F':'f_exposure_limits','8G':'g_risk_gate',
    '9A':'a_data_gate','9B':'b_context_gate','9C':'c_setup_gate','9D':'d_confirmation_gate','9E':'e_risk_gate','9F':'f_execution_gate','9G':'g_final_decision','9H':'h_decision_logging',
}


def _module(code: str):
    return importlib.import_module(f"trading_system.engines.e{code[0]}.{SUFFIX[code]}")


def _professional_gate(engine_id: str, output: dict[str, Any], context: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Hard decision conditions for the nine professional decision layers.

    Scores describe quality; these gates decide whether the evidence is sufficient
    to continue. No score is allowed to override a failed professional gate.
    """
    def state(code: str, key: str = "state") -> Any:
        return output.get(code, {}).get(key)

    direction = state("1C", "direction")
    if engine_id == "E1":
        if direction not in {"UP", "DOWN"}:
            return False, ("E1_MARKET_STATE_UNCLEAR",)
        if state("1G") == "TRANSITION":
            return False, ("E1_MARKET_STATE_TRANSITION",)
        return True, ()

    if engine_id == "E2":
        if direction not in {"UP", "DOWN"}:
            return False, ("E2_DIRECTION_UNCLEAR",)
        if state("2F") == "TRANSITION":
            return False, ("E2_REGIME_TRANSITION",)
        regime_states = [state(code, "regime") for code in ("2A", "2B", "2C", "2D", "2E", "2F")]
        if not any(s in {"TREND", "RANGE", "MEAN_REVERSION", "BREAKOUT", "EXPANSION_PHASE", "BALANCED_PHASE", "STABLE"} for s in regime_states):
            return False, ("E2_REGIME_UNCLEAR",)
        return True, ()

    if engine_id == "E3":
        structure = state("3B")
        bos = state("3C")
        aligned = state("3F") == "INTERNAL_EXTERNAL_ALIGNED"
        if structure not in {"BULLISH", "BEARISH"} or bos != "BOS_CONFIRMED" or not aligned:
            return False, ("E3_STRUCTURE_NOT_CONFIRMED",)
        return True, ()

    if engine_id == "E4":
        quality = state("4F") == "QUALITY_MEASURABLE"
        sweep = state("4B") in {"SWEEP_HIGH", "SWEEP_LOW"}
        rejection = state("4C") == "REJECTION"
        acceptance = state("4D") == "ACCEPTANCE"
        if not quality or not (sweep and rejection or acceptance):
            return False, ("E4_LIQUIDITY_EVIDENCE_INSUFFICIENT",)
        return True, ()

    if engine_id == "E5":
        if state("5D") == "EXTENDED" or state("5E") != "SPACE_AVAILABLE":
            return False, ("E5_LOCATION_DISADVANTAGED",)
        if state("5F") != "LOCATION_QUALITY_MEASURABLE":
            return False, ("E5_LOCATION_UNCONFIRMED",)
        return True, ()

    if engine_id == "E6":
        if state("6D") != "NOT_INVALIDATED" or state("6F") not in {"MATURE"}:
            return False, ("E6_SETUP_NOT_MATURE",)
        if state("6B") != "DIRECTIONAL_SETUP":
            return False, ("E6_SETUP_NOT_DIRECTIONAL",)
        return True, ()

    if engine_id == "E7":
        if state("7F") != "CONFIRMATION_PASS":
            return False, ("E7_CONFIRMATION_INSUFFICIENT",)
        if state("7A") != "TRIGGER_OBSERVED" or state("7B") != "QUALITY_PASS":
            return False, ("E7_TRIGGER_NOT_CONFIRMED",)
        if state("7D") != "NO_FAILURE":
            return False, ("E7_CONFIRMATION_INVALIDATED",)
        return True, ()

    if engine_id == "E8":
        plan = output.get("trade_plan", {})
        if not plan.get("valid"):
            return False, ("E8_RISK_PLAN_INVALID",)
        if state("8G") != "RISK_GATE_READY":
            return False, ("E8_RISK_GATE_NOT_READY",)
        if float(plan.get("rr_tp2", 0)) < 2.0:
            return False, ("E8_RR_BELOW_MINIMUM",)
        return True, ()

    return True, ()


def _trade_plan(context: dict[str, Any], direction: str) -> dict[str, Any]:
    bars = context.get("bars") or []
    if len(bars) < 15 or direction not in {"UP", "DOWN"}:
        return {"valid": False, "reason": "INSUFFICIENT_RISK_DATA"}

    recent = bars[-15:]
    entry = float(recent[-1]["close"])
    true_ranges = []
    previous_close = None
    for bar in recent:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        tr = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(tr)
        previous_close = close
    atr = sum(true_ranges) / len(true_ranges)
    if atr <= 0:
        return {"valid": False, "reason": "INVALID_ATR"}

    buffer = max(atr * 0.25, entry * 0.0002)
    risk_distance = atr * 1.5
    if direction == "UP":
        structural_stop = min(float(b["low"]) for b in recent) - buffer
        stop = min(entry - risk_distance, structural_stop)
        risk = entry - stop
        tp1 = entry + risk
        tp2 = entry + 2.0 * risk
    else:
        structural_stop = max(float(b["high"]) for b in recent) + buffer
        stop = max(entry + risk_distance, structural_stop)
        risk = stop - entry
        tp1 = entry - risk
        tp2 = entry - 2.0 * risk

    return {
        "valid": risk > 0 and tp2 > 0,
        "direction": "BUY" if direction == "UP" else "SELL",
        "entry": round(entry, 8),
        "stop_loss": round(stop, 8),
        "take_profit_1": round(tp1, 8),
        "take_profit_2": round(tp2, 8),
        "risk_distance": round(risk, 8),
        "atr": round(atr, 8),
        "rr_tp1": 1.0,
        "rr_tp2": 2.0,
    }


def run_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    results = []
    for code in SUB_ENGINE_CODES[engine_id]:
        result = _module(code).SubEngine().run(context)
        results.append(result)
        if not result.gate_passed:
            return EngineResult(engine_id, ENGINE_NAMES[engine_id], False, result.score,
                                {"sub_engine": code, "output": result.output, "trace": result.trace},
                                tuple(result.trace.get("reason_codes", [])))

    score = mean(r.score for r in results)
    output = {r.sub_engine_id: r.output for r in results}

    if engine_id == "E8":
        trend = context.get("E1_result", {}).get("1C", {}).get("direction", "NEUTRAL")
        plan = _trade_plan(context, trend)
        output["trade_plan"] = plan
        if not plan.get("valid"):
            return EngineResult(engine_id, ENGINE_NAMES[engine_id], False, score, output, (plan.get("reason", "RISK_PLAN_INVALID"),))

    gate_passed, reasons = _professional_gate(engine_id, output, context)
    output["professional_gate"] = "PASS" if gate_passed else "FAIL"
    output["professional_reason_codes"] = list(reasons)
    return EngineResult(engine_id, ENGINE_NAMES[engine_id], gate_passed, score, output, reasons)


def run_e9_decision(context: dict[str, Any], upstream: list[EngineResult]) -> EngineResult:
    sub = run_engine("E9", context)
    if not all(e.gate_passed for e in upstream):
        return EngineResult("E9", ENGINE_NAMES["E9"], False, sub.score,
                            {"decision": "NO_TRADE", "blocked_by": [e.engine_id for e in upstream if not e.gate_passed]},
                            ("UPSTREAM_GATE_FAILED",))

    e1 = next(e for e in upstream if e.engine_id == "E1")
    e8 = next(e for e in upstream if e.engine_id == "E8")
    trend = e1.output.get("1C", {}).get("direction", "NEUTRAL")
    plan = e8.output.get("trade_plan", {})
    decision = plan.get("direction", "NO_TRADE") if plan.get("valid") else "NO_TRADE"
    final_gate = sub.gate_passed and decision in {"BUY", "SELL"}
    output = {
        "decision": decision if final_gate else "NO_TRADE",
        "decision_authority": "E9",
        "pipeline": "E1>E2>E3>E4>E5>E6>E7>E8>E9",
        "trade_plan": plan,
        "upstream_direction": trend,
        "gate_passed": final_gate,
    }
    return EngineResult("E9", ENGINE_NAMES["E9"], final_gate, sub.score,
                        output, tuple(sub.reason_codes) if final_gate else tuple(sub.reason_codes) + ("FINAL_EXECUTION_GATE_FAILED",))
