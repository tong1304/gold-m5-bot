from production_v2.professional_opportunity import consolidate, enrich_engine


def test_directional_pending_proof_is_visible_not_executable():
    output = enrich_engine("E6", {"finding": "BUY AUCTION_ACCEPTANCE_CONTINUATION is validating", "confidence": 0.72, "state": "VALIDATING", "reasons": ["SETUP_NOT_TRADE_READY", "SPACE_CONFLICT"]})
    assert output["opportunity_direction"] == "BUY"
    assert output["opportunity_state"] == "OPPORTUNITY_WAITING"
    assert output["professional_opportunity"]["trade_authorized"] is False


def test_e8_block_does_not_erase_opportunity():
    output = enrich_engine("E8", {"finding": "UNRESOLVED", "direction": "BUY", "confidence": 0.8, "reasons": ["REAL_RR_BELOW_MINIMUM", "TARGET_REALISM_TOO_LOW"]})
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


def test_all_nine_scopes_expose_conditional_opportunity_read():
    samples = {
        "E1": {"market_state": "TREND_UP", "direction": "UP", "confidence": 0.8},
        "E2": {"direction": "BUY", "opportunity_maturity": "DEVELOPING", "confidence": 0.7},
        "E3": {"direction": "BUY", "lifecycle": "TRANSITION", "confidence": 0.7},
        "E4": {"direction": "SELL", "auction_state": "PENDING", "event": "HIGH_SWEEP_REJECTION", "confidence": 0.7},
        "E5": {"direction": "SELL", "structural_location": "AT_RESISTANCE", "confidence": 0.7},
        "E6": {"finding": "SELL LIQUIDITY_REVERSAL is validating", "state": "VALIDATING", "confidence": 0.7},
        "E7": {"direction": "SELL", "confirmation_state": "PENDING", "confidence": 0.7},
        "E8": {"direction": "SELL", "confidence": 0.7, "reasons": ["REAL_RR_BELOW_MINIMUM"]},
        "E9": {"decision": "NO_TRADE", "gate_passed": False, "confidence": 0.7},
    }
    for engine, sample in samples.items():
        output = enrich_engine(engine, sample)
        op = output["professional_opportunity"]
        assert op["engine"] == engine
        assert op["authority"] == engine
        assert op["trade_authorized"] is False
        assert op["next_required_event"]
        assert op["conditional_paths"]
        assert "execution" not in op["conditional_paths"][0].lower()


def test_directional_space_is_part_of_quality_not_a_trade_trigger():
    output = enrich_engine("E5", {"direction": "BUY", "confidence": 0.9, "available_space_atr_long": 0.4, "available_space_atr_short": 2.5, "structural_location": "AT_RESISTANCE"})
    op = output["professional_opportunity"]
    assert op["space_atr"] == 0.4
    assert op["space_quality"] < 50
    assert op["trade_authorized"] is False
    assert op["conditional_paths"]


def test_neutral_market_with_directional_radar_is_not_no_opportunity():
    output = enrich_engine("E2", {
        "direction": "NEUTRAL",
        "confidence": 0.3,
        "opportunity_book": {
            "leader": "SELL",
            "competition": "CONTESTED",
            "candidates": [
                {"direction": "BUY", "state": "DEVELOPING", "quality": 0.61, "wait_for": ["BUY_CONFIRMATION"]},
                {"direction": "SELL", "state": "DEVELOPING", "quality": 0.74, "wait_for": ["SELL_CONFIRMATION"]},
            ],
        },
    })
    op = output["professional_opportunity"]
    assert output["opportunity_direction"] == "SELL"
    assert output["opportunity_state"] == "OPPORTUNITY_WAITING"
    assert op["directional_opportunities"]["BUY"]["quality"] == 61.0
    assert op["directional_opportunities"]["SELL"]["quality"] == 74.0
    assert output["opportunity_strength"] == 74.0


def test_consolidate_keeps_both_directional_watches_from_neutral_e2():
    e2 = enrich_engine("E2", {
        "direction": "NEUTRAL",
        "confidence": 0.3,
        "opportunity_book": {
            "leader": "SELL",
            "competition": "CONTESTED",
            "candidates": [
                {"direction": "BUY", "state": "DEVELOPING", "quality": 0.61, "wait_for": ["BUY_CONFIRMATION"]},
                {"direction": "SELL", "state": "DEVELOPING", "quality": 0.74, "wait_for": ["SELL_CONFIRMATION"]},
            ],
        },
    })
    result = consolidate({"E2": type("R", (), {"output": e2})()})
    directional = result["directional_radar"]
    assert set(directional) == {"BUY", "SELL"}
    assert result["leader"] == "SELL"
    assert result["competition"] == "CONTESTED"
    assert result["best"]["direction"] == "SELL"
