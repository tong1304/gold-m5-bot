from v11.regime import allowed_engines_for_regime
from v11.risk import MIN_RISK_REWARD
from v11.strategy_engine import _e5_momentum_ok, _e3_breakout_ok


def test_v121_regime_engine_mapping_is_exact():
    assert allowed_engines_for_regime("TREND") == {"E1", "E2", "E5"}
    assert allowed_engines_for_regime("TRANSITION") == {"E3", "E4"}
    assert allowed_engines_for_regime("RANGE") == {"E6", "E7", "E8"}


def test_v121_rr_floor_is_one_point_five():
    assert MIN_RISK_REWARD == 1.5


def test_e5_requires_at_least_2_5_atr_body_and_150_percent_volume():
    assert not _e5_momentum_ok(body_atr=2.49, volume_ratio=1.50, marubozu=True)
    assert not _e5_momentum_ok(body_atr=2.50, volume_ratio=1.49, marubozu=True)
    assert _e5_momentum_ok(body_atr=2.50, volume_ratio=1.50, marubozu=True)


def test_e3_requires_1_8_volume_expansion():
    assert not _e3_breakout_ok(close_break=True, volume_ratio=1.79)
    assert _e3_breakout_ok(close_break=True, volume_ratio=1.80)
    assert not _e3_breakout_ok(close_break=False, volume_ratio=2.00)
