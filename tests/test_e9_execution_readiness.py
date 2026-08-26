from production_v2.professional_brain import _execution_readiness


def test_e9_rejects_actionable_direction_without_complete_e8_plan():
    result = _execution_readiness({"E8": {"output": {"trade_plan": None, "risk_gate": "RISK_NOT_READY"}}}, "SELL")
    assert result["ready"] is False
    assert "E8_TRADE_PLAN_INCOMPLETE" in result["reasons"]


def test_e9_requires_complete_trade_plan_before_actionable_decision():
    result = _execution_readiness({"E8": {"output": {"trade_plan": {"entry": 4600, "stop": 4610, "target": 4580, "rr": 2.0}, "risk_gate": "RISK_READY"}}}, "SELL")
    assert result["ready"] is True
