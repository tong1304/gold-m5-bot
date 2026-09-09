from production_v2.e4_brain import analyze_e4


def _bars(values):
    return [{"open": v - 0.2, "high": v + 0.5, "low": v - 0.5, "close": v, "closed": True} for v in values]


def test_e4_is_analysis_only_and_uses_no_upstream_decision_gate_or_score():
    result = analyze_e4(_bars([100 + i * 0.1 for i in range(60)]), {"E1": {"evidence": {"output": {"score": 99, "gate": True, "direction": "UP"}}}})
    assert result["gate"] is None
    assert result["decision"] is None
    assert result["decision_authority"] == "E9_ONLY"
    assert result["evidence"]["decisions_used"] is False
    assert result["evidence"]["gates_used"] is False
    assert result["evidence"]["scores_used"] is False
    assert result["score"] is None


def test_e4_exposes_professional_question_and_confirmation_contract():
    result = analyze_e4(_bars([100 + i * 0.05 for i in range(60)]))
    assert result["question"] == "Where is liquidity, who took it, and did price accept or reject the auction?"
    assert result["reasoning_role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert result["observations"]
    assert "auction_state" in result
    assert "follow_through" in result
    assert "follow_through_bars" in result
    assert "auction_confirmation" in result


def test_e4_context_is_only_a_hint():
    result = analyze_e4(_bars([100 + i * 0.05 for i in range(60)]), {"E1": {"evidence": {"output": {"direction": "BUY", "score": 100, "gate": True}}}})
    assert result["contextual_direction_hint"] == "UP"
    assert result["decision"] is None
    assert result["evidence"]["scores_used"] is False
    assert result["evidence"]["gates_used"] is False


def test_e4_finding_and_confirmation_state_are_consistent():
    result = analyze_e4(_bars([100 + i * 0.05 for i in range(60)]))
    state = result["auction_state"]
    finding = result["finding"]
    if state == "ACCEPTANCE_CONFIRMED":
        assert "ACCEPTANCE_CONFIRMED" in finding
    if state == "REJECTION_CONFIRMED":
        assert "REJECTION_CONFIRMED" in finding
    if result["direction_confirmed"]:
        assert state.endswith("_CONFIRMED")
