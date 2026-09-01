from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", [])))


def test_pending_e4_response_is_not_market_control_vote():
    upstream = {
        "E1": _engine("E1", {"pressure": "SELL"}),
        "E2": _engine("E2", {"direction": "SELL"}),
        "E3": _engine("E3", {"structure_integrity": "VALID", "structure_direction": "SELL", "external_state": "DOWN", "internal_state": "DOWN"}),
        "E4": _engine("E4", {"auction_state": "PENDING", "event": "HIGH_SWEEP_REJECTION", "response_actor": "SELLERS"}),
        "E5": _engine("E5", {}),
        "E6": _engine("E6", {"direction": "SELL", "setup": "LIQUIDITY_REVERSAL", "thesis": "sell failed high auction", "setup_state": "MATURE"}),
        "E7": _engine("E7", {"confirmation_state": "PENDING", "trigger_observed": False, "reason_codes": ["PROOF_GATES_INCOMPLETE"]}),
        "E8": _engine("E8", {"risk_state": "UNRESOLVED", "economic_state": "UNRESOLVED"}),
    }
    result = analyze_e9({}, upstream)
    assert result.output["pending_e4_response_excluded"] is True
    assert not any(item["source"] == "E4_CONFIRMED_AUCTION_RESPONSE" for item in result.output["control_evidence"])
    assert result.output["control_scores"]["SELL"] == 6.5


def test_complete_positive_short_path_can_execute():
    upstream = {
        "E1": _engine("E1", {"pressure": "SELL"}),
        "E2": _engine("E2", {"direction": "SELL"}),
        "E3": _engine("E3", {"structure_integrity": "VALID", "structure_direction": "SELL", "external_state": "DOWN", "internal_state": "DOWN"}),
        "E4": _engine("E4", {"auction_state": "REJECTED", "event": "HIGH_SWEEP_REJECTION", "response_actor": "SELLERS"}),
        "E5": _engine("E5", {"repricing_direction": "SELL"}),
        "E6": _engine("E6", {"direction": "SELL", "setup": "LIQUIDITY_REVERSAL", "thesis": "sell failed high auction", "setup_state": "MATURE"}),
        "E7": _engine("E7", {"confirmation_state": "CONFIRMED", "trigger_observed": True, "reason_codes": ["CONFIRMATION_PROVEN"]}),
        "E8": _engine("E8", {"risk_state": "READY", "economic_state": "READY", "verified": True, "trade_plan": {"entry": 100.0, "stop_loss": 101.0, "take_profit": 102.5, "rr": 2.5}}),
    }
    result = analyze_e9({}, upstream)
    assert result.output["decision"] == "SELL"
    assert result.output["execution_state"] == "APPROVED"
    assert result.output["all_gates_pass"] is True
