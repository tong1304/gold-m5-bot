from trading_system.engines.e8.g_risk_gate import SubEngine


def _bars():
    bars = []
    for i in range(55):
        close = 100.0 + i * 0.09
        high = 106.0 if i == 50 else close + 0.20
        bars.append({"open": close - 0.08, "high": high, "low": close - 0.20, "close": close})
    for close in (104.0, 104.3, 104.6, 104.8, 105.0):
        bars.append({"open": close - 0.08, "high": close + 0.20, "low": close - 0.20, "close": close})
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
