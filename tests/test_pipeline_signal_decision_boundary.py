from production_v2.contracts import DecisionResult, EngineResult


def _e9(decision, gate=True):
    return EngineResult(
        "E9",
        "Master Decision Brain",
        gate,
        90.0,
        {"decision": decision},
        (),
    )


def test_e9_buy_survives_pipeline_decision_boundary():
    result = DecisionResult(decision="NO_TRADE", gate_passed=False, engines=(_e9("BUY"),))
    assert result.decision == "BUY"
    assert result.state == "SIGNAL_READY"


def test_e9_sell_survives_pipeline_decision_boundary():
    result = DecisionResult(decision="NO_TRADE", gate_passed=False, engines=(_e9("SELL"),))
    assert result.decision == "SELL"
    assert result.state == "SIGNAL_READY"


def test_e9_no_trade_remains_no_trade():
    result = DecisionResult(decision="NO_TRADE", gate_passed=False, engines=(_e9("NO_TRADE", False),))
    assert result.decision == "NO_TRADE"


def test_gate_failure_blocks_buy_sell():
    result = DecisionResult(decision="NO_TRADE", gate_passed=False, engines=(_e9("BUY", False),))
    assert result.decision == "NO_TRADE"
