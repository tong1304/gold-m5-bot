from production_v2.professional_brain import _execution_readiness


def _plan(direction="SELL"):
    return {
        "direction": direction,
        "entry": 4600.0,
        "stop_loss": 4610.0 if direction == "SELL" else 4590.0,
        "take_profit_1": 4585.0 if direction == "SELL" else 4615.0,
        "take_profit_2": 4580.0 if direction == "SELL" else 4620.0,
        "rr_tp2": 2.0,
    }


def test_e9_rejects_actionable_direction_without_complete_e8_plan():
    result = _execution_readiness({"E8": {"output": {"trade_plan": None, "risk_gate": "RISK_NOT_READY"}}}, "SELL")
    assert result["ready"] is False
    assert "EXECUTION_PLAN_NOT_READY" in result["reasons"]


def test_e9_requires_complete_trade_plan_before_actionable_decision():
    result = _execution_readiness({"E8": {"output": {"trade_plan": _plan("SELL"), "risk_gate": "RISK_READY"}}}, "SELL")
    assert result["ready"] is True
    assert result["plan"]["direction"] == "SELL"


def test_e9_uses_e8_top_level_risk_gate_not_nested_specialist_status():
    e8_output = {
        "specialists": {
            "8A": {"output": {"risk_gate": "RISK_NOT_READY"}},
            "8G": {"output": {"risk_gate": "RISK_READY"}},
        },
        "risk_gate": "RISK_READY",
        "trade_plan": _plan("SELL"),
    }
    result = _execution_readiness({"E8": {"output": e8_output}}, "SELL")
    assert result["ready"] is True
    assert result["risk_basis"] == "E8_VERIFIED_PLAN"
