from production_v2.professional_e4_brain_v15 import analyze_e4


def _bars(values):
    return [{"open": v - 0.2, "high": v + 0.5, "low": v - 0.5, "close": v} for v in values]


def test_e4_professional_contract_exposes_auction_quality_and_competing_readings():
    result = analyze_e4({"bars": _bars([100 + i * 0.05 for i in range(60)])})
    assert "auction_quality" in result
    assert "event_quality" in result
    assert "post_event_displacement" in result
    assert "competing_interpretations" in result
    assert "liquidity_taker_confidence" in result
    assert "professional_reasoning" in result


def test_e4_professional_contract_preserves_analysis_only_boundary():
    result = analyze_e4({"bars": _bars([100 + i * 0.05 for i in range(60)])})
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["decision_authority"] == "E9_ONLY"
    assert result["trade_decision_authority"] is False
