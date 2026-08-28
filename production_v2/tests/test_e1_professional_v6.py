from production_v2.e1_professional_layer_v6 import arbitrate_market_state_v6


def test_v6_preserves_dominant_downtrend_during_counter_pressure():
    result = arbitrate_market_state_v6(
        core_state="UNCLEAR",
        core_direction="DOWN",
        ema_direction="DOWN",
        structure_direction="DOWN",
        long_consensus=2 / 3,
        long_persistence=2 / 3,
        structure_alignment=1.0,
        ema_alignment=1.0,
        recent_pressure="UP",
        protected_structure_intact=True,
        transition_status="NONE",
    )

    assert result["market_state"] == "TREND_DOWN"
    assert result["direction"] == "DOWN"
    assert result["trend_maturity"] == "ESTABLISHED"
    assert result["counter_pressure"] == "PULLBACK_WITHIN_TREND"
    assert result["transition"] == "ABSENT"


def test_v6_does_not_promote_mixed_context_to_trend():
    result = arbitrate_market_state_v6(
        core_state="UNCLEAR",
        core_direction="DOWN",
        ema_direction="UP",
        structure_direction="MIXED",
        long_consensus=2 / 3,
        long_persistence=2 / 3,
        structure_alignment=0.48,
        ema_alignment=0.0,
        recent_pressure="DOWN",
        protected_structure_intact=True,
        transition_status="WATCH",
    )

    assert result["market_state"] in {"TRANSITION", "UNCLEAR"}
    assert result["trend_maturity"] != "ESTABLISHED"


def test_v6_committed_transition_requires_real_acceptance():
    result = arbitrate_market_state_v6(
        core_state="TRANSITION",
        core_direction="UP",
        ema_direction="UP",
        structure_direction="UP",
        long_consensus=1.0,
        long_persistence=0.75,
        structure_alignment=1.0,
        ema_alignment=1.0,
        recent_pressure="UP",
        protected_structure_intact=False,
        transition_status="COMMITTED",
    )

    assert result["market_state"] == "TREND_UP"
    assert result["transition"] == "ABSENT"
    assert result["transition_commitment"] is True
