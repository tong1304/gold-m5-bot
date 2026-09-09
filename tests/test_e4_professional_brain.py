from production_v2.e4_brain import analyze_e4


def _bars(values):
    return [
        {"open": v - 0.2, "high": v + 0.5, "low": v - 0.5, "close": v, "closed": True}
        for v in values
    ]


def test_e4_is_analysis_only_and_keeps_e9_authority():
    result = analyze_e4(
        _bars([100 + i * 0.1 for i in range(60)]),
        {"E1": {"evidence": {"output": {"score": 99, "gate": True, "direction": "UP"}}}},
    )
    assert result["professional_brain"] is True
    assert result["role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert result["decision_authority"] == "E9_ONLY"
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["score"] is None
    assert result["entry_authorized"] is False


def test_e4_exposes_professional_question_and_auction_lifecycle():
    result = analyze_e4(_bars([100 + i * 0.05 for i in range(60)]))
    assert result["question"] == "Where is liquidity, who took it, and did price accept or reject the auction?"
    assert result["role"] == "LIQUIDITY_AUCTION_ANALYST"
    assert result["observations"]
    assert "auction_state" in result
    assert "auction_confirmation_state" in result
    assert "auction_confirmation" in result
    assert "follow_through" in result
    assert "follow_through_bars" in result
    assert result["lifecycle"] in {"PENDING", "CONFIRMED", "INVALIDATED", "EXPIRED"}


def test_e4_upstream_direction_is_not_authority():
    result = analyze_e4(
        _bars([100 + i * 0.05 for i in range(60)]),
        {"E1": {"evidence": {"output": {"direction": "BUY", "score": 100, "gate": True}}}},
    )
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["score"] is None
    assert result["entry_authorized"] is False
    assert result["decision_authority"] == "E9_ONLY"


def test_e4_finding_confirmation_state_consistency():
    result = analyze_e4(_bars([100 + i * 0.05 for i in range(60)]))
    state = result["auction_state"]
    finding = result["finding"]
    if state == "ACCEPTANCE_CONFIRMED":
        assert "CONFIRMED" in finding
    if state == "REJECTION_CONFIRMED":
        assert "CONFIRMED" in finding
    if result["direction_confirmed"]:
        assert state.endswith("_CONFIRMED")
