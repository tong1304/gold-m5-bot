from production_v2.contracts import DecisionResult, EngineResult
from production_v2.signal_boundary import is_actionable_signal


def _result(decision="BUY", gate_passed=True, e9_decision=None):
    e9_decision = e9_decision or decision
    e9 = EngineResult(
        engine_id="E9",
        name="MASTER",
        gate_passed=gate_passed,
        score=80.0 if gate_passed else 20.0,
        output={"decision": e9_decision},
        reason_codes=("READY",) if gate_passed else ("NOT_READY",),
    )
    return DecisionResult(
        engines=(e9,),
        decision=decision,
        state="SIGNAL_READY" if gate_passed else "ANALYSIS_COMPLETE_NO_TRADE",
    )


def test_only_e9_authorized_buy_sell_are_actionable_notifications():
    assert is_actionable_signal(_result("BUY"))
    assert is_actionable_signal(_result("SELL"))


def test_no_trade_is_never_an_actionable_notification():
    assert not is_actionable_signal(_result("NO_TRADE", gate_passed=False))


def test_gate_failure_is_never_an_actionable_notification():
    assert not is_actionable_signal(_result("BUY", gate_passed=False))


def test_result_and_e9_decision_must_agree():
    assert not is_actionable_signal(_result("BUY", e9_decision="SELL"))
