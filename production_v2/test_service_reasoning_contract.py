from types import SimpleNamespace

from production_v2.service import LiveService


def test_live_service_keeps_reasoning_contract_for_pipeline_traces():
    engine = SimpleNamespace(
        engine_id="E1",
        output={
            "professional_reasoning": {
                "market_state": "TREND_DOWN",
                "volatility_state": "EXPANDING",
                "structure_state": "BEARISH",
                "directional_pressure": "BEARISH",
                "trend_state": "DOWN",
                "transition": "ABSENT",
            },
            "reason_codes": ["TREND_CONFIRMED"],
        },
    )

    reasoning = LiveService._reasoning(engine)

    assert reasoning["role"] == "MARKET_STATE_ANALYST"
    assert "MARKET_STATE=TREND_DOWN" in reasoning["conclusion"]
    assert "VOLATILITY=EXPANDING" in reasoning["conclusion"]
    assert "TREND_STATE=DOWN" in reasoning["conclusion"]
    assert "TREND_CONFIRMED" in reasoning["reasons"]
