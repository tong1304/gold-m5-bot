from production_v2.e1_brain import _hierarchical_state


def test_structure_has_authority_over_short_term_pressure():
    result = _hierarchical_state(
        pressure="UP",
        structure_direction="DOWN",
        structure_quality=1.0,
        consensus=0.75,
        persistence=0.75,
        ema_relation="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        context_flip=False,
        structure_break=False,
    )
    assert result["state"] == "TREND_DOWN"
    assert result["direction"] == "DOWN"
    assert "STRUCTURE_DISAGREES_WITH_PRESSURE" in result["counter_evidence"]


def test_mixed_structure_cannot_be_promoted_to_confirmed_trend():
    result = _hierarchical_state(
        pressure="DOWN",
        structure_direction="NEUTRAL",
        structure_quality=0.30,
        consensus=1.0,
        persistence=1.0,
        ema_relation="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        context_flip=False,
        structure_break=False,
    )
    assert result["state"] == "UNCLEAR"
    assert result["direction"] == "DOWN"
    assert result["directional_state"] == "DEVELOPING"


def test_ema_lag_alone_cannot_create_transition():
    result = _hierarchical_state(
        pressure="DOWN",
        structure_direction="DOWN",
        structure_quality=1.0,
        consensus=1.0,
        persistence=1.0,
        ema_relation="UP",
        long_consensus=1.0,
        long_persistence=1.0,
        context_flip=False,
        structure_break=False,
    )
    assert result["state"] == "TREND_DOWN"
    assert result["transition"] is False


def test_transition_requires_structural_repricing_against_established_context():
    result = _hierarchical_state(
        pressure="UP",
        structure_direction="DOWN",
        structure_quality=1.0,
        consensus=1.0,
        persistence=1.0,
        ema_relation="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        context_flip=True,
        structure_break=True,
    )
    assert result["state"] == "TRANSITION"
    assert result["transition"] is True


def test_single_counter_candle_does_not_change_market_state():
    result = _hierarchical_state(
        pressure="DOWN",
        structure_direction="DOWN",
        structure_quality=1.0,
        consensus=1.0,
        persistence=1.0,
        ema_relation="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        context_flip=False,
        structure_break=False,
        single_counter_candle=True,
    )
    assert result["state"] == "TREND_DOWN"
    assert result["transition"] is False
