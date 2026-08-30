from production_v2.professional_opportunity import consolidate, enrich_engine


def test_directional_pending_proof_is_visible_not_executable():
    output = enrich_engine("E6", {
        "finding": "BUY AUCTION_ACCEPTANCE_CONTINUATION is validating",
        "confidence": 0.72,
        "state": "VALIDATING",
        "reasons": ["SETUP_NOT_TRADE_READY", "SPACE_CONFLICT"],
    })
    assert output["opportunity_direction"] == "BUY"
    assert output["opportunity_state"] == "OPPORTUNITY_WAITING"
    assert output["professional_opportunity"]["trade_authorized"] is False


def test_e8_block_does_not_erase_opportunity():
    output = enrich_engine("E8", {
        "finding": "UNRESOLVED",
        "direction": "BUY",
        "confidence": 0.8,
        "reasons": ["REAL_RR_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW"],
    })
    assert output["opportunity_direction"] == "BUY"
    assert output["opportunity_state"] == "OPPORTUNITY_WAITING"
    assert output["opportunity_stage"] == "ECONOMICALLY_BLOCKED"


def test_e9_only_authorizes_when_gate_and_decision_pass():
    waiting = enrich_engine("E9", {"decision": "BUY", "gate_passed": False, "confidence": 0.9})
    ready = enrich_engine("E9", {"decision": "BUY", "gate_passed": True, "confidence": 0.9})
    assert waiting["professional_opportunity"]["trade_authorized"] is False
    assert ready["professional_opportunity"]["trade_authorized"] is True
    assert waiting["opportunity_state"] == "OPPORTUNITY_WAITING"
    assert ready["opportunity_stage"] == "EXECUTABLE"


def test_consolidate_returns_non_empty_opportunity_radar():
    e1 = enrich_engine("E1", {"market_state": "TREND_UP", "direction": "UP", "confidence": 0.8})
    e6 = enrich_engine("E6", {"finding": "BUY setup validating", "confidence": 0.7, "state": "VALIDATING"})
    result = consolidate({"E1": type("R", (), {"output": e1})(), "E6": type("R", (), {"output": e6})()})
    assert result["count"] >= 1
    assert result["best"] is not None
