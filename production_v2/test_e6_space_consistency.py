from production_v2.contracts import EngineResult
from production_v2.e6_pending_event_surgery import _normalize_space_consistency


def _result(direction="SELL", missing=None):
    return EngineResult("E6", "Setup Brain", False, 0.0, {
        "setup": "OPPORTUNITY_WATCH",
        "direction": direction,
        "watch_only": True,
        "missing_proof": list(missing or ["E2_OPPORTUNITY_CONFIRMATION", "E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]),
        "missing_evidence": list(missing or ["E2_OPPORTUNITY_CONFIRMATION", "E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]),
        "reason_codes": list(missing or ["E2_OPPORTUNITY_CONFIRMATION", "E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]),
        "reasons": list(missing or ["E2_OPPORTUNITY_CONFIRMATION", "E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]),
        "wait_for": ",".join(missing or ["E2_OPPORTUNITY_CONFIRMATION", "E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]),
    }, ())


def _upstream(short_space):
    return {"E5": EngineResult("E5", "Location", False, 0.0, {
        "available_space_atr_long": 0.8828526314,
        "available_space_atr_short": short_space,
    }, ())}


def test_sell_space_above_threshold_cannot_report_structural_space_insufficient():
    result = _normalize_space_consistency(
        _result(missing=["E2_OPPORTUNITY_CONFIRMATION", "STRUCTURAL_SPACE_INSUFFICIENT", "E7_CONFIRMATION"]),
        _upstream(1.8566488777),
    )
    assert result.output["available_space_atr"] == 1.8566
    assert "STRUCTURAL_SPACE_INSUFFICIENT" not in result.output["missing_proof"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" not in result.output["reason_codes"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" not in result.output["wait_for"]
    assert result.output["space_consistency_authority"] == "E5"


def test_sell_space_below_threshold_must_report_structural_space_insufficient():
    result = _normalize_space_consistency(
        _result(),
        _upstream(0.50),
    )
    assert result.output["available_space_atr"] == 0.5
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result.output["missing_proof"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result.output["reason_codes"]
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result.output["wait_for"]


def test_buy_uses_long_space_not_sell_space():
    result = _normalize_space_consistency(
        _result(direction="BUY", missing=["E7_CONFIRMATION"]),
        {"E5": EngineResult("E5", "Location", False, 0.0, {
            "available_space_atr_long": 0.50,
            "available_space_atr_short": 1.80,
        }, ())},
    )
    assert result.output["available_space_atr"] == 0.5
    assert "STRUCTURAL_SPACE_INSUFFICIENT" in result.output["missing_proof"]
