from production_v2 import e8_brain, pipeline as pipeline_module
from production_v2.e8_applicability_boundary import _has_surviving_thesis
from production_v2.contracts import EngineResult
from production_v2.pipeline import _attach_profit_edge


def test_watch_is_not_a_surviving_e6_thesis():
    e6 = {
        "setup": "OPPORTUNITY_WATCH",
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": "SELL",
        "watch_only": True,
        "trade_ready": False,
    }
    assert _has_surviving_thesis(e6) is False


def test_pipeline_uses_applicability_guarded_e8():
    assert pipeline_module.analyze_e8 is e8_brain.analyze_e8


def test_e8_does_not_report_probability_blockers_without_e6_thesis():
    snapshot = {
        "bars": [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}] * 40,
        "price": 100.0,
    }
    e6 = {
        "setup": "OPPORTUNITY_WATCH",
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": "SELL",
        "watch_only": True,
        "trade_ready": False,
        "gate_passed": False,
        "reason_codes": ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"],
    }
    result = pipeline_module.analyze_e8(snapshot, {"E6": type("R", (), {"output": e6})()})
    assert result.output["finding"] == "NOT_APPLICABLE"
    assert result.output["reason_codes"] == ["E6_THESIS_REQUIRED"]
    assert "HISTORICAL_SAMPLE_INSUFFICIENT" not in result.output["reason_codes"]
    assert "PROBABILITY_EDGE_NOT_TRUSTWORTHY" not in result.output["reason_codes"]


def test_profit_edge_does_not_reopen_e8_blockers_after_thesis_boundary():
    e8 = EngineResult(
        "E8",
        "Trade Economics Brain",
        False,
        0.0,
        {
            "finding": "NOT_APPLICABLE",
            "direction": "SELL",
            "setup": "OPPORTUNITY_WATCH",
            "economic_state": "NOT_APPLICABLE",
            "trade_plan": {"valid": False},
            "reason_codes": ["E6_THESIS_REQUIRED"],
            "reasons": ["E6_THESIS_REQUIRED"],
            "primary_veto": "E6_THESIS_REQUIRED",
            "veto_class": "NOT_APPLICABLE",
            "applicability": "NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS",
        },
    )
    results = {
        "E1": EngineResult("E1", "Market State Brain", False, 0.0, {}, ()),
        "E5": EngineResult("E5", "Location / Value Brain", False, 0.0, {}, ()),
        "E6": EngineResult("E6", "Setup Brain", False, 0.0, {
            "setup": "OPPORTUNITY_WATCH",
            "direction": "SELL",
            "watch_only": True,
            "trade_ready": False,
        }, ()),
        "E7": EngineResult("E7", "Confirmation Brain", False, 0.0, {}, ()),
        "E8": e8,
    }
    _attach_profit_edge(results, {"symbol": "XAUUSD"})
    output = results["E8"].output
    assert output["finding"] == "NOT_APPLICABLE"
    assert output["reason_codes"] == ["E6_THESIS_REQUIRED"]
    assert "HISTORICAL_SAMPLE_INSUFFICIENT" not in output["reason_codes"]
    assert "PROFIT_EDGE_NOT_PROVEN" not in output["reason_codes"]
    assert "PROBABILITY_EDGE_NOT_TRUSTWORTHY" not in output["reason_codes"]
