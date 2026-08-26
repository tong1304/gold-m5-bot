from production_v2.contracts import EngineResult
from production_v2.pipeline import _normalize_e8_execution_boundary


def test_e8_exposes_verified_trade_plan_at_e9_boundary():
    """E9 receives E8's execution contract without knowing E8 internals."""
    plan = {
        "direction": "BUY",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit_1": 101.5,
        "take_profit_2": 102.0,
        "rr_tp2": 2.0,
        "verified": True,
    }
    e8 = EngineResult(
        "E8",
        "Trade Economics Brain",
        None,
        55.0,
        {
            "specialists": {
                "8A": {"output": {"state": "INVALIDATION_DEFINED"}},
                "8G": {
                    "output": {
                        "trade_plan": plan,
                        "plan_status": "COMPLETE",
                        "risk_gate": "RISK_READY",
                        "risk_basis": "E8_VERIFIED_GEOMETRY",
                        "direction": "BUY",
                    }
                },
            }
        },
        (),
    )

    normalized = _normalize_e8_execution_boundary(e8)
    assert normalized is not None
    assert normalized.output["trade_plan"] == plan
    assert normalized.output["plan_status"] == "COMPLETE"
    assert normalized.output["risk_gate"] == "RISK_READY"
    assert normalized.output["direction"] == "BUY"
