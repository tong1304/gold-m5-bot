from production_v2.contracts import DecisionResult, EngineResult
from production_v2.professional_governance import enforce_final_authority


def test_enforce_final_authority_accepts_engine_result_and_returns_engine_result():
    e9 = EngineResult(
        "E9",
        "Master Decision Brain",
        True,
        92.0,
        {
            "decision": "BUY",
            "mandatory_gates": {
                "core_thesis": True,
                "closed_candle_trigger": True,
                "survivable_economics": True,
                "fatal_veto_clear": True,
            },
            "all_gates_pass": True,
        },
        (),
    )

    result = enforce_final_authority(e9, {"hard_veto": False, "hard_vetoes": []})

    assert isinstance(result, EngineResult)
    assert result.output["decision"] == "BUY"
    assert result.output["decision_authorized"] is True
    assert result.output["decision_authority"] == "E9"
    assert result.output["governance_reasons"] == []


def test_enforce_final_authority_hard_veto_forces_no_trade():
    e9 = EngineResult(
        "E9", "Master Decision Brain", True, 95.0,
        {
            "decision": "SELL",
            "mandatory_gates": {
                "core_thesis": True,
                "closed_candle_trigger": True,
                "survivable_economics": True,
                "fatal_veto_clear": True,
            },
            "all_gates_pass": True,
        },
    )

    result = enforce_final_authority(e9, {"hard_veto": True, "hard_vetoes": ["E8_RISK_INVALIDATED"]})

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["decision_authorized"] is False
    assert "NINE_BRAIN_FATAL_VETO" in result.output["governance_reasons"]


def test_decision_result_normalizes_pipeline_legacy_constructor_shape():
    engines = {
        "E1": EngineResult("E1", "Market State Brain", True, 80.0, {}),
        "E9": EngineResult("E9", "Master Decision Brain", True, 90.0, {"decision": "BUY", "trade_plan": {"entry": 1}}),
    }

    result = DecisionResult(
        decision="BUY",
        state="SIGNAL_READY",
        engines=engines,
        blocked_by=None,
        wait_bars=0,
    )

    assert isinstance(result, DecisionResult)
    assert result.decision == "BUY"
    assert result.gate_passed is True
    assert result.score == 90.0
    assert result.engines == tuple(engines.values())
    assert result.risk["trade_plan"] == {"entry": 1}
    assert result.state == "SIGNAL_READY"
