from production_v2.profit_edge import evaluate_profit_edge


def test_profit_edge_requires_sufficient_conditional_sample():
    records = [{"direction": "BUY", "setup": "IMPULSE_CONTINUATION", "win": True}] * 29
    result = evaluate_profit_edge(
        symbol="GOLD",
        regime="TREND_UP",
        direction="BUY",
        setup="IMPULSE_CONTINUATION",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=records,
        realized_rr=1.8,
        cost_r=0.05,
    )
    assert result["state"] == "UNTRUSTED"
    assert "PROFIT_EDGE_NOT_PROVEN" in result["blockers"]


def test_profit_edge_is_positive_only_after_cost_stress():
    records = (
        [{"direction": "BUY", "setup": "IMPULSE_CONTINUATION", "win": True, "r_multiple": 1.8}] * 70
        + [{"direction": "BUY", "setup": "IMPULSE_CONTINUATION", "win": False, "r_multiple": -1.0}] * 30
    )
    result = evaluate_profit_edge(
        symbol="GOLD",
        regime="TREND_UP",
        direction="BUY",
        setup="IMPULSE_CONTINUATION",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=records,
        realized_rr=1.8,
        cost_r=0.05,
    )
    assert result["state"] == "POSITIVE_EDGE"
    assert result["expected_value_r"] > 0.10
    assert result["stress_expected_value_r"] > 0.0
    assert result["sample"] == 100


def test_profit_edge_is_conditioned_without_future_bars():
    records = [
        {"direction": "BUY", "setup": "IMPULSE_CONTINUATION", "regime": "TREND_UP", "win": True},
        {"direction": "BUY", "setup": "OTHER", "regime": "TREND_UP", "win": False},
        {"direction": "SELL", "setup": "IMPULSE_CONTINUATION", "regime": "TREND_UP", "win": False},
    ] * 40
    result = evaluate_profit_edge(
        symbol="GOLD",
        regime="TREND_UP",
        direction="BUY",
        setup="IMPULSE_CONTINUATION",
        location="PREMIUM",
        confirmation="CONFIRMED",
        historical_outcomes=records,
        realized_rr=1.8,
        cost_r=0.05,
    )
    assert result["sample"] == 40
    assert result["conditioning"]["regime"] == "TREND_UP"
    assert result["conditioning"]["direction"] == "BUY"
    assert result["conditioning"]["setup"] == "IMPULSE_CONTINUATION"
