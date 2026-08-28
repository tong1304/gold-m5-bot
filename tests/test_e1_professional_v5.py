import pytest

from production_v2.e1_professional_layer_v5 import (
    classify_recent_pressure,
    arbitrate_transition,
)


def test_single_counter_candle_is_pullback_not_reversal():
    result = classify_recent_pressure(
        trend_direction="DOWN",
        recent_directions=["DOWN", "DOWN", "UP"],
        protected_level=101.0,
        recent_closes=[99.0, 98.0, 99.0],
        atr=2.0,
    )
    assert result["classification"] == "PULLBACK_WITHIN_TREND"
    assert result["trend_integrity"] == "INTACT"


def test_persistent_counter_pressure_without_structure_break_is_still_pullback():
    result = classify_recent_pressure(
        trend_direction="DOWN",
        recent_directions=["UP", "UP", "UP", "UP", "UP"],
        protected_level=101.0,
        recent_closes=[99.0, 99.5, 100.0, 100.2, 100.5],
        atr=2.0,
    )
    assert result["classification"] == "COUNTER_PRESSURE_THREAT"
    assert result["trend_integrity"] == "INTACT"


def test_transition_requires_structural_acceptance_and_persistent_counter_pressure():
    result = arbitrate_transition(
        prior_direction="DOWN",
        current_direction="UP",
        prior_state="TREND_DOWN",
        candidate=True,
        acceptance_confirmed=True,
        persistence_score=0.60,
        protected_level=101.0,
        recent_closes=[102.0, 103.0, 104.0],
        atr=2.0,
    )
    assert result["status"] == "COMMITTED"


def test_direction_flip_without_acceptance_stays_watch():
    result = arbitrate_transition(
        prior_direction="DOWN",
        current_direction="UP",
        prior_state="TREND_DOWN",
        candidate=True,
        acceptance_confirmed=False,
        persistence_score=0.90,
        protected_level=101.0,
        recent_closes=[99.0, 100.0, 100.5],
        atr=2.0,
    )
    assert result["status"] == "WATCH"
