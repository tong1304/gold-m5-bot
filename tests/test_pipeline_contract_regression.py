import pytest

from production_v2.contracts import DecisionResult, EngineResult
from production_v2.pipeline import _build_decision_result, _finalize_e9_authority


def test_finalize_e9_authority_consumes_engine_result_and_preserves_output():
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
    audit = {"hard_veto": False, "hard_vetoes": []}

    result = _finalize_e9_authority(e9, audit)

    assert isinstance(result, EngineResult)
    assert result.output["decision"] == "BUY"
    assert result.output["decision_authorized"] is True
    assert result.output["decision_authority"] == "E9"
    assert result.output["governance_reasons"] == []


def test_build_decision_result_matches_public_contract():
    engines = {
        "E1": EngineResult("E1", "Market State Brain", True, 80.0, {}),
        "E9": EngineResult("E9", "Master Decision Brain", True, 90.0, {"decision": "BUY", "trade_plan": {"entry": 1}}),
    }

    result = _build_decision_result(
        symbol="XAUUSD",
        timeframe="M5",
        decision="BUY",
        gate_passed=True,
        score=90.0,
        engines=engines,
    )

    assert isinstance(result, DecisionResult)
    assert result.symbol == "XAUUSD"
    assert result.timeframe == "M5"
    assert result.decision == "BUY"
    assert result.gate_passed is True
    assert result.score == 90.0
    assert result.engines == tuple(engines.values())
    assert result.risk["trade_plan"] == {"entry": 1}


def test_finalize_e9_authority_hard_veto_forces_no_trade():
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

    result = _finalize_e9_authority(e9, {"hard_veto": True, "hard_vetoes": ["E8_RISK_INVALIDATED"]})

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["decision_authorized"] is False
    assert "NINE_BRAIN_FATAL_VETO" in result.output["governance_reasons"]
