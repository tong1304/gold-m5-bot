from production_v2.e4_brain import analyze_e4


def _bars(seq):
    return [{"open": o, "high": h, "low": l, "close": c, "closed": True} for o, h, l, c in seq]


def _base(n=60, price=100.0):
    return [(price, price + 1.0, price - 1.0, price + 0.1) for _ in range(n)]


def test_historical_liquidity_is_not_a_current_event():
    s = _base()
    s[10] = (100, 106, 99, 105)
    result = analyze_e4({"bars": _bars(s)})
    assert result["event"]["type"] == "NO_LIQUIDITY_EVENT"
    assert result["direction"] == "NEUTRAL"
    assert result["direction_confirmed"] is False


def test_three_separated_touches_are_cluster_liquidity():
    s = _base()
    for i, high in ((12, 105.00), (27, 105.03), (42, 104.98)):
        s[i] = (104.5, high, 104.0, 104.7)
    result = analyze_e4({"bars": _bars(s)})
    zones = result["liquidity_map"]["high_zones"]
    assert any(z["kind"] == "CLUSTER_LIQUIDITY" and z["touches"] >= 3 for z in zones)


def test_equal_liquidity_requires_distinct_pivot_touches():
    s = _base()
    s[15] = (104.5, 105.00, 104.0, 104.7)
    s[25] = (104.5, 105.03, 104.0, 104.7)
    result = analyze_e4({"bars": _bars(s)})
    zones = result["liquidity_map"]["high_zones"]
    assert any(z["kind"] == "EQUAL_LIQUIDITY" and z["touches"] == 2 for z in zones)


def test_high_sweep_rejection_requires_follow_through():
    s = _base()
    s[30] = (104.5, 105.0, 104.0, 104.7)
    s[55] = (104.7, 106.5, 100.0, 104.0)
    s[56] = (104.0, 104.5, 101.5, 102.0)
    s[57] = (102.0, 103.0, 99.8, 100.5)
    result = analyze_e4({"bars": _bars(s)})
    assert result["event"]["type"] == "HIGH_SWEEP_REJECTION"
    assert result["direction"] == "DOWN"
    assert result["auction_state"] == "REJECTION_CONFIRMED"


def test_true_acceptance_requires_two_consecutive_post_break_closes():
    s = _base()
    s[30] = (104.5, 105.0, 104.0, 104.7)
    s[55] = (104.8, 106.2, 104.7, 105.8)
    s[56] = (105.8, 106.4, 105.2, 106.0)
    s[57] = (106.0, 106.2, 104.5, 104.8)
    s[58] = (104.8, 105.3, 104.2, 104.7)
    s[59] = (104.7, 105.1, 104.1, 104.6)
    result = analyze_e4({"bars": _bars(s)})
    assert result["auction_state"] != "ACCEPTANCE_CONFIRMED"
    assert result["direction_confirmed"] is False
    assert "TRUE_ACCEPTANCE_NOT_PROVEN" in result["reasons"] or result["auction_state"] in {"INVALIDATED", "EXPIRED"}


def test_actor_is_explicitly_price_action_inference():
    s = _base()
    s[30] = (104.5, 105.0, 104.0, 104.7)
    s[55] = (104.7, 106.5, 100.0, 104.0)
    result = analyze_e4({"bars": _bars(s)})
    event = result["event"]
    assert event["actor_evidence_type"] == "PRICE_ACTION_INFERENCE_ONLY"
    assert "INFERENCE" in event["liquidity_taker"]
    assert "ORDER_FLOW" not in event["actor_evidence_type"]


def test_upstream_direction_is_context_only_and_never_execution_authority():
    result = analyze_e4(
        {"bars": _bars(_base())},
        {"E1": {"evidence": {"finding": "TREND_STATE=DOWN"}}, "E3": {"evidence": {"finding": "DOWN"}}},
    )
    assert result["contextual_direction_hint"] == "DOWN"
    assert result["direction"] == "NEUTRAL"
    assert result["direction_confirmed"] is False
    assert result["decision"] is None
    assert result["gate"] is None
    assert result["trade_decision_authority"] is False


def test_e4_exposes_auditable_reasoning_for_production_trace():
    result = analyze_e4({"bars": _bars(_base())})
    assert result["observations"]
    assert result["analyst_conclusion"] == result["finding"]
    assert result["professional_reasoning"]["question"] == "Where is liquidity, who took it, and did price accept or reject the auction?"
    assert result["professional_reasoning"]["independent_thesis"]
    assert result["audit"]["closed_candle_only"] is True
