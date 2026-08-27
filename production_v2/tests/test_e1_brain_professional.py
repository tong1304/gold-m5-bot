from production_v2.e1_brain import analyze_e1


def bars(n=120, start=100.0, step=0.20):
    out = []
    price = start
    for i in range(n):
        close = price + step
        out.append({"open": price, "high": close + 0.05, "low": price - 0.03, "close": close})
        price = close
    return out


def test_e1_is_market_state_only():
    result = analyze_e1(bars())
    assert result["reasoning_role"] == "MARKET_STATE_ANALYST"
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert "decision" not in result


def test_e1_exposes_evidence_and_counter_evidence():
    result = analyze_e1(bars())
    assert isinstance(result["evidence"], list)
    assert isinstance(result["conflicts"], list)
    assert "professional_reasoning" in result
    assert "classification_reason" in result["professional_reasoning"]


def test_e1_withholds_state_when_data_is_insufficient():
    result = analyze_e1(bars(20))
    assert result["market_state"] == "UNCLEAR"
    assert result["analysis_status"] == "INCOMPLETE"
    assert result["confidence"] == 0.0


def test_e1_can_identify_compression_without_making_trade_decision():
    data = []
    price = 100.0
    for _ in range(120):
        data.append({"open": price, "high": price + 0.01, "low": price - 0.01, "close": price + 0.001})
    result = analyze_e1(data)
    assert result["trade_decision_authority"] is False
    assert result["market_state"] in {"COMPRESSION", "RANGE", "TRANSITION", "UNCLEAR"}
