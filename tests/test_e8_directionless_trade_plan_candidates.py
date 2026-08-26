from trading_system.engines.e8.g_risk_gate import SubEngine


def _bars():
    bars = []
    for i in range(60):
        close = 100.0 + (0.01 if i % 2 == 0 else -0.005)
        bars.append({"open": close - 0.02, "high": close + 0.08, "low": close - 0.08, "close": close})
    return bars


def test_e8_publishes_directionless_trade_plan_candidates_when_direction_is_unresolved():
    result = SubEngine().run({
        "bars": _bars(),
        "risk_policy": {"min_rr": 1.5, "max_stop_atr": 3.0},
    })

    assert result.output["direction"] == "NEUTRAL"
    assert result.output["plan_status"] == "CANDIDATES_READY"
    candidates = result.output["trade_plan_candidates"]
    assert set(candidates) == {"BUY", "SELL"}
    for direction, plan in candidates.items():
        assert plan["direction"] == direction
        for key in ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2"):
            assert plan[key] is not None
        assert plan["rr_tp2"] >= 1.5
