from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parents[1]
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


def module_name(code):
    return 'trading_system.engines.' + code[0] + '.' + code.lower().replace('-', '_')


def test_all_58_sub_engines_exist_and_expose_contract():
    assert len(SUB_ENGINE_NAMES) == 58
    for code in SUB_ENGINE_NAMES:
        mod = importlib.import_module(module_name(code))
        assert hasattr(mod, 'SubEngine')
        engine = mod.SubEngine()
        result = engine.run({'symbol': 'TEST', 'timeframe': 'M5', 'bars': []})
        assert result.sub_engine_id == code
        assert result.gate_passed is False
        assert 0 <= result.score <= 100
        assert result.trace['sub_engine_id'] == code


def test_sub_engines_have_no_trade_authority():
    for code in SUB_ENGINE_NAMES:
        mod = importlib.import_module(module_name(code))
        public = [n for n in dir(mod.SubEngine) if not n.startswith('_')]
        forbidden = {'buy', 'sell', 'long', 'short', 'place_order', 'execute_order'}
        assert not forbidden.intersection({n.lower() for n in public})
