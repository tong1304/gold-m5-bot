from production_v2.e1_professional_core_v14 import select_dominant_direction_v15


def test_strong_counter_structure_blocks_ema_only_override():
    result = select_dominant_direction_v15(
        structure_direction="UP",
        structure_quality=0.80,
        structural_persistence=True,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        ema_relation="DOWN",
        ema_gap=-1.50,
    )

    assert result["direction"] == "UP"
    assert result["basis"] == "STRUCTURE_FIRST_COUNTER_HORIZON"
    assert result["blocked_override"] is True


def test_weak_structure_allows_persistent_long_horizon_direction():
    result = select_dominant_direction_v15(
        structure_direction="UP",
        structure_quality=0.40,
        structural_persistence=False,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        ema_relation="DOWN",
        ema_gap=-1.50,
    )

    assert result["direction"] == "DOWN"
    assert result["basis"] == "LONG_HORIZON_EMA_ALIGNMENT"
    assert result["blocked_override"] is False
