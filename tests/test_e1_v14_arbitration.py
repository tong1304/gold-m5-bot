from production_v2.e1_professional_core_v14 import analyze_e1_professional_v14


def candles(values):
    out = []
    for i, close in enumerate(values):
        prev = values[i - 1] if i else close
        out.append({"open": prev, "high": max(close, prev) + 0.5, "low": min(close, prev) - 0.5, "close": close})
    return out


def test_e1_does_not_flip_downtrend_from_short_counter_pressure():
    values = [120 - i * 0.8 for i in range(90)] + [48.0, 48.8, 49.6, 50.4, 51.2, 52.0, 52.8, 53.6, 54.4, 55.2]
    result = analyze_e1_professional_v14(candles(values))
    assert result["dominant_direction"] == "DOWN"
    assert result["market_state"] == "TREND_DOWN"
    assert result["transition_confirmed"] is False
    assert result["transition_committed"] is False
    assert result["counter_evidence"]["direction"] == "UP"


def test_e1_requires_structural_repricing_for_transition():
    values = [120 - i * 0.8 for i in range(100)]
    values[-1] = values[-2] + 3.0
    result = analyze_e1_professional_v14(candles(values))
    assert result["market_state"] == "TREND_DOWN"
    assert result["transition_confirmed"] is False
    assert result["transition_commitment"]["required"] is True
    assert "STRUCTURAL_REPRICING" in result["transition_commitment"]["missing"]


def test_e1_exposes_professional_arbitration_without_trade_authority():
    result = analyze_e1_professional_v14(candles([100 + i * 0.5 for i in range(100)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["professional_reasoning"]["arbitration_order"][:4] == ["DATA_QUALITY", "STRUCTURE", "LONG_HORIZON", "PERSISTENCE"]
    assert result["professional_reasoning"]["primary_thesis"]["direction"] in {"UP", "DOWN", "NEUTRAL"}
