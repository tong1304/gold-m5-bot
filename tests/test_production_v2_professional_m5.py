from production_v2.engines import _professional_gate, _trade_plan


def test_e1_requires_dominant_direction_for_short_term_entry():
    output = {
        "1A": {"data_quality": "VALID", "state": "VALID"},
        "1C": {"direction": "UP"},
        "1G": {"state": "NOT_DOMINANT"},
    }
    passed, reasons = _professional_gate("E1", output, {})
    assert passed is False
    assert "E1_DIRECTION_NOT_DOMINANT" in reasons


def test_trade_plan_rejects_structural_stop_that_is_too_wide_for_m5():
    bars = []
    price = 100.0
    for i in range(20):
        bars.append({"open": price, "high": price + 1, "low": price - 1, "close": price + 0.5})
        price += 0.5
    bars[-5]["low"] = 80.0

    plan = _trade_plan(
        {
            "bars": bars,
            "risk_policy": {
                "stop_atr": 1.5,
                "max_stop_atr": 2.5,
                "min_rr": 1.5,
                "target_rr": 2.0,
                "structure_buffer_atr": 0.2,
            },
        },
        "UP",
    )
    assert plan["valid"] is False
    assert plan["reason"] == "STOP_TOO_WIDE_FOR_SHORT_TERM"


def test_trade_plan_reports_actual_risk_and_rr_consistently():
    bars = []
    price = 100.0
    for _ in range(20):
        bars.append({"open": price, "high": price + 1, "low": price - 1, "close": price + 0.2})
        price += 0.2

    plan = _trade_plan(
        {
            "bars": bars,
            "risk_policy": {
                "stop_atr": 1.5,
                "max_stop_atr": 3.0,
                "min_rr": 1.5,
                "target_rr": 2.0,
                "structure_buffer_atr": 0.2,
            },
        },
        "UP",
    )
    assert plan["valid"] is True
    assert abs(plan["risk_distance"] - (plan["entry"] - plan["stop_loss"])) < 1e-9
    assert abs(plan["rr_tp2"] - 2.0) < 1e-9
    assert plan["risk_atr"] <= 3.0
