from production_v2.contracts import EngineResult
from production_v2.pipeline import _sanitize_specialist_result


def test_e1_direction_is_preserved_as_analytical_evidence():
    result = EngineResult(
        "E1",
        "Market State Brain",
        None,
        80.0,
        {
            "market_state": "TREND_DOWN",
            "direction": "DOWN",
            "directional_pressure": "BEARISH",
            "professional_reasoning": {
                "direction": "DOWN",
                "thesis": "Persistent bearish pressure with mixed structure.",
            },
            "decision": None,
            "gate": None,
        },
        (),
    )

    sanitized = _sanitize_specialist_result(result)
    output = sanitized.output

    assert output["market_state"] == "TREND_DOWN"
    assert output["direction"] == "DOWN"
    assert output["directional_pressure"] == "BEARISH"
    assert output["professional_reasoning"]["direction"] == "DOWN"
    assert "decision" not in output
    assert "gate" not in output


def test_execution_words_are_not_forwarded_as_trade_decisions():
    result = EngineResult(
        "E1",
        "Market State Brain",
        None,
        80.0,
        {
            "direction": "UP",
            "thesis": "Directional pressure is UP; no BUY/SELL decision is made by E1.",
        },
        (),
    )

    output = _sanitize_specialist_result(result).output
    assert output["direction"] == "UP"
    assert "BUY" not in output["thesis"]
    assert "SELL" not in output["thesis"]
    assert "UP" in output["thesis"]
