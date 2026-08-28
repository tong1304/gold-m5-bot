from production_v2.e4_brain import analyze_e4, _find_recent_event, _follow_through


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


def test_e4_acceptance_candidate_cannot_be_confirmed_without_follow_through():
    bars = _bars([100 + i * 0.1 for i in range(35)])
    event = {
        "type": "HIGH_ACCEPTANCE_CANDIDATE",
        "auction_state": "ACCEPTANCE",
        "directional_implication": "UP",
        "index": 34,
        "zone": {"side": "HIGH", "upper": 103.0, "lower": 102.9},
        "liquidity_taker": "BUY_SIDE_PRESSURE_INFERENCE",
        "actor_evidence_type": "PRICE_ACTION_INFERENCE_ONLY",
    }
    result = _follow_through(event, bars, atr=1.0)
    assert result["present"] is False
    assert result["acceptance_quality"] is False


def test_e4_rejection_requires_post_event_follow_through():
    bars = _bars([100 + i * 0.02 for i in range(35)])
    event = {"type": "HIGH_SWEEP_REJECTION", "auction_state": "REJECTION", "directional_implication": "DOWN", "index": 1, "zone": {"side": "HIGH", "upper": 100.0, "lower": 99.9}}
    assert _follow_through(event, bars[:2], atr=1.0)["present"] is False


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
