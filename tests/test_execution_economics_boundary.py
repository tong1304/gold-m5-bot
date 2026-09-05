from production_v2.contracts import DecisionResult, EngineResult
from production_v2.execution_state import authorize_order, is_executed, transition


def _authorized_result():
    e9 = EngineResult(
        engine_id="E9",
        name="MASTER",
        gate_passed=True,
        score=80.0,
        output={"decision": "BUY", "symbol": "XAUUSD", "timeframe": "M5"},
        reason_codes=("READY",),
    )
    return DecisionResult(engines=(e9,), decision="TRADE", state="SIGNAL_READY")


def test_e9_authorization_creates_intent_but_not_execution():
    result = _authorized_result()
    execution = authorize_order(result)
    assert result.decision == "BUY"
    assert execution["state"] == "ORDER_INTENT"
    assert not is_executed(execution)


def test_broker_states_must_be_explicit_before_position_is_executed():
    execution = authorize_order(_authorized_result())
    execution = transition(execution, "ORDER_SUBMITTED", order_id="o-1")
    assert not is_executed(execution)
    execution = transition(execution, "ACCEPTED", order_id="o-1")
    assert not is_executed(execution)
    execution = transition(execution, "POSITION_OPEN", order_id="o-1", position_id="p-1")
    assert is_executed(execution)


def test_no_trade_cannot_create_order_intent():
    e9 = EngineResult(
        engine_id="E9", name="MASTER", gate_passed=False, score=20.0,
        output={"decision": "NO_TRADE"}, reason_codes=("NOT_READY",),
    )
    result = DecisionResult(engines=(e9,), decision="NO_TRADE")
    assert authorize_order(result)["state"] == "NOT_REQUESTED"
