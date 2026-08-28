from production_v2.e1_professional_core_v18 import select_dominant_regime_v18


def test_conflicting_long_horizon_does_not_flip_persistent_structure_without_repricing():
    out = select_dominant_regime_v18(
        structure_direction="UP",
        structure_quality=0.90,
        structural_persistence=True,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        pressure_direction="DOWN",
        ema_relation="UP",
        transition_confirmed=False,
    )
    assert out["market_state"] == "TREND_UP"
    assert out["dominant_direction"] == "UP"
    assert out["transition"] == "WATCH"
    assert out["trend_confirmed"] is True
    assert "STRUCTURE_VS_LONG_HORIZON_CONFLICT" in out["reasons"]


def test_confirmed_structural_repricing_allows_transition():
    out = select_dominant_regime_v18(
        structure_direction="UP",
        structure_quality=0.90,
        structural_persistence=True,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        pressure_direction="DOWN",
        ema_relation="DOWN",
        transition_confirmed=True,
    )
    assert out["market_state"] == "TRANSITION"
    assert out["dominant_direction"] == "NEUTRAL"
    assert out["transition"] == "CONFIRMED"
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
        transition_confirmed=False,
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
        transition_confirmed=False,
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
        transition_confirmed=False,
    )
    assert out["market_state"] == "TREND_DOWN"
    assert out["dominant_direction"] == "DOWN"
    assert out["transition"] == "WATCH"
    assert out["trend_confirmed"] is True
    assert "COUNTER_PRESSURE" in out["reasons"]
