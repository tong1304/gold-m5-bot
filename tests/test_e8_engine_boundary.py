from production_v2.engines import run_engine


def _bars():
    bars = []
    for i in range(60):
        close = 100.0 + i * 0.10
        bars.append({
            "open": close - 0.02,
            "high": close + 0.08,
            "low": close - 0.08,
            "close": close,
        })
    return bars


def test_e8_exposes_verified_trade_plan_at_engine_boundary():
    """E8's verified risk plan must be consumable directly by E9."""
    result = run_engine(
        "E8",
        {
            "symbol": "GOLD",
            "timeframe": "M5",
            "bars": _bars(),
            "risk_policy": {"min_rr": 1.5, "max_stop_atr": 3.0},
        },
    )

    plan = result.output["trade_plan"]
    assert plan["verified"] is True
    assert plan["direction"] == "BUY"
    assert plan["entry"] < plan["take_profit_1"] < plan["take_profit_2"]
    assert plan["stop_loss"] < plan["entry"]
    assert plan["rr_tp2"] >= 1.5
