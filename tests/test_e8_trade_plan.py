from trading_system.engines.e8.g_risk_gate import SubEngine


def _bars():
    bars = []
    for i in range(60):
        close = 100.0 + i * 0.04
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


def test_e8_expectancy_uses_execution_adjusted_rr_once():
    """REAL_RR already normalizes execution cost; EV must not charge it twice."""
    from production_v2.e8_brain import _economic

    result = _economic(
        geometry={"real_rr": 1.50},
        probability={"trusted": True, "stress_probability": 0.60},
        execution={"cost_atr": 0.05},
        survival={"state": "ROBUST"},
        space={"state": "USABLE", "effective_available_space_atr": 2.0},
        target_realism={"state": "REALISTIC"},
        stop_quality={"state": "QUALITY"},
    )

    assert result["expected_value_r"] == 0.50
    assert result["expected_win_r"] == 0.90
    assert result["expected_loss_r"] == 0.40
    assert result["economic_edge_r"] == 0.50
    assert result["breakeven_probability"] == 0.40
