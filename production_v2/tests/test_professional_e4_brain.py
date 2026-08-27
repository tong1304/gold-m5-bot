from production_v2.professional_e4_brain import analyze_e4, PROFESSIONAL_QUESTION, E4_ROLE, EVIDENCE_HIERARCHY


def _bars(n=80, base=100.0):
    bars = []
    for i in range(n):
        close = base + i * 0.2
        bars.append({"open": close - 0.1, "high": close + 0.4, "low": close - 0.4, "close": close})
    return bars


def test_e4_has_same_professional_brain_contract_shape():
    result = analyze_e4(_bars())
    assert PROFESSIONAL_QUESTION == "Where is liquidity, who took it, and did price accept or reject the auction?"
    assert E4_ROLE == "LIQUIDITY_AUCTION_ANALYST"
    assert "DATA_QUALITY" in EVIDENCE_HIERARCHY
    assert result["reasoning_role"] == E4_ROLE
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert "professional_reasoning" in result
    assert "reasoning_trace" in result
    assert "evidence" in result


def test_e4_reports_liquidity_event_without_deciding_trade():
    bars = _bars()
    # Create a recent sweep above a prior swing area and rejection.
    bars[-3]["high"] = bars[-4]["high"] + 2.0
    bars[-3]["close"] = bars[-4]["high"] - 0.2
    bars[-2]["open"] = bars[-3]["close"]
    bars[-2]["high"] = bars[-3]["high"] - 0.2
    bars[-2]["low"] = bars[-2]["close"] - 0.3
    bars[-1]["open"] = bars[-2]["close"]
    bars[-1]["high"] = bars[-2]["high"] + 0.1
    bars[-1]["low"] = bars[-1]["close"] - 0.3

    result = analyze_e4(bars)
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["score"] is None
    assert result["trade_decision_authority"] is False
    assert result["event"]["type"] in {
        "HIGH_SWEEP_REJECTION",
        "HIGH_FAILED_BREAK_RECLAIM",
        "NO_CONFIRMED_LIQUIDITY_EVENT",
    }
