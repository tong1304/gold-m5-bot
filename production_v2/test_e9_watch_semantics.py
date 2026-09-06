from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, output.get("gate_passed", False), 0.0, output, tuple(output.get("reason_codes", ())))


def test_e9_watch_waits_for_setup_proof_before_e7_trigger():
    upstream = {
        "E1": _engine("E1", {"pressure": "BEARISH", "market_state": "TRANSITION"}),
        "E2": _engine("E2", {"opportunity_decision": "NEUTRAL", "reason_codes": ["DIRECTIONAL_EDGE_NOT_ESTABLISHED"]}),
        "E3": _engine("E3", {"structure": "MIXED", "reason_codes": ["PROTECTED_STRUCTURE_INCOMPLETE"]}),
        "E4": _engine("E4", {"event": "HIGH_FAILED_BREAK_RECLAIM", "auction_state": "PENDING", "reason_codes": ["AUCTION_NOT_TERMINALLY_CONFIRMED"]}),
        "E5": _engine("E5", {"value_state": "DISCOUNT", "reason_codes": ["STRUCTURAL_SPACE_INSUFFICIENT"]}),
        "E6": _engine("E6", {
            "setup": "OPPORTUNITY_WATCH",
            "candidate_type": "OPPORTUNITY_CANDIDATE",
            "direction": "SELL",
            "watch_only": True,
            "trade_ready": False,
            "thesis_state": "HYPOTHESIS",
            "finding": "SELL opportunity is being watched; causal setup is not yet proven.",
            "missing_proof": ["E4_AUCTION_FOLLOW_THROUGH", "E3_INTERNAL_STRUCTURE_ALIGNMENT"],
        }),
        "E7": _engine("E7", {"confirmation_state": "NOT_APPLICABLE", "reason_codes": ["CONFIRMATION_NOT_APPLICABLE"]}),
        "E8": _engine("E8", {"finding": "NOT_APPLICABLE", "applicability": "NOT_APPLICABLE_WITHOUT_SURVIVING_E6_THESIS"}),
    }

    result = analyze_e9({}, upstream)

    assert result.output["decision"] == "NO_TRADE"
    assert result.output["governance_decision"] == "WATCH"
    assert "E7_VALID_CLOSED_CANDLE_TRIGGER_REQUIRED" not in result.output["next_required_events"]
    assert "E6_SETUP_THESIS_REQUIRED" in result.output["next_required_events"]
    assert "E7_TRIGGER_BLOCKED_UNTIL_E6_THESIS" in result.output["next_required_events"]
    assert result.output["execution_state"] == "BLOCKED"
