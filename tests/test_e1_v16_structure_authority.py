"""E1 V16 regression tests: weak/mixed current structure must not be promoted by horizon/EMA context."""

from production_v2.e1_professional_core_v15 import select_dominant_direction_v15


def test_e1_does_not_call_mixed_structure_a_trend_from_long_horizon_ema_context():
    out = select_dominant_direction_v15(
        structure_direction="NEUTRAL",
        structure_quality=0.30,
        structural_persistence=False,
        long_direction="DOWN",
        long_consensus=1.0,
        long_persistence=1.0,
        ema_relation="DOWN",
        ema_gap=-1.0,
    )

    assert out["direction"] == "NEUTRAL"
    assert out["basis"] == "NO_DOMINANT_REGIME"
    assert out["blocked_override"] is False


def test_e1_strong_current_structure_remains_authoritative_against_horizon_context():
    out = select_dominant_direction_v15(
        structure_direction="DOWN",
        structure_quality=0.76,
        structural_persistence=True,
        long_direction="UP",
        long_consensus=1.0,
        long_persistence=1.0,
        ema_relation="UP",
        ema_gap=1.0,
    )

    assert out["direction"] == "DOWN"
    assert out["basis"] == "STRUCTURE_FIRST_COUNTER_HORIZON"
    assert out["blocked_override"] is True
