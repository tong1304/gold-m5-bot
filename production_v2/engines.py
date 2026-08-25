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
    return EngineResult(engine_id, ENGINE_NAMES[engine_id], True, score, output, ())


def run_e9_decision(context: dict[str, Any], upstream: list[EngineResult]) -> EngineResult:
    sub = run_engine("E9", context)
    if not all(e.gate_passed for e in upstream):
        return EngineResult("E9", ENGINE_NAMES["E9"], False, sub.score,
                            {"decision": "NO_TRADE", "blocked_by": [e.engine_id for e in upstream if not e.gate_passed]},
                            ("UPSTREAM_GATE_FAILED",))

    trend = next((e.output.get("1C", {}).get("direction") for e in upstream if e.engine_id == "E1"), "NEUTRAL")
    decision = trend if trend in {"UP", "DOWN"} else "NO_TRADE"
    decision = {"UP": "BUY", "DOWN": "SELL"}.get(decision, "NO_TRADE")
    return EngineResult("E9", ENGINE_NAMES["E9"], sub.gate_passed, sub.score,
                        {"decision": decision, "decision_authority": "E9", "pipeline": "E1>E2>E3>E4>E5>E6>E7>E8>E9"},
                        tuple(sub.reason_codes))
