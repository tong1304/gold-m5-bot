from production_v2.profit_edge import evaluate_profit_edge


def _row(*, confirmation="CONFIRMED", win=True, r=2.0, location="PREMIUM", regime="TREND_DOWN"):
    return {
        "symbol": "GOLD",
        "direction": "SELL",
        "setup": "LIQUIDITY_REVERSAL",
        "regime": regime,
        "location": location,
        "confirmation": confirmation,
        "win": win,
        "r_multiple": r,
    }


def test_exact_positive_edge_can_be_trusted():
    records = [_row(win=True, r=2.0) for _ in range(45)] + [_row(win=False, r=-1.0) for _ in range(5)]
    edge = evaluate_profit_edge(
        symbol="GOLD",
        regime="TREND_DOWN",
        direction="SELL",
        setup="LIQUIDITY_REVERSAL",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=records,
        realized_rr=2.0,
        cost_r=0.02,
    )
    assert edge["calibration_state"] == "EXACT_CALIBRATED"
    assert edge["exact_sample"] == 50
    assert edge["trusted"] is True
    assert edge["state"] == "POSITIVE_EDGE"
    assert edge["expected_value_r"] > 0.10
    assert edge["stress_expected_value_r"] > 0.0
    assert "PROBABILITY_EDGE_NOT_STATISTICALLY_ROBUST" not in edge["blockers"]


def test_relaxed_context_never_becomes_exact_trust():
    records = [_row(win=True, r=2.0, location="DISCOUNT") for _ in range(35)]
    edge = evaluate_profit_edge(
        symbol="GOLD",
        regime="TREND_DOWN",
        direction="SELL",
        setup="LIQUIDITY_REVERSAL",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=records,
        realized_rr=2.0,
        cost_r=0.02,
    )
    assert edge["calibration_state"] == "RELAXED_CONTEXT_ONLY"
    assert edge["exact_sample"] == 0
    assert edge["trusted"] is False
    assert "CONDITIONAL_SAMPLE_RELAXED" in edge["blockers"]
    assert "PROFIT_EDGE_NOT_TRUSTED" in edge["blockers"]


def test_sparse_context_is_exposed_without_false_confidence():
    records = [_row(win=True, r=2.0) for _ in range(12)]
    edge = evaluate_profit_edge(
        symbol="GOLD",
        regime="TREND_DOWN",
        direction="SELL",
        setup="LIQUIDITY_REVERSAL",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=records,
        realized_rr=2.0,
        cost_r=0.02,
    )
    assert edge["calibration_state"] == "SPARSE_CONTEXT"
    assert edge["trusted"] is False
    assert "PROFIT_EDGE_NOT_PROVEN" in edge["blockers"]
