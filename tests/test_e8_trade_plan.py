from trading_system.engines.e8.g_risk_gate import SubEngine


def _bars():
    bars = []
    for i in range(55):
        close = 100.0 + i * 0.09
        bars.append({"open": close - 0.02, "high": close + 0.08, "low": close - 0.08, "close": close})
    for close in (104.90, 104.95, 105.00, 105.05, 105.00):
        bars.append({"open": close - 0.02, "high": close + 0.08, "low": close - 0.08, "close": close})
    return bars


def test_e8_publishes_complete_trade_plan_when_risk_is_ready():
    result = SubEngine().run({
        "bars": _bars(),
        "risk_policy": {"min_rr": 1.5, "max_stop_atr": 3.0},
        "E6_result": {"6F": {"output": {"state": "MATURE"}}},
        "E7_result": {"7F": {"output": {"state": "CONFIRMATION_PASS"}}},
    })

    assert result.output["risk_gate"] == "RISK_READY"
    plan = result.output["trade_plan"]
    assert plan["direction"] == "BUY"
    for key in ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2"):
        assert plan[key] is not None
    assert plan["stop_loss"] < plan["entry"] < plan["take_profit_1"] < plan["take_profit_2"]
    assert plan["rr_tp2"] >= 1.5


def test_e8_builds_risk_geometry_without_needing_setup_confirmation():
    """E8 owns trade economics; setup maturity belongs to E6/E7/E9."""
    result = SubEngine().run({
        "bars": _bars(),
        "risk_policy": {"min_rr": 1.5, "max_stop_atr": 3.0},
    })

    plan = result.output["trade_plan"]
    assert result.output["plan_status"] == "COMPLETE"
    assert plan["direction"] == "BUY"
    assert plan["entry"] < plan["take_profit_2"]
    assert plan["stop_loss"] < plan["entry"]
    assert plan["rr_tp2"] >= 1.5
