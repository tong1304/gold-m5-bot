from production_v2.pipeline import _trade_plan_complete
from production_v2.contracts import EngineResult


def test_pipeline_accepts_direction_matched_e8_candidate_as_complete_execution_contract():
    plan = {
        "direction": "SELL",
        "entry": 100.0,
        "stop_loss": 101.0,
        "take_profit_1": 98.5,
        "take_profit_2": 98.0,
        "rr_tp2": 2.0,
    }
    e8 = EngineResult("E8", "Trade Economics Brain", None, 70.0, {
        "trade_plan_candidates": {"BUY": {**plan, "direction": "BUY"}, "SELL": plan},
        "risk_gate": "RISK_CANDIDATES_READY",
    }, ())

    assert _trade_plan_complete(e8, direction="SELL") is True
    assert _trade_plan_complete(e8, direction="BUY") is True
