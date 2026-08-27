from production_v2.e4_brain import analyze_e4


def _bars(seq):
    return [{"open": o, "high": h, "low": l, "close": c} for o, h, l, c in seq]


def _base(n=40, price=100):
    return [(price, price + 1, price - 1, price) for _ in range(n)]


def test_historical_liquidity_is_not_a_current_event():
    s = _base()
    s[10] = (100, 106, 99, 105)
    s[-1] = (100, 101, 99.5, 100.2)
    result = analyze_e4({"bars": _bars(s)})
    assert result["finding"] == "NO_CONFIRMED_LIQUIDITY_EVENT"


def test_high_sweep_rejection_produces_downward_evidence_only():
    s = _base()
    s[30] = (100, 105, 99, 104)
    s[-1] = (104, 106.5, 100, 100.5)
    result = analyze_e4({"bars": _bars(s)})
    assert result["finding"] == "HIGH_SWEEP_REJECTION"
    assert result["direction"] == "DOWN"
    assert result["auction_state"] == "REJECTION"
    assert result["trade_decision_authority"] is False


def test_acceptance_requires_closed_candle_displacement():
    s = _base()
    s[30] = (100, 105, 99, 104)
    s[-1] = (104, 106.5, 103.5, 106.2)
    result = analyze_e4({"bars": _bars(s)})
    assert result["finding"] == "HIGH_ACCEPTANCE"
    assert result["direction"] == "UP"


def test_e1_e2_e3_direction_is_context_not_execution_authority():
    result = analyze_e4(
        {"bars": _bars(_base())},
        {"E1": {"evidence": {"finding": "TREND_STATE=DOWN"}}},
    )
    assert result["contextual_direction_hint"] == "DOWN"
    assert result["direction"] == "NEUTRAL"
    assert result["decision"] is None
    assert result["gate"] is None


def test_e4_exposes_recency_confirmation_and_quality_components():
    result = analyze_e4({"bars": _bars(_base())})
    assert "age_bars" in result["event"]
    assert result["event"]["confirmation_state"] in {"CONFIRMED", "UNCONFIRMED", "NONE"}
    assert "event_recency" in result["quality_components"]
    assert "liquidity_quality" in result["quality_components"]
    assert "auction_quality" in result["quality_components"]


def test_e4_current_event_must_be_on_latest_closed_candle():
    s = _base()
    s[30] = (100, 106, 99, 100.2)
    s[-2] = (100, 101, 99.5, 100.2)
    s[-1] = (100.2, 101.0, 99.8, 100.3)
    result = analyze_e4({"bars": _bars(s)})
    assert result["event"]["age_bars"] == 0
    assert result["event"]["type"] == "NO_CONFIRMED_LIQUIDITY_EVENT"
