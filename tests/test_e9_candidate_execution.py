from production_v2.contracts import EngineResult
from production_v2.professional_brain import _execution_readiness


def _plan(direction):
    return {
        "direction": direction,
        "entry": 100.0,
        "stop_loss": 99.0 if direction == "BUY" else 101.0,
        "take_profit_1": 101.5 if direction == "BUY" else 98.5,
        "take_profit_2": 102.0 if direction == "BUY" else 98.0,
        "rr_tp2": 2.0,
    }


def test_e9_selects_e8_candidate_matching_final_direction():
    e8 = EngineResult(
        "E8", "Trade Economics Brain", None, 70.0,
        {
            "trade_plan_candidates": {
                "BUY": _plan("BUY"),
                "SELL": _plan("SELL"),
            },
            "plan_status": "CANDIDATES_READY",
            "risk_gate": "RISK_CANDIDATES_READY",
        },
        (),
    )

    readiness = _execution_readiness({"E8": e8}, "SELL")

    assert readiness["ready"] is True
    assert readiness["plan"]["direction"] == "SELL"
    assert readiness["risk_basis"] == "E8_VERIFIED_CANDIDATE"
