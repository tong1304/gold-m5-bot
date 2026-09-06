import pytest

from .order_execution_boundary import ExecutionBoundaryError, advance_execution_state, initial_execution_state


def test_only_gated_e9_trade_creates_order_intent():
    assert initial_execution_state({"decision": "BUY", "gate_passed": False})["state"] == "NONE"
    intent = initial_execution_state({"decision": "BUY", "gate_passed": True})
    assert intent["state"] == "ORDER_INTENT"
    assert intent["authorized_by"] == "E9"


def test_order_intent_cannot_become_position_open_without_external_ack():
    intent = initial_execution_state({"decision": "SELL", "gate_passed": True})
    with pytest.raises(ExecutionBoundaryError):
        advance_execution_state(intent, "POSITION_OPEN")


def test_execution_requires_explicit_monotonic_acknowledgements():
    state = initial_execution_state({"decision": "BUY", "gate_passed": True})
    state = advance_execution_state(state, "ORDER_SUBMITTED")
    state = advance_execution_state(state, "BROKER_ACCEPTED")
    state = advance_execution_state(state, "POSITION_OPEN")
    assert state["state"] == "POSITION_OPEN"
    assert state["history"] == ["ORDER_INTENT", "ORDER_SUBMITTED", "BROKER_ACCEPTED", "POSITION_OPEN"]


def test_non_monotonic_execution_transition_is_rejected():
    state = initial_execution_state({"decision": "BUY", "gate_passed": True})
    with pytest.raises(ExecutionBoundaryError):
        advance_execution_state(state, "BROKER_ACCEPTED")
