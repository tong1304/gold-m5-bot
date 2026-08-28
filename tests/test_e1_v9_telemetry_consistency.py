from production_v2.e1_professional_layer_v9 import normalize_e1_telemetry


def test_v9_telemetry_uses_authoritative_e1_state_not_stale_reasoning_fields():
    output = {
        "market_state": "TREND_DOWN",
        "trend_state": "DOWN",
        "directional_pressure": "DOWN",
        "current_pressure": "BULLISH",
        "transition": "ABSENT",
        "structure_state": "BEARISH",
        "volatility_state": "NORMAL",
        "professional_reasoning": {
            "market_state": "TREND_DOWN",
            "trend_state": "NONE",
            "directional_pressure": "DOWN",
            "structure_state": "BULLISH",
            "volatility_state": "EXPANDING",
        },
    }

    normalized = normalize_e1_telemetry(output)

    assert normalized["market_state"] == "TREND_DOWN"
    assert normalized["trend_state"] == "DOWN"
    assert normalized["directional_pressure"] == "DOWN"
    assert normalized["structure_state"] == "BEARISH"
    assert normalized["volatility_state"] == "NORMAL"
    assert normalized["current_pressure"] == "BULLISH"


def test_v9_telemetry_keeps_pullback_distinct_from_regime_direction():
    output = {
        "market_state": "TREND_DOWN",
        "trend_state": "DOWN",
        "directional_pressure": "DOWN",
        "current_pressure": "BULLISH",
        "counter_pressure": "PULLBACK_WITHIN_TREND",
        "market_phase": "PULLBACK",
        "transition": "ABSENT",
        "professional_reasoning": {},
    }

    normalized = normalize_e1_telemetry(output)

    assert normalized["trend_state"] == "DOWN"
    assert normalized["directional_pressure"] == "DOWN"
    assert normalized["current_pressure"] == "BULLISH"
    assert normalized["counter_pressure"] == "PULLBACK_WITHIN_TREND"
    assert normalized["market_phase"] == "PULLBACK"
