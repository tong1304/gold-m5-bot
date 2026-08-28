from production_v2.e1_professional_core_v18 import select_dominant_regime_v18


def test_conflicting_persistent_long_horizon_blocks_structural_trend():
    out = select_dominant_regime_v18(
        structure_direction="UP",
        structure_quality=0.90,
        structural_persistence=True,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        pressure_direction="DOWN",
        ema_relation="UP",
    )
    assert out["market_state"] == "TRANSITION"
    assert out["dominant_direction"] == "NEUTRAL"
    assert out["transition"] == "WATCH"
    assert out["trend_confirmed"] is False


def test_convergent_structure_and_horizon_promotes_trend():
    out = select_dominant_regime_v18(
        structure_direction="DOWN",
        structure_quality=0.90,
        structural_persistence=True,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        pressure_direction="DOWN",
        ema_relation="DOWN",
    )
    assert out["market_state"] == "TREND_DOWN"
    assert out["dominant_direction"] == "DOWN"
    assert out["transition"] == "ABSENT"
    assert out["trend_confirmed"] is True


def test_weak_structure_does_not_create_trend():
    out = select_dominant_regime_v18(
        structure_direction="UP",
        structure_quality=0.51,
        structural_persistence=False,
        long_direction="UP",
        long_consensus=1.0,
        long_persistence=1.0,
        pressure_direction="UP",
        ema_relation="UP",
    )
    assert out["market_state"] == "TRANSITION"
    assert out["dominant_direction"] == "NEUTRAL"
    assert out["trend_confirmed"] is False


def test_short_term_counter_pressure_does_not_flip_established_trend():
    out = select_dominant_regime_v18(
        structure_direction="DOWN",
        structure_quality=0.90,
        structural_persistence=True,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        pressure_direction="UP",
        ema_relation="DOWN",
    )
    assert out["market_state"] == "TREND_DOWN"
    assert out["dominant_direction"] == "DOWN"
    assert out["transition"] == "WATCH"
    assert out["trend_confirmed"] is True
    assert "COUNTER_PRESSURE" in out["reasons"]
