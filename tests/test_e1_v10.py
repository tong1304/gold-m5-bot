from production_v2.e1_professional_layer_v10 import _transition_v10


def test_transition_requires_persistent_opposite_structure():
    result = _transition_v10(
        dominant="DOWN", ema="DOWN", structure="UP",
        structure_recent="UP", structure_lookback="DOWN",
        slope20=0.60, slope40=0.45, gap=0.10, recent="UP", base="TREND_DOWN",
    )
    assert result["status"] == "CANDIDATE"
    assert result["committed"] is False


def test_transition_confirmed_requires_ema_flip_and_persistent_structure():
    result = _transition_v10(
        dominant="DOWN", ema="UP", structure="UP",
        structure_recent="UP", structure_lookback="UP",
        slope20=0.60, slope40=0.45, gap=0.80, recent="UP", base="TREND_DOWN",
    )
    assert result["status"] == "CONFIRMED"
    assert result["committed"] is True


def test_counter_pressure_does_not_become_transition_when_structure_is_old_regime():
    result = _transition_v10(
        dominant="DOWN", ema="DOWN", structure="DOWN",
        structure_recent="NEUTRAL", structure_lookback="DOWN",
        slope20=0.90, slope40=-0.10, gap=-0.80, recent="UP", base="TREND_DOWN",
    )
    assert result["status"] == "COUNTER_PRESSURE"
    assert result["committed"] is False
