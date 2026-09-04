from production_v2.contracts import DecisionResult, EngineResult


def test_legacy_trade_wrapper_is_normalized_to_e9_direction():
    e9 = EngineResult(
        "E9",
        "Master Decision Brain",
        True,
        91.0,
        {"decision": "BUY", "trade_ready": True},
        (),
    )

    result = DecisionResult(decision="TRADE", gate_passed=True, engines={"E9": e9})

    assert result.decision == "BUY"
    assert result.gate_passed is True
    assert result.state == "SIGNAL_READY"


def test_e9_gate_remains_final_authority_at_public_boundary():
    e9 = EngineResult(
        "E9",
        "Master Decision Brain",
        False,
        42.0,
        {"decision": "BUY", "trade_ready": True},
        ("E8_RISK_INVALIDATED",),
    )

    result = DecisionResult(decision="BUY", gate_passed=True, engines={"E9": e9})

    assert result.gate_passed is False
    assert result.decision == "BUY"
    assert result.state == "ANALYSIS_COMPLETE_NO_TRADE"


def test_no_trade_remains_no_trade_when_e9_is_not_actionable():
    e9 = EngineResult(
        "E9",
        "Master Decision Brain",
        False,
        42.0,
        {"decision": "NO_TRADE", "trade_ready": False},
        ("WAITING_FOR_E7_TRIGGER",),
    )

    result = DecisionResult(decision="TRADE", gate_passed=False, engines={"E9": e9})

    assert result.decision == "NO_TRADE"
    assert result.state == "ANALYSIS_COMPLETE_NO_TRADE"
