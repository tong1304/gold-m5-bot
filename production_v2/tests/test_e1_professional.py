from production_v2.e1_brain import analyze_e1


def bars_from_closes(closes):
    return [{"open": c, "high": c + 0.5, "low": c - 0.5, "close": c} for c in closes]


def test_e1_never_owns_trade_decision():
    result = analyze_e1(bars_from_closes([100 + i * 0.1 for i in range(100)]))
    assert result["trade_decision_authority"] is False
    assert result["decision_authority"] == "E9_ONLY"
    assert result["professional_reasoning"]["task"] == "DESCRIBE_MARKET_STATE_ONLY"


def test_e1_ema_is_context_not_trade_regime_authority():
    closes = [100 + i * 0.5 for i in range(70)] + [135 - i * 0.35 for i in range(30)]
    result = analyze_e1(bars_from_closes(closes))
    assert "EMA_CONTEXT_DISAGREES_WITH_PRESSURE" in result["professional_reasoning"]["counter_evidence"] or result["directional_pressure"] in {"UP", "DOWN"}
    assert result["professional_reasoning"]["ema_role"] == "CONTEXT_ONLY"


def test_e1_reports_incomplete_data_as_unclear():
    result = analyze_e1(bars_from_closes([100 + i for i in range(20)]))
    assert result["market_state"] == "UNCLEAR"
    assert result["analysis_status"] == "INCOMPLETE"


def test_e1_transition_requires_confirmed_change_not_simple_disagreement():
    closes = [100 + i * 0.1 for i in range(100)]
    result = analyze_e1(bars_from_closes(closes))
    assert result["transition"] == "ABSENT"
    assert result["market_state"] != "TRANSITION"


def test_e1_exposes_evidence_hierarchy_and_ownership():
    result = analyze_e1(bars_from_closes([100 + i * 0.2 for i in range(100)]))
    assert "STRUCTURE" in result["professional_reasoning"]["evidence_hierarchy"]
    assert "trade_execution" in result["professional_reasoning"]["ownership_boundaries"]["does_not_own"]
