from production_v2.contracts import EngineResult
from production_v2.e9_brain import analyze_e9


def _engine(engine_id, output):
    return EngineResult(engine_id, engine_id, False, 0.0, output, tuple(output.get("reason_codes", ())))


def test_e9_preserves_e6_candidate_identity_when_setup_is_only_in_finding():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "structure": "BULLISH", "pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "NEUTRAL", "reason_codes": ("DIRECTIONAL_EDGE_NOT_ESTABLISHED",)}),
        "E3": _engine("E3", {"finding": "BULLISH_STRUCTURE", "lifecycle": "ESTABLISHED", "invalidation": "NO_INVALIDATION"}),
        "E4": _engine("E4", {"event": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING", "liquidity_taker": "BUYERS", "response_actor": "SELLERS"}),
        "E5": _engine("E5", {"finding": "WAIT_CONFIRMATION", "structural_location": "INSIDE_STRUCTURE"}),
        "E6": _engine("E6", {
            "finding": "SELL LIQUIDITY_REVERSAL is a candidate hypothesis only; required upstream proof is incomplete.",
            "reason_codes": ("E2_OPPORTUNITY_UNRESOLVED", "SPACE_CONFLICT"),
            "maturity": "HYPOTHESIS",
        }),
        "E7": _engine("E7", {
            "finding": "The thesis remains a hypothesis; required proof is incomplete.",
            "reason_codes": ("PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING"),
        }),
        "E8": _engine("E8", {
            "risk_state": "UNRESOLVED",
            "reason_codes": ("INVALID_TRADE_GEOMETRY", "REAL_RR_BELOW_MINIMUM"),
        }),
    }

    result = analyze_e9({}, upstream)
    output = result.output if hasattr(result, "output") else result

    assert output["decision"] in {"NO_TRADE", "WAIT_FOR_PROOF"}
    assert output["thesis_state"] == "ESTABLISHED"
    assert output["setup_state"] == "HYPOTHESIS"
    assert output["execution_state"] == "BLOCKED"
    assert output["direction"] == "SELL"
    assert output["setup"] == "LIQUIDITY_REVERSAL"


def test_e9_candidate_identity_never_authorizes_trade_without_confirmation_and_risk():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "structure": "BULLISH", "pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "NEUTRAL"}),
        "E3": _engine("E3", {"finding": "BULLISH_STRUCTURE", "lifecycle": "ESTABLISHED", "invalidation": "NO_INVALIDATION"}),
        "E4": _engine("E4", {"event": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING"}),
        "E5": _engine("E5", {"finding": "WAIT_CONFIRMATION"}),
        "E6": _engine("E6", {
            "finding": "SELL LIQUIDITY_REVERSAL is a candidate hypothesis only; required upstream proof is incomplete.",
            "maturity": "HYPOTHESIS",
        }),
        "E7": _engine("E7", {"confirmation_state": "PENDING", "reason_codes": ("VALID_CLOSED_CANDLE_TRIGGER_MISSING",)}),
        "E8": _engine("E8", {"risk_state": "UNRESOLVED", "reason_codes": ("INVALID_TRADE_GEOMETRY",)}),
    }

    result = analyze_e9({}, upstream)
    output = result.output if hasattr(result, "output") else result

    assert output["decision"] in {"NO_TRADE", "WAIT_FOR_PROOF"}
    assert output["execution_state"] == "BLOCKED"
    assert output["direction"] == "SELL"
    assert output["setup"] == "LIQUIDITY_REVERSAL"
    assert output["all_gates_pass"] is False


def test_e9_exposes_four_layer_governance_and_named_market_control_state():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "structure": "BULLISH", "pressure": "DOWN"}),
        "E2": _engine("E2", {"finding": "DOWN opportunity is developing"}),
        "E3": _engine("E3", {"finding": "BULLISH_STRUCTURE", "structure_direction": "UP", "lifecycle": "ESTABLISHED", "invalidation": "NO_INVALIDATION"}),
        "E4": _engine("E4", {"event": "HIGH_SWEEP_REJECTION", "auction_state": "PENDING", "liquidity_taker": "BUYERS", "response_actor": "SELLERS"}),
        "E5": _engine("E5", {"value_response": "ACCEPTED_BELOW_VALUE"}),
        "E6": _engine("E6", {
            "finding": "SELL LIQUIDITY_REVERSAL is a candidate hypothesis only; required upstream proof is incomplete.",
            "direction": "SELL",
            "setup": "LIQUIDITY_REVERSAL",
            "maturity": "HYPOTHESIS",
        }),
        "E7": _engine("E7", {"confirmation_state": "PENDING", "reason_codes": ("PROOF_GATES_INCOMPLETE", "VALID_CLOSED_CANDLE_TRIGGER_MISSING")}),
        "E8": _engine("E8", {"risk_state": "UNRESOLVED", "reason_codes": ("REAL_RR_BELOW_MINIMUM", "INVALID_TRADE_GEOMETRY")}),
    }

    result = analyze_e9({}, upstream)
    output = result.output if hasattr(result, "output") else result

    assert output["market_control_state"] in {"BUY-CONTROLLED", "SELL-CONTROLLED", "MIXED", "UNRESOLVED"}
    assert output["control_direction"] in {"BUY", "SELL", "NEUTRAL"}
    assert 0.0 <= float(output["control_confidence"]) <= 100.0
    assert output["evidence_alignment"] in {"ALIGNED", "PARTIALLY_ALIGNED", "CONFLICTED", "UNRESOLVED"}
    assert isinstance(output["dominant_control_evidence"], list)
    assert output["governance_layers"]["market_control"] == "MARKET_CONTROL"
    assert output["governance_layers"]["thesis_control"] == "E6_OWNER"
    assert output["governance_layers"]["proof_control"] == "E7_CONFIRMATION_AND_E8_ECONOMICS"
    assert output["governance_layers"]["final_governance"] == "E9_FINAL_AUTHORITY"
    assert output["decision"] in {"EXECUTE", "WAIT_FOR_PROOF", "REJECTED_HARD_CONFLICT", "NO_TRADE", "BUY", "SELL"}


def test_e9_thesis_direction_cannot_be_rewritten_by_market_control():
    upstream = {
        "E1": _engine("E1", {"market_state": "TRANSITION", "pressure": "DOWN", "structure": "BEARISH"}),
        "E2": _engine("E2", {"finding": "DOWN opportunity is developing"}),
        "E3": _engine("E3", {"structure_direction": "DOWN", "finding": "BEARISH_STRUCTURE", "lifecycle": "ESTABLISHED", "invalidation": "NO_INVALIDATION"}),
        "E4": _engine("E4", {"auction_state": "PENDING", "response_actor": "SELLERS"}),
        "E5": _engine("E5", {"repricing_state": "ACCEPTANCE_BELOW_VALUE"}),
        "E6": _engine("E6", {"direction": "BUY", "setup": "PULLBACK", "finding": "BUY PULLBACK is validating", "maturity": "VALIDATING"}),
        "E7": _engine("E7", {"confirmation_state": "PENDING", "reason_codes": ("PROOF_GATES_INCOMPLETE",)}),
        "E8": _engine("E8", {"risk_state": "UNRESOLVED", "reason_codes": ("REAL_RR_BELOW_MINIMUM",)}),
    }

    result = analyze_e9({}, upstream)
    output = result.output if hasattr(result, "output") else result

    assert output["thesis_direction"] == "BUY"
    assert output["direction"] == "BUY"
    assert output["control_direction"] == "SELL"
    assert output["decision"] in {"WAIT_FOR_PROOF", "NO_TRADE"}
    assert output["decision"] != "EXECUTE"
