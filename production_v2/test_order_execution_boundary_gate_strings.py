from .order_execution_boundary import initial_execution_state


def test_string_false_gate_cannot_authorize_order_intent():
    state = initial_execution_state({"decision": "BUY", "gate_passed": "False"})
    assert state["state"] == "NONE"
