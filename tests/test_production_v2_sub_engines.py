from pathlib import Path
import importlib

SUB_ENGINE_NAMES = [
    '1A_DATA_QUALITY','1B_VOLATILITY_STATE','1C_TREND_STATE','1D_RANGE_STATE','1E_COMPRESSION','1F_EXPANSION','1G_TRANSITION',
    '2A_TREND_REGIME','2B_RANGE_REGIME','2C_MEAN_REVERSION_BEHAVIOR','2D_BREAKOUT_REGIME','2E_REGIME_PHASE','2F_REGIME_TRANSITION',
    '3A_SWING_DETECTION','3B_STRUCTURE_CLASSIFICATION','3C_BREAK_OF_STRUCTURE','3D_STRUCTURAL_FAILURE','3E_STRUCTURE_STRENGTH','3F_INTERNAL_EXTERNAL_STRUCTURE',
    '4A_LIQUIDITY_ZONE_DETECTION','4B_SWEEP_DETECTION','4C_REACTION_REJECTION','4D_ACCEPTANCE','4E_RECLAIM_FAILED_BREAK','4F_LIQUIDITY_STRENGTH_QUALITY',
    '5A_EQUILIBRIUM_VALUE','5B_STRUCTURAL_LOCATION','5C_LIQUIDITY_LOCATION','5D_EXTENSION','5E_AVAILABLE_SPACE','5F_LOCATION_QUALITY',
    '6A_SETUP_CONTEXT','6B_SETUP_ARCHETYPE','6C_SETUP_FORMATION_STATE_MACHINE','6D_SETUP_INVALIDATION','6E_SETUP_QUALITY','6F_SETUP_MATURITY',
    '7A_TRIGGER_DETECTION','7B_TRIGGER_QUALITY','7C_FOLLOW_THROUGH','7D_FAILURE_INVALIDATION','7E_EXECUTION_CONDITIONS','7F_CONFIRMATION_QUALITY',
    '8A_INVALIDATION_MODEL','8B_STOP_PLACEMENT','8C_TARGET_LIQUIDITY_OBJECTIVE','8D_R_MULTIPLE','8E_POSITION_SIZE','8F_EXPOSURE_LIMITS','8G_RISK_GATE',
    '9A_DATA_GATE','9B_CONTEXT_GATE','9C_SETUP_GATE','9D_CONFIRMATION_GATE','9E_RISK_GATE','9F_EXECUTION_GATE','9G_FINAL_DECISION','9H_DECISION_LOGGING',
]

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


def module_name(code):
    key = code[:2]
    return f"trading_system.engines.e{key[0]}.{SUFFIX[key]}"


def test_all_58_sub_engines_exist_and_expose_contract():
    assert len(SUB_ENGINE_NAMES) == 58
    for code in SUB_ENGINE_NAMES:
        mod = importlib.import_module(module_name(code))
        engine = mod.SubEngine()
        result = engine.run({'symbol': 'TEST', 'timeframe': 'M5', 'bars': [{'open': 1, 'high': 2, 'low': 0.5, 'close': 1.5}]})
        # Engine IDs are canonical two-character IDs (1A..9H), while
        # SUB_ENGINE_NAMES are human-readable names used to resolve modules.
        assert result.sub_engine_id == code[:2]
        assert result.gate_passed is True
        assert 0 <= result.score <= 100
        assert result.trace['sub_engine_id'] == code[:2]


def test_invalid_input_fails_closed():
    mod = importlib.import_module(module_name('1A'))
    result = mod.SubEngine().run({'symbol': 'TEST', 'timeframe': 'M5', 'bars': []})
    assert result.gate_passed is False
    assert 'INVALID_OR_MISSING_INPUT' in result.trace['reason_codes']


def test_sub_engines_have_no_order_api():
    for code in SUB_ENGINE_NAMES:
        mod = importlib.import_module(module_name(code))
        public = {n.lower() for n in dir(mod.SubEngine) if not n.startswith('_')}
        assert not public.intersection({'buy', 'sell', 'long', 'short', 'place_order', 'execute_order'})
