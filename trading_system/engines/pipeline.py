from __future__ import annotations

from importlib import import_module
from typing import Any

SUB_ENGINE_CODES=['1A','1B','1C','1D','1E','1F','1G','2A','2B','2C','2D','2E','2F','3A','3B','3C','3D','3E','3F','4A','4B','4C','4D','4E','4F','5A','5B','5C','5D','5E','5F','6A','6B','6C','6D','6E','6F','7A','7B','7C','7D','7E','7F','8A','8B','8C','8D','8E','8F','8G','9A','9B','9C','9D','9E','9F','9G','9H']
SUFFIX={'1A':'a_data_quality','1B':'b_volatility_state','1C':'c_trend_state','1D':'d_range_state','1E':'e_compression','1F':'f_expansion','1G':'g_transition','2A':'a_trend_regime','2B':'b_range_regime','2C':'c_mean_reversion_behavior','2D':'d_breakout_regime','2E':'e_regime_phase','2F':'f_regime_transition','3A':'a_swing_detection','3B':'b_structure_classification','3C':'c_break_of_structure','3D':'d_structural_failure','3E':'e_structure_strength','3F':'f_internal_external_structure','4A':'a_liquidity_zone_detection','4B':'b_sweep_detection','4C':'c_reaction_rejection','4D':'d_acceptance','4E':'e_reclaim_failed_break','4F':'f_liquidity_strength_quality','5A':'a_equilibrium_value','5B':'b_structural_location','5C':'c_liquidity_location','5D':'d_extension','5E':'e_available_space','5F':'f_location_quality','6A':'a_setup_context','6B':'b_setup_archetype','6C':'c_setup_formation_state_machine','6D':'d_setup_invalidation','6E':'e_setup_quality','6F':'f_setup_maturity','7A':'a_trigger_detection','7B':'b_trigger_quality','7C':'c_follow_through','7D':'d_failure_invalidation','7E':'e_execution_conditions','7F':'f_confirmation_quality','8A':'a_invalidation_model','8B':'b_stop_placement','8C':'c_target_liquidity_objective','8D':'d_r_multiple','8E':'e_position_size','8F':'f_exposure_limits','8G':'g_risk_gate','9A':'a_data_gate','9B':'b_context_gate','9C':'c_setup_gate','9D':'d_confirmation_gate','9E':'e_risk_gate','9F':'f_execution_gate','9G':'g_final_decision','9H':'h_decision_logging'}

def _module_for(code:str)->str:return f'trading_system.engines.e{code[0]}.{SUFFIX[code]}'

def run_all(data:dict[str,Any])->dict[str,Any]:
    results={}; context=dict(data)
    engine_groups=[SUB_ENGINE_CODES[i:i+n] for i,n in ((0,7),(7,6),(13,6),(19,6),(25,6),(31,6),(37,6),(43,7),(50,8))]
    for group in engine_groups:
        engine_id=group[0][0]; local={}
        for code in group:
            result=import_module(_module_for(code)).SubEngine().run(context)
            results[code]=result; local[code]=result.output
        context[f'E{engine_id}_result']=local
    return results
