from production_v2.contracts import EngineResult
from production_v2.e7_thesis_boundary import enforce_e6_thesis_boundary


def _result(output):
    return EngineResult("E7", "Confirmation Brain", False, 50.0, output, ())


def test_concrete_e6_setup_is_not_downgraded_to_opportunity_watch():
    e6 = EngineResult(
        "E6",
        "Setup Brain",
        False,
        70.0,
        {
            "state": "VALIDATING",
            "setup_state": "VALIDATING",
            "setup": "BREAKOUT_RETEST",
            "setup_family": "BREAKOUT_RETEST",
            "candidate_type": "SETUP_CANDIDATE",
            "watch_only": False,
            "setup_exists": True,
            "direction": "BUY",
            "trade_ready": False,
            "e6_causal_gate": "PASSED",
        },
        (),
    )

    def original_e7(snapshot, upstream):
        return _result({
            "confirmation": "DEVELOPING",
            "confirmation_state": "DEVELOPING",
            "trigger_status": "NOT_CONFIRMED",
            "trigger_observed": False,
        })

    result = enforce_e6_thesis_boundary(original_e7, {"bars": []}, {"E6": e6})

    assert result.output["confirmation"] == "DEVELOPING"
    assert result.output["trigger_status"] == "NOT_CONFIRMED"
    assert "E6_OPPORTUNITY_WATCH_NOT_SETUP" not in result.output.get("reason_codes", [])
