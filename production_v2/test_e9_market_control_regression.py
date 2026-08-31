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

    assert result["decision"] == "NO_TRADE"
    assert result["thesis_state"] == "ESTABLISHED"
    assert result["setup_state"] == "HYPOTHESIS"
    assert result["execution_state"] == "BLOCKED"
    assert result["direction"] == "SELL"
    assert result["setup"] == "LIQUIDITY_REVERSAL"


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

    assert result["decision"] == "NO_TRADE"
    assert result["execution_state"] == "BLOCKED"
    assert result["direction"] == "SELL"
    assert result["setup"] == "LIQUIDITY_REVERSAL"
    assert result["all_gates_pass"] is False
