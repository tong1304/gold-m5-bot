from production_v2.e1_brain import analyze_e1


def candles(values):
    out = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        high = max(close, prev) + 0.4
        low = min(close, prev) - 0.4
        out.append({"open": prev, "high": high, "low": low, "close": close})
    return out


def test_e1_exposes_professional_thesis_and_invalidation_without_trade_authority():
    values = [100 + i * 0.7 for i in range(100)]
    result = analyze_e1(candles(values))
    reasoning = result["professional_reasoning"]

    assert result["trade_decision_authority"] is False
    assert reasoning["task"] == "DESCRIBE_MARKET_STATE_ONLY"
    assert reasoning["primary_thesis"]["direction"] in {"UP", "DOWN", "NEUTRAL"}
    assert "supporting_evidence" in reasoning["primary_thesis"]
    assert "counter_evidence" in reasoning["primary_thesis"]
    assert "invalidation" in reasoning
    assert reasoning["invalidation"]["conditions"]


def test_e1_distinguishes_trend_state_from_trade_action():
    values = [120 - i * 0.7 for i in range(100)]
    result = analyze_e1(candles(values))

    assert result["market_state"] in {"TREND_DOWN", "EXPANSION", "UNCLEAR", "TRANSITION"}
    assert "entry" not in result["professional_reasoning"]
    assert "stop_loss" not in result["professional_reasoning"]
    assert "take_profit" not in result["professional_reasoning"]


def test_e1_has_regime_confidence_components_not_just_directional_consensus():
    values = [100 + i * 0.25 for i in range(100)]
    result = analyze_e1(candles(values))
    reasoning = result["professional_reasoning"]

    assert "confidence_model" in reasoning
    assert set(reasoning["confidence_model"]) >= {
        "support",
        "counter_evidence",
        "structure",
        "persistence",
        "stability",
    }
    assert "state_stability" in reasoning
