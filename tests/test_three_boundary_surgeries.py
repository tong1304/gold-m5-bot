from production_v2.contracts import EngineResult
from production_v2.e6_opportunity_guard import _watch
from production_v2.e8_applicability_boundary import _not_applicable
from production_v2 import e9_brain


def test_e6_watch_normalizes_stale_no_setup_finding():
    original = EngineResult(
        "E6",
        "Setup Formation Brain",
        False,
        0.0,
        {
            "finding": "No causal setup hypothesis survives current closed-candle evidence.",
            "setup": "OPPORTUNITY_WATCH",
            "direction": "SELL",
            "watch_only": True,
            "trade_ready": False,
            "gate_passed": False,
            "reason_codes": ["E4_AUCTION_FOLLOW_THROUGH"],
        },
        (),
    )
    candidate = {
        "direction": "SELL",
        "family": "LIQUIDITY_RESPONSE",
        "space": 0.42,
        "missing": ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"],
        "support": ["E4_DIRECTIONAL_AUCTION_EVIDENCE"],
        "counter": [],
        "event_id": "candle|event",
        "contested": False,
    }
    result = _watch(original, candidate)
    assert result.output["setup"] == "OPPORTUNITY_WATCH"
    assert result.output["watch_only"] is True
    assert result.output["finding"].startswith("SELL opportunity is forming")
    assert "No causal setup hypothesis survives" not in result.output["finding"]


def test_e8_not_applicable_boundary_does_not_execute_original_engine():
    called = {"value": False}

    def original(_snapshot, _results):
        called["value"] = True
        return EngineResult("E8", "Trade Economics Brain", False, 99.0, {"finding": "SHOULD_NOT_RUN"}, ())

    result = _not_applicable(original, {})
    assert result.output["finding"] == "NOT_APPLICABLE"
    assert result.output["reason_codes"] == ["E6_THESIS_REQUIRED"]
    assert called["value"] is False


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
    assert result.output["governance_reason"] == "WAITING_FOR_E7_TRIGGER"
    assert not any(code in result.output["reason_codes"] for code in {
        "STOP_QUALITY_TOO_LOW",
        "REAL_RR_BELOW_MINIMUM",
        "PROBABILITY_EDGE_NOT_TRUSTWORTHY",
        "TARGET_REALISM_TOO_LOW",
        "STRUCTURAL_SURVIVAL_NOT_PROVEN",
    })
