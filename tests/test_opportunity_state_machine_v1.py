import pytest

from production_v2.opportunity_state_machine import can_transition, transition


def test_professional_progression_is_valid():
    stages = ["WATCH", "THESIS", "CONFIRMING", "ACTIONABLE", "TRADE"]
    assert all(can_transition(a, b) for a, b in zip(stages, stages[1:]))


def test_waiting_stage_does_not_equal_invalidation():
    assert can_transition("CONFIRMING", "CONFIRMING")
    assert not can_transition("CONFIRMING", "INVALIDATED") is False


def test_terminal_paths_are_explicit():
    assert can_transition("WATCH", "EXPIRED")
    assert can_transition("ACTIONABLE", "TOO_LATE")
    assert transition("ACTIONABLE", "TOO_LATE") == "TOO_LATE"


def test_invalid_backward_trade_transition_is_rejected():
    with pytest.raises(ValueError):
        transition("TRADE", "WATCH")
