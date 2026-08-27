from trading_system.engines import run_engine


def _bars(n=100):
    bars = []
    price = 3000.0
    for i in range(n):
        close = price + i * 1.5
        bars.append({"open": close - 0.8, "high": close + 1.0, "low": close - 1.0, "close": close})
    return bars


def test_e2_publishes_auction_quality_and_opportunity_score():
    out = run_engine("E2", {"bars": _bars()}, {}).output
    assert out["auction_phase"] in {"ACCEPTANCE", "REPRICING", "BALANCE", "REJECTION", "TRANSITION"}
    assert 0.0 <= out["opportunity_score"] <= 1.0
    assert out["opportunity_quality"] in {"HIGH", "MEDIUM", "LOW"}
    assert out["evidence_map"]["directional_pressure"] in {"UP", "DOWN", "NEUTRAL"}
    assert out["evidence_map"]["location"] in {"EDGE_LOW", "EDGE_HIGH", "MID_RANGE"}


def test_e2_requires_acceptance_not_a_single_spike_for_breakout_opportunity():
    bars = _bars()
    last = bars[-1]["close"]
    for i in (-2, -1):
        bars[i]["high"] = last + 20.0
        bars[i]["close"] = last + (5.0 if i == -1 else 0.5)
        bars[i]["open"] = bars[i]["close"] - 0.2
        bars[i]["low"] = bars[i]["close"] - 0.5
    out = run_engine("E2", {"bars": bars}, {}).output
    assert out["auction_phase"] != "ACCEPTANCE" or out["acceptance_quality"] in {"CONFIRMED", "STRONG"}


def test_e2_range_opportunity_requires_edge_and_rejection():
    bars = []
    for i in range(100):
        close = 3000.0 + (0.7 if i % 2 == 0 else -0.7)
        bars.append({"open": close, "high": close + 2.0, "low": close - 2.0, "close": close})
    out = run_engine("E2", {"bars": bars}, {}).output
    assert out["regime"] == "RANGE"
    assert out["opportunity"] == "WAIT_FOR_RANGE_EDGE"
    assert out["opportunity_state"] == "WAIT"


def test_e2_final_professional_core_separates_idea_from_entry_and_records_counterfactual():
    out = run_engine("E2", {"bars": _bars()}, {}).output
    assert out["architecture"] == "E2_PROFESSIONAL_CORE_ONLY"
    assert out["sub_engines_active"] is False
    assert out["trade_decision_authority"] == "E9_ONLY"
    assert out["entry"] is None
    assert out["trigger"] is None
    assert out["gate"] is None
    assert out["opportunity_decision"] in {"ACTIONABLE_BIAS", "WATCH", "WAIT", "NO_OPPORTUNITY"}
    assert out["edge_assessment"] in {"EDGE_PRESENT", "EDGE_CONDITIONAL", "NO_EDGE"}
    assert isinstance(out["why_not_trade"], list)
    assert isinstance(out["counterfactual"], list)
    assert out["professional_reasoning"]["entry_authorized"] is False
    assert out["professional_reasoning"]["e1_used_as"] == "CROSS_CHECK_ONLY"


def test_e2_does_not_upgrade_direction_into_action_when_location_is_late():
    bars = _bars()
    for i in range(92, 100):
        base = 3000.0 + i * 1.5
        bars[i] = {
            "open": base - 0.2,
            "high": base + 0.5,
            "low": base - 0.3,
            "close": base + 0.4,
        }
    out = run_engine("E2", {"bars": bars}, {}).output
    assert out["direction"] == "UP"
    assert out["opportunity_decision"] in {"WATCH", "WAIT", "NO_OPPORTUNITY"}
    assert "late" in " ".join(out["why_not_trade"]).lower() or out["timing_state"] == "LATE"
