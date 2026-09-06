from production_v2.contracts import EngineResult
from production_v2 import e9_brain


def test_e9_watch_boundary_never_surfaces_economic_blockers():
    e6 = {
        "setup": "OPPORTUNITY_WATCH",
        "setup_state": "FORMING",
        "direction": "SELL",
        "watch_only": True,
        "trade_ready": False,
        "gate_passed": False,
        "thesis_status": "FORMING",
        "reason_codes": ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"],
    }
    e7 = {"finding": "NOT_APPLICABLE", "reason_codes": ["E6_OPPORTUNITY_WATCH_NOT_SETUP"]}
    e8 = {
        "finding": "NOT_APPLICABLE",
        "applicability": "NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS",
        "reason_codes": ["E6_THESIS_REQUIRED"],
        "economic_state": "NOT_APPLICABLE",
    }
    upstream = {
        "E1": EngineResult("E1", "E1", False, 0.0, {"pressure": "BEARISH"}, ()),
        "E2": EngineResult("E2", "E2", False, 0.0, {}, ()),
        "E3": EngineResult("E3", "E3", False, 0.0, {"external_state": "MIXED"}, ()),
        "E4": EngineResult("E4", "E4", False, 0.0, {"auction_state": "PENDING"}, ()),
        "E5": EngineResult("E5", "E5", False, 0.0, {}, ()),
        "E6": EngineResult("E6", "E6", False, 0.0, e6, ()),
        "E7": EngineResult("E7", "E7", False, 0.0, e7, ()),
        "E8": EngineResult("E8", "E8", False, 0.0, e8, ()),
    }
    result = e9_brain.analyze_e9({}, upstream)
    assert result.output["decision"] == "NO_TRADE"
    assert result.output["final_governance"] == "WATCH"
    assert result.output["governance_reason"] == "WAITING_FOR_E6_SETUP_THESIS"
    assert not any(code in result.output["reason_codes"] for code in {
        "STOP_QUALITY_TOO_LOW",
        "REAL_RR_BELOW_MINIMUM",
        "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
        "TARGET_REALISM_TOO_LOW",
        "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    })
