from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9, classify_lifecycle


def _r(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", [])))


def test_no_e6_thesis_makes_e7_and_e8_not_applicable():
    result = classify_lifecycle(
        {"state": "ABSENT", "setup": "NONE", "direction": "NEUTRAL", "maturity": "UNRESOLVED"},
        {"state": "NO_SETUP", "confirmation": "NO_SURVIVING_SETUP"},
        {"finding": "UNRESOLVED", "economic_state": "NOT_EVALUABLE", "reason_codes": ["INVALID_TRADE_GEOMETRY"]},
    )
    assert result["stage"] == "NO_THESIS"
    assert result["e7_state"] == "NOT_APPLICABLE"
    assert result["e8_state"] == "NOT_APPLICABLE"
    assert result["reason"] == "NO_SURVIVING_E6_THESIS"


def test_e9_does_not_promote_downstream_e8_noise_to_governance_blockers_without_thesis():
    upstream = {
        "E1": _r("E1", {"pressure": "UP"}),
        "E2": _r("E2", {"finding": "NEUTRAL opportunity is unproven"}),
        "E3": _r("E3", {"finding": "MIXED"}),
        "E4": _r("E4", {"event": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING"}),
        "E5": _r("E5", {"value_response": "ACCEPTED_ABOVE_VALUE"}),
        "E6": _r("E6", {"finding": "No causal setup hypothesis survives current closed-candle evidence.", "state": "ABSENT", "setup": "NONE", "direction": "NEUTRAL", "maturity": "UNRESOLVED", "reason_codes": ["CAUSAL_SETUP_PROOF_INCOMPLETE"]}),
        "E7": _r("E7", {"state": "NO_SETUP", "confirmation": "NO_SURVIVING_SETUP", "reason_codes": ["NO_SURVIVING_SETUP"]}),
        "E8": _r("E8", {"finding": "UNRESOLVED", "economic_state": "NOT_EVALUABLE", "reason_codes": ["INVALID_TRADE_GEOMETRY", "HISTORICAL_SAMPLE_INSUFFICIENT"]}),
    }
    result = analyze_e9({}, upstream)
    assert result.output["final_governance"] == "NO_THESIS"
    assert result.output["confirmation_state"] == "NOT_APPLICABLE"
    assert result.output["economic_state"] == "NOT_APPLICABLE"
    assert result.output["economic_blockers"] == []
    assert "INVALID_TRADE_GEOMETRY" not in result.output["reason_codes"]


def test_e9_keeps_e7_and_e8_as_independent_gates_when_e6_thesis_exists():
    upstream = {
        "E1": _r("E1", {"pressure": "UP"}),
        "E2": _r("E2", {"direction": "UP", "finding": "UP opportunity is developing"}),
        "E3": _r("E3", {"structure_direction": "UP", "external_state": "UP", "internal_state": "UP", "finding": "BULLISH_STRUCTURE"}),
        "E4": _r("E4", {"event": "LOW_SWEEP_REJECTION", "auction_state": "PENDING", "response_actor": "BUYERS"}),
        "E5": _r("E5", {"repricing_state": "ACCEPTANCE_ABOVE_VALUE"}),
        "E6": _r("E6", {"state": "FORMING", "maturity": "HYPOTHESIS", "setup": "LIQUIDITY_REVERSAL", "direction": "BUY", "thesis": "BUY liquidity reversal", "finding": "BUY LIQUIDITY_REVERSAL is forming"}),
        "E7": _r("E7", {"confirmation_state": "PENDING", "reason_codes": ["PROOF_GATES_INCOMPLETE"]}),
        "E8": _r("E8", {"economic_state": "NOT_EVALUABLE", "reason_codes": ["NO_USABLE_STRUCTURAL_TARGET"]}),
    }
    result = analyze_e9({}, upstream)
    assert result.output["final_governance"] == "WAIT_FOR_PROOF"
    assert result.output["confirmation_state"] == "PENDING"
    assert result.output["economic_state"] == "BLOCKED"
    assert result.output["thesis_lifecycle_source"] == "E6"
