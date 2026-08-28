from production_v2.e4_brain import analyze_e4


def _bars(values):
    return [{"open": v - 0.2, "high": v + 0.5, "low": v - 0.5, "close": v, "closed": True} for v in values]


def test_e4_professional_contract_exposes_auditable_auction_state():
    result = analyze_e4({"bars": _bars([100 + i * 0.05 for i in range(60)])})
    assert "auction_quality" in result
    assert "professional_reasoning" in result
    assert "audit" in result
    assert result["professional_reasoning"]["actor_identification"] == "INFERENCE_FROM_OHLC_ONLY"
    assert result["audit"]["closed_candle_only"] is True
    assert result["audit"]["no_lookahead"] is True


def test_e4_professional_contract_preserves_analysis_only_boundary():
    result = analyze_e4({"bars": _bars([100 + i * 0.05 for i in range(60)])})
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["decision_authority"] == "E9_ONLY"
    assert result["trade_decision_authority"] is False


def test_e4_true_acceptance_is_not_confirmed_by_the_event_candle_alone():
    result = analyze_e4({"bars": _bars([100 + i * 0.05 for i in range(60)])})
    assert result["direction_confirmed"] is False or result["auction_state"] != "ACCEPTANCE_CONFIRMED"
